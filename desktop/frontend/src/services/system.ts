import request from '@/utils/request'

export const systemCheck = async () => {
  return await request.get('/sys_health')
}

export interface DeployStatus {
  backend: {
    status: string
    port: number
  }
  cuda: {
    available: boolean
    version: string | null
    gpu_name: string | null
  }
  whisper: {
    model_size: string
    transcriber_type: string
  }
  ffmpeg: {
    available: boolean
  }
  mcp: {
    status: 'running' | 'error' | 'unavailable'
    url: string
    port: number
    tools_count: number
    auth_required: boolean
    error: string | null
  }
}

export const getDeployStatus = async (): Promise<DeployStatus> => {
  return await request.get('/deploy_status')
}

export const recheckMcpStatus = async (): Promise<DeployStatus['mcp']> => {
  return await request.post('/mcp/recheck')
}

export interface MonitoringSnapshot {
  window: { days: number; start_at: string; end_at: string; provider_id?: string | null }
  health: { status: 'healthy' | 'degraded'; components: Record<string, string> }
  usage: { total_tokens: number; record_count: number; overview: Record<string, unknown> }
  tasks: { task_count: number; call_count: number; running: number; completed: number; failed: number; other: number }
  task_rows?: Array<{ task_id: string; call_count: number; total_tokens: number; status?: string | null; latest_call_at?: string | null }>
  providers?: Array<{ provider_id: string; provider_name: string; call_count: number; total_tokens: number; failed: number }>
  runtime: DeployStatus
  plugins: { ready: boolean; failed_plugins: string[]; status: string }
}

export const getMonitoringSnapshot = async (days = 1, providerId?: string): Promise<MonitoringSnapshot> => {
  return await request.get('/monitoring/snapshot', { params: { days, ...(providerId ? { provider_id: providerId } : {}) } })
}
