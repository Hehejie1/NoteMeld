export const RELAY_PROTOCOL_VERSION = 'notemeld.sync.v1'

export type RelayFrameType = 'command' | 'receipt' | 'event' | 'handshake'
export interface RemoteFrame {
  protocol_version: typeof RELAY_PROTOCOL_VERSION
  session_id: string
  sender_device_id: string
  recipient_device_id: string
  sequence: number
  frame_id: string
  authority_epoch: number
  frame_type: RelayFrameType
  nonce: string
  ciphertext: string
}

function decodeBase64Url(value: string): Uint8Array {
  if (!/^[A-Za-z0-9_-]+$/.test(value)) throw new Error('invalid base64url value')
  const normalized = value.replace(/-/g, '+').replace(/_/g, '/') + '='.repeat((4 - value.length % 4) % 4)
  const binary = atob(normalized)
  return Uint8Array.from(binary, character => character.charCodeAt(0))
}

export function validateRemoteFrame(value: unknown, maxCiphertextBytes = 4 * 1024 * 1024): RemoteFrame {
  if (!value || typeof value !== 'object') throw new Error('invalid relay frame')
  const frame = value as Partial<RemoteFrame>
  if (frame.protocol_version !== RELAY_PROTOCOL_VERSION || typeof frame.session_id !== 'string' || !frame.session_id ||
      typeof frame.sender_device_id !== 'string' || !frame.sender_device_id || typeof frame.recipient_device_id !== 'string' || !frame.recipient_device_id ||
      typeof frame.frame_id !== 'string' || !frame.frame_id || typeof frame.sequence !== 'number' || !Number.isSafeInteger(frame.sequence) || frame.sequence < 1 ||
      typeof frame.authority_epoch !== 'number' || !Number.isSafeInteger(frame.authority_epoch) || frame.authority_epoch < 0 ||
      !['command', 'receipt', 'event', 'handshake'].includes(frame.frame_type ?? '') || typeof frame.nonce !== 'string' || typeof frame.ciphertext !== 'string' || !frame.ciphertext) {
    throw new Error('invalid relay frame')
  }
  if (decodeBase64Url(frame.nonce).byteLength !== 12) throw new Error('invalid relay frame nonce')
  if (decodeBase64Url(frame.ciphertext).byteLength > maxCiphertextBytes) throw new Error('relay ciphertext exceeds limit')
  return frame as RemoteFrame
}

export function relayAssociatedData(frame: RemoteFrame): string {
  const metadata = { ...frame }
  delete metadata.ciphertext
  return JSON.stringify(metadata, Object.keys(metadata).sort())
}
