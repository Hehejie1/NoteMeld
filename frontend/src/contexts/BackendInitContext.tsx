import { createContext, useCallback, useContext, useMemo, type PropsWithChildren } from 'react'
import { useCheckBackend, type BackendCheckPhase, type UseCheckBackendResult } from '@/hooks/useCheckBackend.ts'
import { useCheckRuntime } from '@/hooks/useCheckRuntime.ts'

export type RuntimeInitStatus = 'checking' | 'ready' | 'failed'
export type BackendInitStatus = 'checking' | 'ready' | 'retrying' | 'failed'
export type BackendInitFailureKind = 'runtime' | 'backend'

export type BackendInitContextValue = UseCheckBackendResult & {
  status: BackendInitStatus
  phase: BackendCheckPhase
  runtimeStatus: RuntimeInitStatus
  runtimeReady: boolean
  backendStatus: BackendInitStatus
  backendReady: boolean
  failureKind: BackendInitFailureKind | null
}

const BackendInitContext = createContext<BackendInitContextValue | null>(null)

export const BackendInitProvider = ({ children }: PropsWithChildren) => {
  const runtimeInit = useCheckRuntime()
  const runtimeStatus = runtimeInit.status
  const runtimeReady = runtimeInit.ready
  const backendInit = useCheckBackend({ runtimeReady })
  const backendStatus = backendInit.status
  const backendReady = backendInit.initialized || backendStatus === 'ready'
  const failureKind =
    runtimeStatus === 'failed' ? 'runtime' : backendStatus === 'failed' ? 'backend' : null
  const checkNow = useCallback(async () => {
    if (runtimeStatus !== 'ready') {
      await runtimeInit.checkNow()
      return
    }
    await backendInit.checkNow()
  }, [runtimeStatus, runtimeInit, backendInit])
  const value = useMemo(
    () => ({
      ...backendInit,
      checkNow,
      runtimeStatus,
      runtimeReady,
      backendStatus,
      backendReady,
      failureKind,
    }),
    [backendInit, checkNow, runtimeStatus, runtimeReady, backendStatus, backendReady, failureKind],
  )

  return <BackendInitContext.Provider value={value}>{children}</BackendInitContext.Provider>
}

export const useBackendInitContext = () => {
  const context = useContext(BackendInitContext)

  if (!context) {
    throw new Error('useBackendInitContext must be used within BackendInitProvider')
  }

  return context
}
