const DB_VERSION = 2
const DB_NAME = 'notemeld-secure'
const KEY_NAME = 'device-ed25519-keypair'

export interface DeviceKeyMaterial {
  publicKey: string
  signBytes(payload: Uint8Array): Promise<string>
  sign(payload: string): Promise<string>
}

function encode(value: ArrayBuffer | Uint8Array): string {
  const bytes = value instanceof Uint8Array ? value : new Uint8Array(value)
  let binary = ''
  bytes.forEach(byte => { binary += String.fromCharCode(byte) })
  return btoa(binary).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '')
}

function openDatabase(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, DB_VERSION)
    request.onupgradeneeded = () => {
      if (!request.result.objectStoreNames.contains('tokens')) request.result.createObjectStore('tokens')
      if (!request.result.objectStoreNames.contains('keys')) request.result.createObjectStore('keys')
    }
    request.onsuccess = () => resolve(request.result)
    request.onerror = () => reject(request.error ?? new Error('secure device key database unavailable'))
  })
}

async function readKeyPair(db: IDBDatabase): Promise<CryptoKeyPair | null> {
  return await new Promise((resolve, reject) => {
    const request = db.transaction('keys', 'readonly').objectStore('keys').get(KEY_NAME)
    request.onsuccess = () => resolve(request.result ?? null)
    request.onerror = () => reject(request.error ?? new Error('secure device key read failed'))
  })
}

async function writeKeyPair(db: IDBDatabase, keyPair: CryptoKeyPair): Promise<void> {
  await new Promise<void>((resolve, reject) => {
    const request = db.transaction('keys', 'readwrite').objectStore('keys').put(keyPair, KEY_NAME)
    request.onsuccess = () => resolve()
    request.onerror = () => reject(request.error ?? new Error('secure device key write failed'))
  })
}

/** Create or load the device signing key without exposing the private key. */
export async function openDeviceKeyMaterial(): Promise<DeviceKeyMaterial> {
  if (!crypto.subtle) throw new Error('WebCrypto is unavailable')
  const db = await openDatabase()
  try {
    const existing = await readKeyPair(db)
    const keyPair = existing ?? await crypto.subtle.generateKey({ name: 'Ed25519' }, false, ['sign', 'verify']) as CryptoKeyPair
    if (!existing) await writeKeyPair(db, keyPair)
    const publicKey = encode(await crypto.subtle.exportKey('raw', keyPair.publicKey))
    return {
      publicKey,
      signBytes: async (payload: Uint8Array) => encode(await crypto.subtle.sign({ name: 'Ed25519' }, keyPair.privateKey, payload)),
      sign: async (payload: string) => encode(await crypto.subtle.sign({ name: 'Ed25519' }, keyPair.privateKey, new TextEncoder().encode(payload))),
    }
  } finally {
    db.close()
  }
}
