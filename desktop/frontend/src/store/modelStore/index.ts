import { create } from 'zustand'
import { devtools } from 'zustand/middleware'
import {
  fetchModels,
  fetchEnableModels,
  fetchEnableModelById,
  deleteModelById,
  saveModelsBatch,
  setDefaultModel,
  type BatchModelsRequest,
  type BatchModelsResult,
} from '@/services/model'

interface IModel {
  id: string
  created: number
  object: string
  owned_by: string
  permission: string
  root: string
}

export interface IModelListItem {
  id: number
  provider_id: string
  model_name: string
  context_window_tokens: number
  max_input_tokens: number
  max_output_tokens: number
  supports_vision: boolean
  supports_stream: boolean
  created_at?: string
  // notemeld.model-add.v1 两级协议新增字段
  model_id?: string
  display_name?: string
  enabled?: number
  is_default?: number
  test_status?: string
  capabilities?: Record<string, unknown>
}

interface ModelStore {
  models: IModel[]
  modelList: IModelListItem[]
  loading: boolean
  selectedModel: string

  loadModels: (providerId: string) => Promise<void>
  loadModelsById: (providerId: string) => Promise<IModelListItem[]>
  loadEnabledModels: () => Promise<void>
  saveModels: (data: BatchModelsRequest) => Promise<BatchModelsResult>
  setModelDefault: (providerId: string, modelId: string) => Promise<void>
  deleteModel: (modelId: number) => Promise<void>
  setSelectedModel: (modelId: string) => void
  clearModels: () => void
}

export const useModelStore = create<ModelStore>()(
  devtools((set) => ({
    models: [],
    modelList: [],
    loading: false,
    selectedModel: '',

    //  获取所有可用模型 (全局可用模型列表)
    loadEnabledModels: async () => {
      try {
        set({ loading: true })
        const list = await fetchEnableModels()
        set({ modelList: list })
      } catch (error) {
        set({ modelList: [] })
        console.error('加载可用模型失败', error)
      } finally {
        set({ loading: false })
      }
    },

    //  通过 provider 获取该供应商的模型列表
    loadModels: async (providerId: string) => {
      try {
        set({ loading: true })
        const res = await fetchModels(providerId)

        let models: IModel[] = []

        // 兼容 SyncPage 分页对象与普通数组两种格式
        if (Array.isArray(res.models)) {
          models = res.models
        } else if (res.models?.data && Array.isArray(res.models.data)) {
          models = res.models.data
        }

        set({ models })
      } catch (error) {
        set({ models: [] })
        console.error('加载模型列表失败', error)
      } finally {
        set({ loading: false })
      }
    },

    //  单独获取某个供应商下已启用模型
    loadModelsById: async (providerId: string) => {
      try {
        const models = await fetchEnableModelById(providerId)
        return models
      } catch (error) {
        console.error('加载供应商模型失败', error)
        return []
      }
    },

    //  批量保存多选模型（notemeld.model-add.v1）
    saveModels: async (data) => (await saveModelsBatch(data)) as BatchModelsResult,

    //  设置供应商默认模型
    setModelDefault: async (providerId, modelId) => {
      await setDefaultModel({ provider_id: providerId, model_id: modelId })
    },

    //  删除模型
    deleteModel: async (modelId: number) => {
      try {
        await deleteModelById(modelId)
        //  删除后更新本地状态（可选）
        set((state) => ({
          models: state.models.filter((model) => model.id !== modelId.toString())
        }))
      } catch (error) {
        console.error('删除模型失败', error)
      }
    },

    //  切换选中模型
    setSelectedModel: (modelId: string) => set({ selectedModel: modelId }),

    //  清空
    clearModels: () => set({ models: [], selectedModel: '', modelList: [] }),
  }))
)
