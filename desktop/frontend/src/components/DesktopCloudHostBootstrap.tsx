import { useEffect, useState } from 'react'
import { bootstrap_persisted_cloud_host, get_cloud_host_status, stop_cloud_host, type CloudHostStatus } from '@/services/desktopRuntime'
import { CLOUD_TOKEN_CHANGED_EVENT } from '@/services/tokenStore'
import { shouldUseDesktopRuntime } from '@/utils/runtime'

const RETRY_INTERVAL_MS = 30_000

/** Keep the desktop remote Host alive independently of the current route. */
export default function DesktopCloudHostBootstrap({ backendReady }: { backendReady: boolean }) {
  const [status, setStatus] = useState<CloudHostStatus | null>(null)

  useEffect(() => {
    if (!backendReady || !shouldUseDesktopRuntime()) return
    let active = true
    let timer: number | undefined
    let inFlight = false
    let desiredTokenPresent = true

    const bootstrap = async () => {
      if (inFlight) return
      inFlight = true
      let shouldRetry = true
      try {
        const result = await bootstrap_persisted_cloud_host(
          import.meta.env.VITE_CLOUD_BASE_URL || 'http://127.0.0.1:8583',
        )
        if (!active) return
        if (!desiredTokenPresent) {
          await stop_cloud_host()
          shouldRetry = false
          return
        }
        if (result) {
          const nextStatus = await get_cloud_host_status()
          if (active) setStatus(nextStatus)
          shouldRetry = false
        }
      } catch {
        // A transient Cloud/network failure is retried without exposing credentials.
      } finally {
        inFlight = false
      }
      if (active && shouldRetry) timer = window.setTimeout(() => void bootstrap(), RETRY_INTERVAL_MS)
    }

    const tokenChanged = (event: Event) => {
      const present = (event as CustomEvent<{ present?: boolean }>).detail?.present === true
      desiredTokenPresent = present
      if (timer !== undefined) window.clearTimeout(timer)
      timer = undefined
      if (present) {
        void bootstrap()
      } else {
        setStatus(null)
        void stop_cloud_host().catch(() => undefined)
      }
    }

    window.addEventListener(CLOUD_TOKEN_CHANGED_EVENT, tokenChanged)
    void bootstrap()
    return () => {
      active = false
      window.removeEventListener(CLOUD_TOKEN_CHANGED_EVENT, tokenChanged)
      if (timer !== undefined) window.clearTimeout(timer)
    }
  }, [backendReady])

  if (status?.status !== 'running' || !status.device_id || !status.public_key_sha256) return null
  return (
    <span
      className="sr-only"
      aria-label={`notemeld-cloud-host:running:${status.device_id}:${status.public_key_sha256}`}
    />
  )
}
