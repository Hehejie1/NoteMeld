import { useEffect, useMemo, useState } from 'react'
import CloudClient, { CloudClientError } from '../services/cloud'
import { CloudSessionController, CloudSessionState } from '../services/cloudSessionController'

export function useCloudSession(client: CloudClient, sessionId?: string) {
  const controller = useMemo(() => new CloudSessionController(client), [client])
  const [state, setState] = useState<CloudSessionState>(controller.getState())
  useEffect(() => controller.subscribe(setState), [controller])
  useEffect(() => {
    if (!sessionId) return
    void controller.open(sessionId)
    let polling = true
    const timer = window.setInterval(() => {
      if (!polling) return
      void controller.refreshEvents().catch(error => {
        // A session can be deleted or archived by another Cloud client. Stop
        // polling a terminal 404 instead of producing a permanent Network
        // error storm against a stale selection.
        if (error instanceof CloudClientError && error.statusCode === 404) {
          polling = false
          window.clearInterval(timer)
          controller.reset()
        }
      })
    }, 5000)
    return () => {
      polling = false
      window.clearInterval(timer)
      controller.reset()
    }
  }, [controller, sessionId])
  return { ...state, controller }
}
