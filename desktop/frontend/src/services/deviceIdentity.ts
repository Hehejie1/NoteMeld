const INSTALL_ID_KEY = 'notemeld.install-id.v1'

function randomInstallId(): string {
  const bytes = new Uint8Array(16)
  crypto.getRandomValues(bytes)
  return Array.from(bytes, byte => byte.toString(16).padStart(2, '0')).join('')
}

/** Return a stable, non-secret install identifier for this app installation. */
export function getOrCreateInstallId(storage?: Storage): string {
  const created = randomInstallId()
  try {
    const target = storage ?? window.localStorage
    const existing = target.getItem(INSTALL_ID_KEY)
    if (existing && /^[a-f0-9]{32}$/.test(existing)) return existing
    target.setItem(INSTALL_ID_KEY, created)
  } catch {
    // Private browsing or a restrictive storage policy can deny access. The
    // ephemeral fallback still permits this session to register safely.
  }
  return created
}

/** Platform prefix + install id is the device identity sent to cloud. */
export function makeDeviceId(platform: string, installId = getOrCreateInstallId()): string {
  const normalized = platform.trim().toLowerCase().replace(/[^a-z0-9_-]/g, '-')
  if (!normalized || normalized.length > 32 || !/^[a-z0-9][a-z0-9_-]*$/.test(normalized)) throw new Error('invalid device platform')
  if (!/^[a-f0-9]{32}$/.test(installId)) throw new Error('invalid install id')
  return `${normalized}-${installId}`
}
