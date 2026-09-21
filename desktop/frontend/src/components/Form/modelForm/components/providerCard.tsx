import { Switch } from '@/components/ui/switch'
import { type FC, type MouseEvent } from 'react'
import styles from './index.module.css'
import { useNavigate, useParams } from 'react-router-dom'
import AILogo from '@/components/Form/modelForm/Icons'
import { useProviderStore } from '@/store/providerStore'
import { useModelStore } from '@/store/modelStore'
import { Share2 } from 'lucide-react'
import toast from 'react-hot-toast'
import {
  buildSharePayload,
  encodeShare,
  getProtocol,
  getVendor,
} from '@/lib/modelVendorRegistry'
import type { IProvider } from '@/types'

export interface IProviderCardProps {
  provider: IProvider
}

const ProviderCard: FC<IProviderCardProps> = ({ provider }: IProviderCardProps) => {
  const { id, name: providerName, logo: Icon, enabled } = provider
  const navigate = useNavigate()
  const updateProvider = useProviderStore(state => state.updateProvider)

  const isChecked = enabled === 1

  const handleToggle = (checked: boolean) => {
    const allProviders = useProviderStore.getState().provider
    const current = allProviders.find(p => p.id === id)
    if (!current) return
    updateProvider({
      ...current,
      enabled: checked ? 1 : 0,
    })
  }

  const { id: currentId } = useParams<{ id: string }>()
  const isActive = currentId === id

  const protocolMeta = getProtocol(provider.protocol)
  const vendor = getVendor(provider.vendorId)
  const isOllama = provider.protocol === 'ollama'
  const hasKey = Boolean(provider.hasApiKey)

  // 行内分享：仅携带厂商/协议/地址与模型 id/名称/上下文，永不包含 API Key
  const loadModelsById = useModelStore(state => state.loadModelsById)
  const handleShare = async (event: MouseEvent) => {
    event.stopPropagation()
    try {
      const models = await loadModelsById(id)
      const payload = buildSharePayload({
        vendor_id: provider.vendorId,
        display_name: provider.displayName || providerName,
        protocol: provider.protocol || 'openai-compatible',
        base_url: provider.baseUrl || vendor?.base_url || '',
        models: (models ?? []).map(item => ({
          id: item.model_id || item.model_name,
          display_name: item.display_name,
          context_window: item.context_window_tokens,
        })),
      })
      const uri = encodeShare(payload)
      await navigator.clipboard.writeText(uri)
      toast.success('模型配置链接已复制（不含 API 密钥）')
    } catch {
      toast.error('生成分享链接失败')
    }
  }

  return (
    <div
      data-provider-card={id}
      className={
        styles.card +
        ' flex min-h-[56px] min-w-[178px] flex-col justify-center gap-1 rounded-xl border border-[#f3f3f3] bg-white p-2 shadow-[0_1px_8px_rgba(15,23,42,0.04)] md:min-w-0' +
        (isActive ? ' border-primary/20 bg-primary/5 font-semibold text-blue-600' : '')
      }
    >
      <div className="flex items-center justify-between gap-1">
        <div
          className="flex min-w-0 flex-1 items-center text-base md:text-lg"
          onClick={() => navigate(`/settings/model/${id}`)}
        >
          <div className="flex h-9 w-9 shrink-0 items-center">
            <AILogo name={Icon} />
          </div>
          <div className="min-w-0 truncate font-semibold">{providerName}</div>
        </div>

        <div className="flex shrink-0 items-center gap-1">
          <button
            type="button"
            data-provider-share={id}
            onClick={handleShare}
            title="复制模型配置分享链接（不含 API 密钥）"
            className="rounded p-1 text-neutral-400 hover:bg-blue-50 hover:text-blue-600"
          >
            <Share2 className="h-3.5 w-3.5" />
          </button>
          <Switch checked={isChecked} onCheckedChange={handleToggle} />
        </div>
      </div>

      {/* 协议徽标 + 已保存密钥状态 */}
      <div className="flex items-center gap-1 pl-1">
        <span
          data-provider-protocol={id}
          className="rounded bg-neutral-100 px-1.5 py-0.5 text-[10px] leading-tight text-neutral-600"
        >
          {protocolMeta?.label || provider.protocol || 'OpenAI 兼容'}
        </span>
        {isOllama ? (
          <span
            data-provider-credential={id}
            className="rounded bg-neutral-50 px-1.5 py-0.5 text-[10px] leading-tight text-neutral-400"
          >
            无需密钥
          </span>
        ) : hasKey ? (
          <span
            data-provider-credential={id}
            className="rounded bg-green-50 px-1.5 py-0.5 text-[10px] leading-tight text-green-700"
            title={provider.apiKeyMasked ? `已保存：${provider.apiKeyMasked}` : '密钥已加密保存'}
          >
            密钥已保存{provider.apiKeyMasked ? `（${provider.apiKeyMasked}）` : ''}
          </span>
        ) : (
          <span
            data-provider-credential={id}
            className="rounded bg-amber-50 px-1.5 py-0.5 text-[10px] leading-tight text-amber-700"
          >
            待填密钥
          </span>
        )}
      </div>
    </div>
  )
}
export default ProviderCard
