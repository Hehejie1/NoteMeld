const encoder = new TextEncoder()
const decoder = new TextDecoder()

function encode(value: ArrayBuffer | Uint8Array): string { const bytes = value instanceof Uint8Array ? value : new Uint8Array(value); let binary = ''; bytes.forEach(byte => { binary += String.fromCharCode(byte) }); return btoa(binary).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '') }
function decode(value: string): Uint8Array { const normalized = value.replace(/-/g, '+').replace(/_/g, '/') + '='.repeat((4 - value.length % 4) % 4); const binary = atob(normalized); return Uint8Array.from(binary, character => character.charCodeAt(0)) }

export async function encryptRelayPayload(key: CryptoKey, payload: string, associatedData: string): Promise<{ nonce: string; ciphertext: string }> {
  if (!payload || payload.length > 4 * 1024 * 1024) throw new Error('relay payload exceeds limit')
  const nonce = crypto.getRandomValues(new Uint8Array(12))
  const ciphertext = await crypto.subtle.encrypt({ name: 'AES-GCM', iv: nonce, additionalData: encoder.encode(associatedData) }, key, encoder.encode(payload))
  return { nonce: encode(nonce), ciphertext: encode(ciphertext) }
}

export async function decryptRelayPayload(key: CryptoKey, nonce: string, ciphertext: string, associatedData: string): Promise<string> {
  const plaintext = await crypto.subtle.decrypt({ name: 'AES-GCM', iv: decode(nonce), additionalData: encoder.encode(associatedData) }, key, decode(ciphertext))
  return decoder.decode(plaintext)
}
