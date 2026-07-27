import { useCallback, useEffect, useRef, useState } from 'react'
import { getRuntimeApiBaseUrl } from '@/utils/runtime'

const MAX_RETRIES = 30
const RETRY_INTERVAL = 2000
export type BackendInitStatus = 'checking' | 'ready' | 'retrying' | 'failed'
export type BackendCheckPhase = 'runtime' | 'sys_check' | 'retry_wait' | 'sys_health' | 'ready'
export type UseCheckBackendOptions = {
  runtimeReady: boolean
}

export type UseCheckBackendResult = {
  status: BackendInitStatus
  blocking: boolean
  loading: boolean
  initialized: boolean
  phase: BackendCheckPhase
  retryCount: number
  checkNow: () => Promise<void>
}

const resolveBackendInitApiBaseUrl = () =>
  (getRuntimeApiBaseUrl() || import.meta.env.VITE_API_BASE_URL || '/api').replace(/\/$/, '')

const silentBackendGet = async (path: string) => {
  const response = await fetch(`${resolveBackendInitApiBaseUrl()}${path}`, { cache: 'no-store' })
  if (!response.ok) {
    throw new Error(`backend init request failed: ${response.status}`)
  }

  const payload = await response.json().catch(() => null)
  if (!payload || payload.code !== 0) {
    throw new Error(payload?.msg || 'backend init request failed')
  }

  return payload.data
}

export const useCheckBackend = ({ runtimeReady }: UseCheckBackendOptions): UseCheckBackendResult => {
  const [status, setStatus] = useState<BackendInitStatus>('checking')
  const [initialized, setInitialized] = useState(false)
  const [phase, setPhase] = useState<BackendCheckPhase>('runtime')
  const [retryCount, setRetryCount] = useState(0)
  const checkRef = useRef<() => Promise<void>>(async () => {})
  const retryTimerRef = useRef<number | undefined>(undefined)
  const retriesRef = useRef(0)

  const blocking = status !== 'ready' && status !== 'failed'
  const loading = blocking
  const checkNow = useCallback(async () => {
    retriesRef.current = 0
    setRetryCount(0)
    setInitialized(false)
    setStatus('checking')
    setPhase(runtimeReady ? 'sys_check' : 'runtime')
    if (retryTimerRef.current) {
      window.clearTimeout(retryTimerRef.current)
      retryTimerRef.current = undefined
    }
    if (!runtimeReady) {
      return
    }
    await checkRef.current()
  }, [runtimeReady])
  const nonBlockingResult = () => {
    return { status, blocking, initialized, phase, retryCount, checkNow }
  }

  useEffect(() => {
    let disposed = false
    const startedAt = Date.now()

    if (!runtimeReady) {
      setInitialized(false)
      setStatus('checking')
      setPhase('runtime')
      return () => {
        disposed = true
        if (retryTimerRef.current) {
          window.clearTimeout(retryTimerRef.current)
          retryTimerRef.current = undefined
        }
      }
    }

    const logPhase = (nextPhase: BackendCheckPhase, detail?: string) => {
      if (disposed) return
      setPhase(nextPhase)
      console.info(
        `[NoteMeld] backend init phase=${nextPhase} elapsed=${Date.now() - startedAt}ms${detail ? ` ${detail}` : ''}`,
      )
    }

    const check = async () => {
      try {
        setStatus('checking')
        logPhase('sys_check')
        await silentBackendGet('/sys_check')
        if (disposed) return
        retriesRef.current = 0
        setRetryCount(0)
        setStatus('ready')
        setInitialized(true)
        logPhase('ready')
      } catch (error) {
        console.warn('[NoteMeld] backend init check failed', error)
        if (retriesRef.current < MAX_RETRIES) {
          retriesRef.current++
          setRetryCount(retriesRef.current)
          setStatus('retrying')
          logPhase('retry_wait', `retry=${retriesRef.current}/${MAX_RETRIES}`)
          retryTimerRef.current = window.setTimeout(check, RETRY_INTERVAL)
        } else {
          setStatus('failed')
        }
      }
    }

    checkRef.current = check

    check()

    return () => {
      disposed = true
      if (retryTimerRef.current) {
        window.clearTimeout(retryTimerRef.current)
        retryTimerRef.current = undefined
      }
    }
  }, [runtimeReady])

  return { ...nonBlockingResult(), loading }
}
