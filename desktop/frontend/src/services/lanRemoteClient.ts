import { openRelayWebSocket } from './connectionStrategy'
import type { DeviceKeyMaterial } from './deviceKeyStore'
import { decryptRemoteFrame, encryptRemoteFrame } from './relayFrameCrypto'
import { type RemoteFrame, RELAY_PROTOCOL_VERSION } from './relayProtocol'
import { createHandshake, deriveHandshakeKey, handshakeJson, verifyHandshake, type HandshakeEnvelope } from './e2eeHandshake'

const LAN_PROTOCOL_VERSION = 'notemeld.lan.v1'
const encoder = new TextEncoder()

function encode(value: ArrayBuffer | Uint8Array): string {
  const bytes = value instanceof Uint8Array ? value : new Uint8Array(value)
  let binary = ''
  bytes.forEach(byte => { binary += String.fromCharCode(byte) })
  return btoa(binary).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '')
}

function decode(value: string): Uint8Array {
  const normalized = value.replace(/-/g, '+').replace(/_/g, '/') + '='.repeat((4 - value.length % 4) % 4)
  const binary = atob(normalized)
  return Uint8Array.from(binary, character => character.charCodeAt(0))
}

function encodeProofMessage(sessionId: string, controllerDeviceId: string, hostDeviceId: string, challengeId: string, challenge: string): Uint8Array {
  const values = [sessionId, controllerDeviceId, hostDeviceId, challengeId, challenge]
  if (values.some(value => !value || value.includes('\0'))) throw new Error('invalid LAN proof field')
  return new Uint8Array([...encoder.encode('notemeld-lan-auth-v1\0'), ...values.flatMap((value, index) => index === values.length - 1 ? [...encoder.encode(value)] : [...encoder.encode(value), 0])])
}

interface RemoteClientOptions {
  cloudBaseUrl: string
  relayToken: string
  sessionId: string
  controllerDeviceId: string
  hostDeviceId: string
  hostConnectivity: { lan_endpoints?: string[] }
  keyMaterial: DeviceKeyMaterial
  sessionKey?: CryptoKey
  hostPublicKey?: string
  authorityEpoch: number
  onEvent?: (event: Record<string, unknown>) => void
}

export interface LanRemoteClient {
  transport: 'lan' | 'relay'
  send(input: string, requestId?: string): Promise<Record<string, unknown>>
  close(): void
}

/**
 * Connect to a remote Host using LAN proof first and cloud Relay second.
 * Session key provisioning remains an explicit platform concern; this client
 * never invents or persists a key the Host cannot verify.
 */
