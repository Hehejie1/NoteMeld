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
