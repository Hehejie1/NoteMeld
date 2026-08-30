import { useEffect, useMemo, useState } from 'react'
import type CloudClient from '../services/cloud'
import { CloudSessionController, CloudSessionState } from '../services/cloudSessionController'

export function useCloudSession(client: CloudClient, sessionId?: string) {
  const controller = useMemo(() => new CloudSessionController(client), [client])
  const [state, setState] = useState<CloudSessionState>(controller.getState())
  useEffect(() => controller.subscribe(setState), [controller])
  useEffect(() => {
    if (!sessionId) return
    void controller.open(sessionId)
    const timer = window.setInterval(() => { void controller.refreshEvents().catch(() => undefined) }, 5000)
    return () => window.clearInterval(timer)
  }, [controller, sessionId])
  return { ...state, controller }
}
