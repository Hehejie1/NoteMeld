import { relayAssociatedData, RemoteFrame, validateRemoteFrame } from './relayProtocol'

const encoder = new TextEncoder()
const decoder = new TextDecoder()

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

export async function encryptRemoteFrame(
  metadata: Omit<RemoteFrame, 'nonce' | 'ciphertext'>,
  key: CryptoKey,
  payload: string,
): Promise<RemoteFrame> {
  if (payload.length > 4 * 1024 * 1024) throw new Error('relay payload exceeds limit')
  const nonce = crypto.getRandomValues(new Uint8Array(12))
  const frame = { ...metadata, nonce: encode(nonce), ciphertext: '' } as RemoteFrame
  const ciphertext = await crypto.subtle.encrypt(
    { name: 'AES-GCM', iv: nonce, additionalData: encoder.encode(relayAssociatedData(frame)) },
    key,
    encoder.encode(payload),
  )
  return { ...frame, ciphertext: encode(ciphertext) }
}

export async function decryptRemoteFrame(frame: unknown, key: CryptoKey): Promise<string> {
  const validated = validateRemoteFrame(frame)
  const plaintext = await crypto.subtle.decrypt(
    { name: 'AES-GCM', iv: decode(validated.nonce), additionalData: encoder.encode(relayAssociatedData(validated)) },
    key,
    decode(validated.ciphertext),
  )
  return decoder.decode(plaintext)
}
