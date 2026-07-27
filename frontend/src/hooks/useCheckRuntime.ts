import { useCallback, useEffect, useRef, useState } from 'react'
import {
  ensureDesktopRuntimeReady,
  getRuntimeApiBaseUrl,
  shouldUseDesktopRuntime,
} from '@/utils/runtime'

export type RuntimeInitStatus = 'checking' | 'ready' | 'failed'

export type UseCheckRuntimeResult = {
  status: RuntimeInitStatus
  ready: boolean
  checkNow: () => Promise<void>
}

export const useCheckRuntime = (): UseCheckRuntimeResult => {
  const [status, setStatus] = useState<RuntimeInitStatus>(() =>
    shouldUseDesktopRuntime() ? 'checking' : 'ready',
  )
  const checkRef = useRef<() => Promise<void>>(async () => {})

  const checkNow = useCallback(async () => {
    setStatus(shouldUseDesktopRuntime() ? 'checking' : 'ready')
    await checkRef.current()
  }, [])

  useEffect(() => {
    let disposed = false

    const check = async () => {
      if (!shouldUseDesktopRuntime()) {
        if (!disposed) {
          setStatus('ready')
        }
        return
      }

      try {
        if (getRuntimeApiBaseUrl()) {
          if (!disposed) {
            setStatus('ready')
          }
          return
        }

        if (!disposed) {
          setStatus('checking')
        }
        await ensureDesktopRuntimeReady()
        if (disposed) return
        setStatus('ready')
      } catch (error) {
        console.warn('[NoteMeld] runtime init check failed', error)
        if (disposed) return
        setStatus('failed')
      }
    }

    checkRef.current = check
    void check()

    return () => {
      disposed = true
    }
  }, [])

  return {
    status,
    ready: status === 'ready',
    checkNow,
  }
}
