import request from '@/utils/request.ts'

export const getProviderList = async () => {
  return await request.get('/get_all_providers')
}
export const getProviderById = async (id: string) => {
  return await request.get(`/get_provider_by_id/${id}`)
}
export const updateProviderById = async (data: Record<string, unknown>) => {
  return await request.post('/update_provider', data)
}

export const addProvider = async (data: Record<string, unknown>) => {
  return await request.post('/add_provider', data)
}

export const testConnection = async (data: Record<string, unknown>) => {
  return await request.post('/connect_test', data)
}

export const fetchModels = async (providerId: string, options?: { noCache?: boolean }) => {
  void options
  return await request.get('/model_list/' + providerId)
}

export const fetchModelsByConfig = async (data: {
  api_key?: string
  base_url: string
  name?: string
}) => {
  return await request.post('/model_list_by_config', data)
}

export const fetchEnableModelById = async (id: string) => {
  return await request.get('/model_enable/' + id)
}

export interface ModelRuntimeConfigPayload {
  provider_id: string
  model_name: string
  context_window_tokens: number
  supports_vision: boolean
  supports_stream: boolean
}

export interface ModelRuntimeDefaults {
  model_name: string
  context_window_tokens: number
  supports_vision: boolean
  supports_stream: boolean
  source: string
  matched_rule: string | null
}

export async function fetchModelDefaults(modelName: string): Promise<ModelRuntimeDefaults> {
  return request.post('/models/defaults', { model_name: modelName })
}

export async function addModel(data: ModelRuntimeConfigPayload) {
  return request.post('/models', data)
}

export async function probeModelCapability(data: { provider_id: string; model_name: string }) {
  return request.post('/models/probe', data, { timeout: 20000 })
}

export const fetchEnableModels = async () => {
  return await request.get('/model_list')
}

export const deleteModelById = async (modelId: number) => {
  return await request.get(`/models/delete/${modelId}`)
}

export const fetchProviderTemplates = async () => {
  return await request.get('/provider_templates')
}

export const saveProviderTemplate = async (data: {
  name: string
  logo: string
  base_url: string
}) => {
  return await request.post('/provider_templates', data)
}
