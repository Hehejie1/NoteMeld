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

// 编辑态：使用后端库内 Fernet 密钥测试，前端无法也不得拿到明文 Key
export const testSavedConnection = async (data: { provider_id: string; model_id?: string }) => {
  return await request.post('/connect_test_saved', data)
}

export const fetchModels = async (providerId: string, options?: { noCache?: boolean }) => {
  void options
  return await request.get('/model_list/' + providerId)
}

export const fetchModelsByConfig = async (data: {
  api_key?: string
  base_url: string
  name?: string
  protocol?: string
}) => {
  return await request.post('/model_list_by_config', data)
}

// 编辑态：用后端库内 Fernet 密钥拉取远端模型目录，前端不接触明文 Key
export const fetchModelsBySaved = async (providerId: string) => {
  return await request.post('/model_list_saved', { provider_id: providerId })
}

export const fetchEnableModelById = async (id: string) => {
  return await request.get('/model_enable/' + id)
}

// notemeld.model-add.v1 两级协议：批量保存/默认模型/分享解码
export interface BatchModelItem {
  model_id: string
  display_name?: string
  context_window_tokens: number
  supports_vision: boolean
  supports_stream: boolean
  enabled?: number
  test_status?: string
}

export interface BatchModelsRequest {
  provider_id: string
  models: BatchModelItem[]
  default_model_id?: string | null
}

export interface BatchModelsResult {
  inserted: number
  existed: number
}

export interface DefaultModelRequest {
  provider_id: string
  model_id: string
}

export interface DecodedShareModel {
  id: string
  display_name: string
  context_window: number
}

export interface DecodedModelShare {
  vendor_id: string
  display_name: string
  protocol: string
  base_url: string
  models: DecodedShareModel[]
  imported: true
}

export const fetchEnableModels = async () => {
  return await request.get('/model_list')
}

export const deleteModelById = async (modelId: number) => {
  return await request.get(`/models/delete/${modelId}`)
}

// 按多选结果批量保存模型（幂等 upsert，按 provider_id + model_id）
export async function saveModelsBatch(data: BatchModelsRequest): Promise<BatchModelsResult> {
  return request.post('/models/batch', data)
}

// 设置供应商下的设备级默认模型
export async function setDefaultModel(data: DefaultModelRequest): Promise<void> {
  return request.post('/models/default', data)
}

// 解析 notemeld://model-add 分享文本（后端不触网、拒绝夹带 api_key 与配对码）
export async function decodeModelShare(text: string): Promise<DecodedModelShare> {
  return request.post('/model_share/decode', { text })
}
