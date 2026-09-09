import type { CloudTokenStore } from './cloud'

/** In-memory store for tests, private browsing, or explicitly ephemeral sessions. */
export class MemoryTokenStore implements CloudTokenStore {
  private token: string | null = null
  async load() { return this.token }
  async save(token: string) { this.token = token }
  async clear() { this.token = null }
}

/**
 * Browser token store backed by IndexedDB. The token value is encrypted with a
 * non-extractable AES-GCM key supplied by the platform/bootstrap layer.
 */
export class IndexedDbTokenStore implements CloudTokenStore {
  constructor(private readonly cryptoKey: CryptoKey, private readonly dbName = 'notemeld-secure', private readonly keyName = 'cloud-token') {}

  async load(): Promise<string | null> {
    const value = await this.read()
    if (!value) return null
    try {
      const plaintext = await crypto.subtle.decrypt({ name: 'AES-GCM', iv: value.iv }, this.cryptoKey, value.ciphertext)
      return new TextDecoder().decode(plaintext)
    } catch {
      throw new Error('secure cloud token is corrupted or key is unavailable')
    }
  }

  async save(token: string): Promise<void> {
    if (!token || token.length > 4096) throw new Error('invalid cloud token')
    const iv = crypto.getRandomValues(new Uint8Array(12))
    const ciphertext = await crypto.subtle.encrypt({ name: 'AES-GCM', iv }, this.cryptoKey, new TextEncoder().encode(token))
    await this.write({ iv, ciphertext })
  }

  async clear(): Promise<void> {
    const db = await this.open()
    await new Promise<void>((resolve, reject) => {
      const request = db.transaction('tokens', 'readwrite').objectStore('tokens').delete(this.keyName)
      request.onsuccess = () => resolve()
      request.onerror = () => reject(request.error ?? new Error('secure token delete failed'))
    })
    db.close()
  }

  private open(): Promise<IDBDatabase> {
    return new Promise((resolve, reject) => {
      // Keep this helper on the same schema version as the bootstrap path
      // below. Opening an existing v2 database at v1 throws VersionError.
      const request = indexedDB.open(this.dbName, 2)
      request.onupgradeneeded = () => {
        if (!request.result.objectStoreNames.contains('tokens')) request.result.createObjectStore('tokens')
        if (!request.result.objectStoreNames.contains('keys')) request.result.createObjectStore('keys')
      }
      request.onsuccess = () => resolve(request.result)
      request.onerror = () => reject(request.error ?? new Error('secure token database unavailable'))
    })
  }

  private async read(): Promise<{ iv: Uint8Array; ciphertext: ArrayBuffer } | null> {
    const db = await this.open()
    return new Promise((resolve, reject) => {
      const request = db.transaction('tokens', 'readonly').objectStore('tokens').get(this.keyName)
      request.onsuccess = () => { db.close(); resolve(request.result ?? null) }
      request.onerror = () => { db.close(); reject(request.error ?? new Error('secure token read failed')) }
    })
  }

  private async write(value: { iv: Uint8Array; ciphertext: ArrayBuffer }): Promise<void> {
    const db = await this.open()
    return new Promise((resolve, reject) => {
      const request = db.transaction('tokens', 'readwrite').objectStore('tokens').put(value, this.keyName)
      request.onsuccess = () => { db.close(); resolve() }
      request.onerror = () => { db.close(); reject(request.error ?? new Error('secure token write failed')) }
    })
  }
}

/** Load or create a non-extractable browser key stored separately from the token ciphertext. */
export async function openIndexedDbTokenStore(dbName = 'notemeld-secure'): Promise<IndexedDbTokenStore> {
  const db = await new Promise<IDBDatabase>((resolve, reject) => {
    const request = indexedDB.open(dbName, 2)
    request.onupgradeneeded = () => {
      if (!request.result.objectStoreNames.contains('tokens')) request.result.createObjectStore('tokens')
      if (!request.result.objectStoreNames.contains('keys')) request.result.createObjectStore('keys')
    }
    request.onsuccess = () => resolve(request.result)
    request.onerror = () => reject(request.error ?? new Error('secure token database unavailable'))
  })
  const existing = await new Promise<CryptoKey | null>((resolve, reject) => {
    const read = db.transaction('keys', 'readonly').objectStore('keys').get('cloud-token-key')
    read.onsuccess = () => resolve(read.result ?? null)
    read.onerror = () => reject(read.error ?? new Error('secure token key unavailable'))
  })
  const key = existing ?? await crypto.subtle.generateKey({ name: 'AES-GCM', length: 256 }, false, ['encrypt', 'decrypt'])
  if (!existing) await new Promise<void>((resolve, reject) => {
    const write = db.transaction('keys', 'readwrite').objectStore('keys').put(key, 'cloud-token-key')
    write.onsuccess = () => resolve()
    write.onerror = () => reject(write.error ?? new Error('secure token key unavailable'))
  })
  db.close()
  return new IndexedDbTokenStore(key, dbName)
}
