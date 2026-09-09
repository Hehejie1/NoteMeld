import { type ComponentType } from 'react'
import styles from './index.module.css'
import { useNavigate, useParams } from 'react-router-dom'
import { Badge } from '@/components/ui/badge'
export interface IProviderCardProps {
  id: string
  providerName: string
  Icon: ComponentType
  cookieConfigured?: boolean
}
const ProviderCard = ({
  providerName,
  Icon,
  id,
  cookieConfigured,
}: IProviderCardProps) => {
  const navigate = useNavigate()
  const handleClick = () => {
    navigate(`/settings/download/${id}`)
  }

  const { id: currentId } = useParams<{ id: string }>()
  const isActive = currentId === id
  return (
    <div
      onClick={() => {
        handleClick()
      }}
      className={
        styles.card +
        ' flex h-14 items-center justify-between rounded border border-[#f3f3f3] p-2' +
        (isActive ? ' bg-[#F0F0F0] font-semibold text-blue-600' : '')
      }
    >
      <div className="flex min-w-0 items-center gap-2 text-lg">
        <div className="flex h-6 w-6 items-center">{<Icon></Icon>}</div>
        <div className="truncate font-semibold">{providerName}</div>
      </div>
      {cookieConfigured && (
        <Badge
          variant="outline"
          className="ml-2 border-emerald-200 bg-emerald-50 px-1.5 py-0 text-[11px] font-medium text-emerald-700"
        >
          已设置
        </Badge>
      )}
    </div>
  )
}
export default ProviderCard
