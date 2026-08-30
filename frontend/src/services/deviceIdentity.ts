const INSTALL_ID_KEY = 'notemeld.install-id.v1'

function randomInstallId(): string {
  const bytes = new Uint8Array(16)
  crypto.getRandomValues(bytes)
  return Array.from(bytes, byte => byte.toString(16).padStart(2, '0')).join('')
}

/** Return a stable, non-secret install identifier for this app installation. */
export function getOrCreateInstallId(storage: Storage = window.localStorage): string {
  const existing = storage.getItem(INSTALL_ID_KEY)
  if (existing && /^[a-f0-9]{32}$/.test(existing)) return existing
  const created = randomInstallId()
  storage.setItem(INSTALL_ID_KEY, created)
  return created
}

/** Platform prefix + install id is the device identity sent to cloud. */
export function makeDeviceId(platform: string, installId = getOrCreateInstallId()): string {
  const normalized = platform.trim().toLowerCase().replace(/[^a-z0-9_-]/g, '-')
  if (!normalized || normalized.length > 32 || !/^[a-z0-9][a-z0-9_-]*$/.test(normalized)) throw new Error('invalid device platform')
  if (!/^[a-f0-9]{32}$/.test(installId)) throw new Error('invalid install id')
  return `${normalized}-${installId}`
}
