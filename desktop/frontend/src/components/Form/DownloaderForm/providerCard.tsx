import { type ComponentType } from 'react'
import { NavLink } from 'react-router-dom'
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
  return (
    <NavLink
      to={`/settings/download/${id}`}
      className={({ isActive }) => [
        'flex h-14 min-w-0 items-center justify-between rounded-md border p-2 no-underline transition-colors',
        'focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary',
        isActive
          ? 'border-primary/30 bg-primary/10 font-semibold text-primary'
          : 'border-border-subtle bg-surface-container-lowest text-on-surface-variant hover:bg-surface-container-low hover:text-on-surface',
      ].join(' ')}
    >
      <div className="flex min-w-0 items-center gap-2 text-lg">
        <div className="flex h-6 w-6 items-center">{<Icon></Icon>}</div>
        <div className="truncate font-semibold">{providerName}</div>
      </div>
      {cookieConfigured && (
        <Badge
          variant="outline"
          className="ml-2 shrink-0 border-border-subtle bg-surface-container-low px-1.5 py-0 text-[11px] font-medium text-on-surface-variant"
        >
          已设置
        </Badge>
      )}
    </NavLink>
  )
}
export default ProviderCard