export async function connectLanRemoteClient(options: RemoteClientOptions): Promise<LanRemoteClient> {
  let authorizedEpoch = options.authorityEpoch
  let transport: 'lan' | 'relay' = 'relay'
  let handshakePromise: Promise<void> | null = null
  const socketResult = await openRelayWebSocket(
    options.cloudBaseUrl,
    options.sessionId,
    options.hostConnectivity,
    options.relayToken,
    3_000,
    socket => {
      transport = 'lan'
      handshakePromise = runLanHandshake(socket, options, epoch => { authorizedEpoch = epoch })
      return handshakePromise
    },
  )
  const socket = socketResult.connection
  transport = socketResult.candidate.transport
  if (handshakePromise) await handshakePromise
  let sessionKey = options.sessionKey
  let sequence = 0
  if (transport === 'lan' && !sessionKey) {
    if (!options.hostPublicKey) throw new Error('LAN Host public key is required for E2EE handshake')
    const handshake = await createHandshake(options.keyMaterial, options.sessionId, options.controllerDeviceId, options.hostDeviceId)
    socket.send(handshakeJson(handshake.local))
    const peer = await receiveJson(socket, value => value.protocol_version === 'notemeld.e2ee.handshake.v1') as unknown as HandshakeEnvelope
    await verifyHandshake(peer, options.sessionId, options.hostDeviceId, options.controllerDeviceId, options.hostPublicKey)
    sessionKey = await deriveHandshakeKey(handshake, peer)
  } else if (transport === 'relay' && !sessionKey) {
    if (!options.hostPublicKey) throw new Error('Host public key is required for Relay E2EE handshake')
    const handshake = await createHandshake(options.keyMaterial, options.sessionId, options.controllerDeviceId, options.hostDeviceId)
    const nonce = crypto.getRandomValues(new Uint8Array(12))
    const handshakeFrame: RemoteFrame = {
      protocol_version: RELAY_PROTOCOL_VERSION,
      session_id: options.sessionId,
      sender_device_id: options.controllerDeviceId,
      recipient_device_id: options.hostDeviceId,
      sequence: 1,
      frame_id: crypto.randomUUID(),
      authority_epoch: authorizedEpoch,
      frame_type: 'handshake',
      nonce: encode(nonce),
      ciphertext: encode(encoder.encode(handshakeJson(handshake.local))),
    }
    socket.send(JSON.stringify(handshakeFrame))
    const peerFrame = await receiveJson(socket, value => value.frame_type === 'handshake')
    const peerPayload = JSON.parse(new TextDecoder().decode(decode(String(peerFrame.ciphertext)))) as HandshakeEnvelope
    await verifyHandshake(peerPayload, options.sessionId, options.hostDeviceId, options.controllerDeviceId, options.hostPublicKey)
    sessionKey = await deriveHandshakeKey(handshake, peerPayload)
    sequence = 1
  }
  if (!sessionKey) throw new Error('remote session key is unavailable')
  const pending = new Map<string, { resolve: (value: Record<string, unknown>) => void; reject: (reason: Error) => void }>()
  const onMessage = async (event: MessageEvent) => {
    try {
      const value = JSON.parse(String(event.data)) as Record<string, unknown>
      if (value.type === 'rejected' || value.type === 'failed') {
        const error = new Error(String(value.error || 'remote frame rejected'))
        for (const item of pending.values()) item.reject(error)
        pending.clear()
        return
      }
      if (value.type === 'received') {
        const frameId = String(value.frame_id || '')
        const item = pending.get(frameId)
        if (item) { pending.delete(frameId); item.resolve(value) }
        return
      }
      if (!value.frame_type) return
      const payload = JSON.parse(await decryptRemoteFrame(value, sessionKey)) as Record<string, unknown>
      if (value.frame_type === 'event') {
        options.onEvent?.(payload)
        return
      }
      const frameId = typeof payload.frame_id === 'string' ? payload.frame_id : ''
      const item = pending.get(frameId)
      if (item) { pending.delete(frameId); item.resolve(payload) }
    } catch (error) {
      for (const item of pending.values()) item.reject(error instanceof Error ? error : new Error(String(error)))
      pending.clear()
    }
  }
  socket.addEventListener('message', event => { void onMessage(event) })
  return {
    transport,
    send: async (input, requestId = crypto.randomUUID()) => {
      if (!input.trim()) throw new Error('remote input is required')
      const frameId = crypto.randomUUID()
      sequence += 1
      const metadata: Omit<RemoteFrame, 'nonce' | 'ciphertext'> = { protocol_version: RELAY_PROTOCOL_VERSION, session_id: options.sessionId, sender_device_id: options.controllerDeviceId, recipient_device_id: options.hostDeviceId, sequence, frame_id: frameId, authority_epoch: authorizedEpoch, frame_type: 'command' }
      const frame = await encryptRemoteFrame(metadata, sessionKey, JSON.stringify({ request_id: requestId, input }))
      return await new Promise<Record<string, unknown>>((resolve, reject) => { pending.set(frameId, { resolve, reject }); socket.send(JSON.stringify(frame)) })
    },
    close: () => { for (const item of pending.values()) item.reject(new Error('remote connection closed')); pending.clear(); socket.close() },
  }
}

async function runLanHandshake(socket: WebSocket, options: RemoteClientOptions, onEpoch: (epoch: number) => void): Promise<void> {
  socket.send(JSON.stringify({ type: 'hello', protocol_version: LAN_PROTOCOL_VERSION, controller_device_id: options.controllerDeviceId }))
  const challenge = await receiveJson(socket, value => value.type === 'challenge')
  const signature = await options.keyMaterial.signBytes(encodeProofMessage(options.sessionId, options.controllerDeviceId, options.hostDeviceId, String(challenge.challenge_id), String(challenge.challenge)))
  socket.send(JSON.stringify({ type: 'proof', challenge_id: challenge.challenge_id, challenge: challenge.challenge, signature }))
  const authorized = await receiveJson(socket, value => value.type === 'authorized')
  if (authorized.session_id !== options.sessionId || authorized.host_device_id !== options.hostDeviceId) throw new Error('LAN authorization identity mismatch')
  if (typeof authorized.authority_epoch !== 'number' || authorized.authority_epoch < 1) throw new Error('LAN authorization epoch is invalid')
  onEpoch(authorized.authority_epoch)
}

function receiveJson(socket: WebSocket, predicate: (value: Record<string, unknown>) => boolean): Promise<Record<string, unknown>> {
  return new Promise((resolve, reject) => {
    const timer = window.setTimeout(() => { socket.removeEventListener('message', onMessage); reject(new Error('LAN handshake timed out')) }, 10_000)
    const onMessage = (event: MessageEvent) => {
      try {
        const value = JSON.parse(String(event.data)) as Record<string, unknown>
        if (value.type === 'rejected' || value.type === 'failed') throw new Error(String(value.error || 'LAN handshake rejected'))
        if (!predicate(value)) return
        window.clearTimeout(timer); socket.removeEventListener('message', onMessage); resolve(value)
      } catch (error) { window.clearTimeout(timer); socket.removeEventListener('message', onMessage); reject(error instanceof Error ? error : new Error(String(error))) }
    }
    socket.addEventListener('message', onMessage)
  })
}
