import ProviderCard from '@/components/Form/DownloaderForm/providerCard.tsx'
import { videoPlatforms } from '@/constant/note.ts'
import { getDownloaderCookie } from '@/services/downloader'
import { useEffect, useState } from 'react'

const Provider = () => {
  const [cookieConfiguredMap, setCookieConfiguredMap] = useState<Record<string, boolean>>({})
  const [cookieStatusVersion, setCookieStatusVersion] = useState(0)

  useEffect(() => {
    const refreshCookieStatus = async () => {
      const platforms = videoPlatforms.filter(provider => provider.value !== 'local')
      const entries = await Promise.all(
        platforms.map(async provider => {
          try {
            const res = await getDownloaderCookie(provider.value)
            return [provider.value, Boolean(res?.cookie?.trim())] as const
          } catch {
            return [provider.value, false] as const
          }
        }),
      )

      setCookieConfiguredMap(Object.fromEntries(entries))
    }

    refreshCookieStatus()
  }, [cookieStatusVersion])

  useEffect(() => {
    const handleCookieUpdated = () => setCookieStatusVersion(version => version + 1)

    window.addEventListener('downloader-cookie-updated', handleCookieUpdated)
    return () => window.removeEventListener('downloader-cookie-updated', handleCookieUpdated)
  }, [])

  return (
    <div className="flex flex-col gap-2">
      <div className="text-sm font-light">下载器配置</div>
      <div>
        {videoPlatforms &&
          videoPlatforms.map((provider, index) => {
            if (provider.value !== 'local')
              return (
                <ProviderCard
                  key={index}
                  providerName={provider.label}
                  Icon={provider?.logo}
                  id={provider.value}
                  cookieConfigured={cookieConfiguredMap[provider.value]}
                />
              )
          })}
      </div>
    </div>
  )
}
export default Provider
