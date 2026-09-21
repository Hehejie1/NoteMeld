import { useEffect, useMemo, useState, type FC, type MouseEvent } from 'react'
import { AlertTriangle, Globe, X } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { videoPlatforms } from '@/constant/note'
import { getDownloaderCookie } from '@/services/downloader'
import { cn } from '@/lib/utils'
import { openExternalUrl } from '@/utils/runtime'

export type LinkPlatform =
  | 'bilibili'
  | 'youtube'
  | 'douyin'
  | 'kuaishou'
  | 'wechat_channels'
  | 'web_link'

export interface PlatformCookieStatus {
  platform: LinkPlatform
  cookieMissing: boolean
}

const COOKIE_PLATFORMS = new Set<LinkPlatform>([
  'bilibili',
  'youtube',
  'douyin',
  'kuaishou',
  'wechat_channels',
])

export const platformRequiresCookie = (platform: LinkPlatform): boolean => COOKIE_PLATFORMS.has(platform)

export const getPlatformLabel = (platform: LinkPlatform): string =>
  videoPlatforms.find(item => item.value === platform)?.label || '当前平台'

export const detectPlatform = (url: string): LinkPlatform => {
  const u = url.toLowerCase()
  if (u.includes('bilibili.com') || u.includes('b23.tv')) return 'bilibili'
  if (u.includes('youtube.com') || u.includes('youtu.be')) return 'youtube'
  if (u.includes('douyin.com')) return 'douyin'
  if (u.includes('kuaishou.com')) return 'kuaishou'
  if (u.includes('channels.weixin.qq.com')) return 'wechat_channels'
  return 'web_link'
}

export const formatUrlHost = (url: string): string => {
  try {
    const parsed = new URL(url)
    return `${parsed.host}${parsed.pathname}`.replace(/\/$/, '')
  } catch {
    return url
  }
}

interface PlatformLinkCardProps {
  url: string
  onRemove?: () => void
  className?: string
  tone?: 'light' | 'primary'
  onCookieStatusChange?: (status: PlatformCookieStatus) => void
}

const PlatformLinkCard: FC<PlatformLinkCardProps> = ({
  url,
  onRemove,
  className,
  tone = 'light',
  onCookieStatusChange,
}) => {
  const navigate = useNavigate()
  const platform = useMemo(() => detectPlatform(url), [url])
  const platformInfo = videoPlatforms.find(p => p.value === platform)
  const PlatformLogo = platformInfo?.logo
  const shouldCheckCookie = platformRequiresCookie(platform)
  const [cookieMissing, setCookieMissing] = useState(false)

  useEffect(() => {
    let active = true
    if (!shouldCheckCookie) {
      setCookieMissing(false)
      return
    }

    getDownloaderCookie(platform)
      .then(res => {
        if (!active) return
        const cookie = (res as { cookie?: string } | null)?.cookie
        setCookieMissing(!cookie)
      })
      .catch(() => {
        if (active) setCookieMissing(true)
      })

    return () => {
      active = false
    }
  }, [platform, shouldCheckCookie])

  useEffect(() => {
    onCookieStatusChange?.({
      platform,
      cookieMissing: shouldCheckCookie ? cookieMissing : false,
    })
  }, [cookieMissing, onCookieStatusChange, platform, shouldCheckCookie])

  const openCookieSettings = (event: MouseEvent<HTMLButtonElement>) => {
    event.preventDefault()
    event.stopPropagation()
    navigate(`/settings/download/${platform}`)
  }

  const removeLink = (event: MouseEvent<HTMLButtonElement>) => {
    event.preventDefault()
    event.stopPropagation()
    onRemove?.()
  }

  const openLink = (event: MouseEvent<HTMLAnchorElement>) => {
    event.preventDefault()
    event.stopPropagation()
    openExternalUrl(url).catch(error => {
      console.warn('failed to open platform link', error)
    })
  }

  const primaryTone = tone === 'primary'

  return (
    <span className={cn('group/linkcard inline-flex min-w-0 max-w-full items-center gap-1.5', className)}>
      {onRemove && (
        <button
          type="button"
          onClick={removeLink}
          className={cn(
            'flex h-5 w-5 shrink-0 items-center justify-center rounded-full opacity-0 shadow-sm transition-all group-hover/linkcard:opacity-100',
            primaryTone
              ? 'bg-white/20 text-white hover:bg-white/30'
              : 'bg-white text-on-surface-variant ring-1 ring-border-subtle hover:bg-destructive hover:text-white hover:ring-destructive',
          )}
          aria-label="删除链接"
        >
          <X className="h-3 w-3" />
        </button>
      )}
      <span
        className={cn(
          'inline-flex min-w-0 max-w-full items-center gap-2 overflow-hidden rounded-xl px-2.5 py-1.5 text-[12px] transition-all',
          primaryTone
            ? 'bg-white/15 text-white hover:bg-white/20'
            : 'border border-border-subtle bg-surface-container-low text-on-surface shadow-[0_1px_4px_rgba(15,23,42,0.04)] hover:border-primary/25 hover:bg-white hover:shadow-[0_6px_18px_rgba(15,23,42,0.08)]',
        )}
      >
        {cookieMissing ? (
          <button
            type="button"
            onClick={openCookieSettings}
            title={`未设置${getPlatformLabel(platform)} Cookie，点击去设置`}
            className={cn(
              'flex h-5 w-5 shrink-0 items-center justify-center rounded-full transition-colors',
              primaryTone
                ? 'bg-amber-300 text-amber-950 hover:bg-amber-200'
                : 'bg-amber-100 text-amber-700 hover:bg-amber-200',
            )}
          >
            <AlertTriangle className="h-3.5 w-3.5" />
          </button>
        ) : PlatformLogo ? (
          <a
            href={url}
            onClick={openLink}
            rel="noopener noreferrer"
            className="flex h-5 w-5 shrink-0 items-center justify-center overflow-hidden rounded-md [&>svg]:h-5 [&>svg]:w-5"
          >
            <PlatformLogo />
          </a>
        ) : (
          <a
            href={url}
            onClick={openLink}
            rel="noopener noreferrer"
            className={cn(
              'flex h-5 w-5 shrink-0 items-center justify-center rounded-md',
              primaryTone ? 'bg-white/15 text-white' : 'bg-primary/10 text-primary',
            )}
          >
            <Globe className="h-3.5 w-3.5" />
          </a>
        )}
        <a
          href={url}
          onClick={openLink}
          rel="noopener noreferrer"
          className={cn(
            'shrink-0 rounded-md px-1.5 py-0.5 font-mono text-[10px] font-semibold uppercase tracking-wide transition-colors',
            primaryTone ? 'bg-white/15 text-white' : 'bg-primary/10 text-primary',
          )}
        >
          {platformInfo?.label || '链接'}
        </a>
        <a
          href={url}
          onClick={openLink}
          rel="noopener noreferrer"
          className="min-w-0 flex-1 truncate font-mono text-[11px]"
        >
          {formatUrlHost(url)}
        </a>
      </span>
    </span>
  )
}

export default PlatformLinkCard
