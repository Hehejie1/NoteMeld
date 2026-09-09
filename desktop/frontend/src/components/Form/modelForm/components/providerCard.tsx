import { Switch } from '@/components/ui/switch'
import { type FC } from 'react'
import styles from './index.module.css'
import { useNavigate, useParams } from 'react-router-dom'
import AILogo from '@/components/Form/modelForm/Icons'
import { useProviderStore } from '@/store/providerStore'

export interface IProviderCardProps {
  id: string
  providerName: string
  Icon: string
  enable: number
}

const ProviderCard: FC<IProviderCardProps> = ({
  providerName,
  Icon,
  id,
}: IProviderCardProps) => {
  const navigate = useNavigate()
  const updateProvider = useProviderStore(state => state.updateProvider)
  const enabled = useProviderStore(state => state.provider.find(p => p.id === id)?.enabled)

  const isChecked = enabled === 1

  const handleToggle = (checked: boolean) => {
    const allProviders = useProviderStore.getState().provider
    const provider = allProviders.find(p => p.id === id)
    if (!provider) return
    updateProvider({
      ...provider,
      enabled: checked ? 1 : 0,
    })
  }

  const { id: currentId } = useParams<{ id: string }>()
  const isActive = currentId === id

  return (
    <div
      className={
        styles.card +
        ' flex h-14 min-w-[178px] items-center justify-between rounded-xl border border-[#f3f3f3] bg-white p-2 shadow-[0_1px_8px_rgba(15,23,42,0.04)] md:min-w-0' +
        (isActive ? ' border-primary/20 bg-primary/5 font-semibold text-blue-600' : '')
      }
    >
      <div
        className="flex min-w-0 flex-1 items-center text-base md:text-lg"
        onClick={() => navigate(`/settings/model/${id}`)}
      >
        <div className="flex h-9 w-9 shrink-0 items-center">
          <AILogo name={Icon} />
        </div>
        <div className="min-w-0 truncate font-semibold">{providerName}</div>
      </div>

      <div className="shrink-0">
        <Switch
          checked={isChecked}
          onCheckedChange={handleToggle}
        />
      </div>
    </div>
  )
}
export default ProviderCard
