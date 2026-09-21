import { create } from 'zustand'
import { IProvider, IResponse } from '@/types'
import {
  addProvider,
  getProviderById,
  getProviderList,
  updateProviderById,
} from '@/services/model.ts'

interface ProviderStore {
  provider: IProvider[]
  setProvider: (provider: IProvider) => void
  setAllProviders: (providers: IProvider[]) => void
  getProviderById: (id: number) => IProvider | undefined
  getProviderList: () => IProvider[]
  fetchProviderList: () => Promise<void>
  loadProviderById: (id: string) => Promise<IProvider>
  addNewProvider: (provider: IProvider) => Promise<IProvider | undefined>
  updateProvider: (provider: IProvider) => Promise<void>
}

type ProviderRaw = {
  id: string
  name: string
  logo: string
  enabled: number
  // 安全出口字段（notemeld.model-add.v1）
  base_url?: string
  display_name?: string
  vendor_id?: string
  protocol?: string
  auth_type?: string
  has_api_key?: boolean
  credential_status?: string
  api_key_masked?: string
  created_at?: string
  // 旧字段兜底
  api_key?: string
  baseUrl?: string
  displayName?: string
  vendorId?: string
  authType?: string
  hasApiKey?: boolean
}

const normalizeProvider = (item: ProviderRaw): IProvider => ({
  id: item.id,
  name: item.name,
  logo: item.logo,
  // HTTP 安全出口不再回显明文；保留旧字段读取兜底一版
  apiKey: item.api_key,
  baseUrl: item.base_url ?? item.baseUrl ?? '',
  enabled: item.enabled,
  displayName: item.display_name ?? item.displayName ?? item.name,
  vendorId: item.vendor_id ?? item.vendorId ?? 'custom',
  protocol: item.protocol ?? 'openai-compatible',
  authType: item.auth_type ?? item.authType ?? 'api_key',
  hasApiKey: item.has_api_key ?? item.hasApiKey ?? Boolean(item.api_key),
  credentialStatus: item.credential_status,
  apiKeyMasked: item.api_key_masked,
  createdAt: item.created_at,
})

export const useProviderStore = create<ProviderStore>((set, get) => ({
  provider: [],

  // 添加或更新一个 provider
  setProvider: newProvider =>
    set(state => {
      const exists = state.provider.find(p => p.id === newProvider.id)
      if (exists) {
        return {
          provider: state.provider.map(p => (p.id === newProvider.id ? newProvider : p)),
        }
      } else {
        return { provider: [...state.provider, newProvider] }
      }
    }),

  // 设置整个 provider 列表
  setAllProviders: providers => set({ provider: providers }),
  loadProviderById: async (id: string) => {
    const res:IResponse<IProvider> = await getProviderById(id)

      const item = res
      return normalizeProvider(item as unknown as ProviderRaw)

  },
  addNewProvider: async (provider: IProvider) => {
    const payload = {
      ...provider,
      api_key: provider.apiKey,
      base_url: provider.baseUrl,
    }
    try {
      const res = await addProvider(payload)
      const item = normalizeProvider(res as ProviderRaw)
      await get().fetchProviderList()
      return item
    } catch (error) {
      console.error('Error fetching provider:', error)
    }
  },
  // 按 id 获取单个 provider
  getProviderById: id => get().provider.find(p => p.id === id),
  updateProvider: async (provider: IProvider) => {
    try {
      const existing = get().provider.find(p => p.id === provider.id)
      const merged = { ...existing, ...provider }

      const data = {
        ...merged,
        api_key: merged.apiKey,
        base_url: merged.baseUrl,
      }
      // 拦截器已解包：成功时直接返回 data 部分
      await updateProviderById(data)
      await get().fetchProviderList()
    } catch (error) {
      console.error('Error updating provider:', error)
    }
  },
  getProviderList: () => get().provider,
  fetchProviderList: async () => {
    try {
      const res  = await getProviderList()

        set({
          provider: res.map(normalizeProvider),
        })
    } catch (error) {
      console.error('Error fetching provider list:', error)
    }
  },
}))
