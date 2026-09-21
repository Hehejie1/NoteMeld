import type { DeviceKeyMaterial } from './deviceKeyStore'

const encoder = new TextEncoder()
const protocolVersion = 'notemeld.e2ee.handshake.v1'

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

function handshakeMessage(sessionId: string, sender: string, recipient: string, ephemeralPublic: Uint8Array): Uint8Array {
  if ([sessionId, sender, recipient].some(value => !value || value.includes('\0'))) throw new Error('invalid handshake identity')
  return concat(encoder.encode('notemeld-e2ee-v1\0'), encoder.encode(sessionId), new Uint8Array([0]), encoder.encode(sender), new Uint8Array([0]), encoder.encode(recipient), new Uint8Array([0]), ephemeralPublic)
}

function concat(...parts: Uint8Array[]): Uint8Array {
  const size = parts.reduce((total, part) => total + part.byteLength, 0)
  const result = new Uint8Array(size)
  let offset = 0
  for (const part of parts) { result.set(part, offset); offset += part.byteLength }
  return result
}

export interface HandshakeEnvelope {
  protocol_version: typeof protocolVersion
  session_id: string
  sender_device_id: string
  recipient_device_id: string
  ephemeral_public: string
  signature: string
}

export interface HandshakeState {
  local: HandshakeEnvelope
  localPrivate: CryptoKey
}

/** Create the signed X25519 offer used by Python Host and other platforms. */
export async function createHandshake(keyMaterial: DeviceKeyMaterial, sessionId: string, sender: string, recipient: string): Promise<HandshakeState> {
  const generated = await crypto.subtle.generateKey({ name: 'X25519' } as unknown as AlgorithmIdentifier, true, ['deriveBits']) as CryptoKeyPair
  const ephemeralPublic = new Uint8Array(await crypto.subtle.exportKey('raw', generated.publicKey))
  const signature = await keyMaterial.signBytes(handshakeMessage(sessionId, sender, recipient, ephemeralPublic))
  return { local: { protocol_version: protocolVersion, session_id: sessionId, sender_device_id: sender, recipient_device_id: recipient, ephemeral_public: encode(ephemeralPublic), signature }, localPrivate: generated.privateKey }
}

export async function verifyHandshake(envelope: HandshakeEnvelope, expectedSessionId: string, expectedSender: string, expectedRecipient: string, publicKey: string): Promise<void> {
  if (envelope.protocol_version !== protocolVersion || envelope.session_id !== expectedSessionId || envelope.sender_device_id !== expectedSender || envelope.recipient_device_id !== expectedRecipient) throw new Error('handshake endpoint mismatch')
  const publicBytes = decode(envelope.ephemeral_public)
  const signingKey = await crypto.subtle.importKey('raw', decode(publicKey), { name: 'Ed25519' } as unknown as AlgorithmIdentifier, false, ['verify'])
  const valid = await crypto.subtle.verify({ name: 'Ed25519' } as unknown as AlgorithmIdentifier, signingKey, decode(envelope.signature), handshakeMessage(envelope.session_id, envelope.sender_device_id, envelope.recipient_device_id, publicBytes))
  if (!valid) throw new Error('invalid handshake signature')
}

export async function deriveHandshakeKey(state: HandshakeState, peer: HandshakeEnvelope): Promise<CryptoKey> {
  if (state.local.session_id !== peer.session_id || state.local.sender_device_id !== peer.recipient_device_id || state.local.recipient_device_id !== peer.sender_device_id) throw new Error('handshake endpoint mismatch')
  const peerPublic = decode(peer.ephemeral_public)
  const peerKey = await crypto.subtle.importKey('raw', peerPublic, { name: 'X25519' } as unknown as AlgorithmIdentifier, false, [])
  const shared = await crypto.subtle.deriveBits({ name: 'X25519', public: peerKey } as unknown as AlgorithmIdentifier, state.localPrivate, 256)
  const localPublic = decode(state.local.ephemeral_public)
  const first = state.local.sender_device_id < peer.sender_device_id ? [state.local.sender_device_id, localPublic, peer.sender_device_id, peerPublic] : [peer.sender_device_id, peerPublic, state.local.sender_device_id, localPublic]
  const transcript = concat(encoder.encode('notemeld-e2ee-transcript-v1\0'), handshakeMessage(state.local.session_id, first[0] as string, first[2] as string, new Uint8Array()), first[1] as Uint8Array, first[3] as Uint8Array)
  const hkdfKey = await crypto.subtle.importKey('raw', shared, 'HKDF', false, ['deriveKey'])
  return await crypto.subtle.deriveKey({ name: 'HKDF', hash: 'SHA-256', salt: new Uint8Array(), info: transcript }, hkdfKey, { name: 'AES-GCM', length: 256 }, false, ['encrypt', 'decrypt'])
}

export function handshakeJson(envelope: HandshakeEnvelope): string { return JSON.stringify(envelope) }

export const handshakeProtocolVersion = protocolVersion
