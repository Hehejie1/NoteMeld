import { useEffect, useRef, useState } from 'react'
import { toast } from 'sonner'
import { CheckCircle2, Download, Loader2, RefreshCw } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { ScrollArea } from '@/components/ui/scroll-area'
import {
  checkDesktopUpdate,
  DesktopUpdateCheckResult,
  installPendingDesktopUpdate,
} from '@/services/desktopUpdater'
import { isDesktopEmbedded } from '@/utils/runtime'

const fallbackVersion = '0.0.4'
const defaultReleaseNotes = `每次升级的内容

- 优化桌面端更新体验
- 保留本地知识库、缓存、模型和配置
- 改进 NoteMeld 知识工作台的稳定性`

function formatProgress(downloaded?: number, total?: number): string {
  if (!downloaded && !total) {
    return ''
  }

  if (!total) {
    return `已下载 ${Math.round((downloaded || 0) / 1024 / 1024)} MB`
  }

  return `${Math.round(((downloaded || 0) / total) * 100)}%`
}

async function readAppVersion(): Promise<string> {
  if (!isDesktopEmbedded()) {
    return fallbackVersion
  }

  try {
    const { getVersion } = await import('@tauri-apps/api/app')
    return await getVersion()
  } catch {
    return fallbackVersion
  }
}

export default function AboutPage() {
  const [version, setVersion] = useState(fallbackVersion)
  const [checking, setChecking] = useState(false)
  const [installing, setInstalling] = useState(false)
  const [result, setResult] = useState<DesktopUpdateCheckResult | null>(null)
  const [progress, setProgress] = useState('')
  const [progressPercent, setProgressPercent] = useState(0)
  const totalDownloadRef = useRef<number | undefined>(undefined)

  useEffect(() => {
    readAppVersion().then(setVersion)
  }, [])

  const handleCheck = async () => {
    try {
      setChecking(true)
      setProgress('')
      setProgressPercent(0)
      const nextResult = await checkDesktopUpdate()
      setResult(nextResult)
      if (nextResult.status === 'available') {
        toast.success(`发现新版本 ${nextResult.version}`)
      } else {
        toast.success(nextResult.message)
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : '检查更新失败'
      setResult(null)
      toast.error(message)
    } finally {
      setChecking(false)
    }
  }

  const handleInstall = async () => {
    try {
      setInstalling(true)
      setProgress('准备下载更新包')
      setProgressPercent(0)
      await installPendingDesktopUpdate(event => {
        if (event.phase === 'started') {
          totalDownloadRef.current = event.total
          setProgress('开始下载更新包')
          return
        }
        if (event.phase === 'progress') {
          const total = event.total || totalDownloadRef.current
          const percent = total ? Math.min(100, Math.round(((event.downloaded || 0) / total) * 100)) : 0
          setProgressPercent(percent)
          setProgress(formatProgress(event.downloaded, total) || '正在下载更新包')
          return
        }
        setProgressPercent(100)
        setProgress('下载完成，正在重启安装')
      })
    } catch (error) {
      const message = error instanceof Error ? error.message : '安装更新失败'
      toast.error(message)
      setInstalling(false)
    }
  }

  const hasUpdate = result?.status === 'available'
  const isLatest = result?.status === 'latest'
  const releaseNotes = hasUpdate ? result.body?.trim() || defaultReleaseNotes : defaultReleaseNotes

  return (
    <ScrollArea className="h-full overflow-y-auto bg-[#f5f5f7]">
      <div className="px-6 py-6">
        <h1 className="text-[28px] font-bold tracking-tight text-on-surface">关于</h1>
      </div>

      <div className="mx-auto flex w-full max-w-[860px] flex-col items-center px-8 pb-16 pt-4">
        <div className="flex h-24 w-24 items-center justify-center overflow-hidden rounded-[24px] bg-[#0e0d2a] shadow-sm">
          <img src="/notemeld-logo.png" alt="NoteMeld" className="h-full w-full object-contain" />
        </div>

        <h2 className="mt-5 font-display text-[32px] font-bold leading-none text-on-surface">
          NoteMeld
        </h2>
        <div className="mt-2 font-mono text-[15px] text-on-surface-variant">v{version}</div>
        <p className="mt-3 text-center text-sm text-on-surface-variant">
          More Than Notes，本地优先的 AI 知识工作台。
        </p>

        {!result && !checking && !installing && (
          <button
            type="button"
            onClick={handleCheck}
            className="mt-8 flex h-14 w-full max-w-[760px] items-center gap-4 rounded-2xl bg-white px-7 text-left text-[17px] font-medium text-on-surface shadow-sm transition-colors hover:bg-surface-container"
          >
            <RefreshCw className="h-5 w-5 text-on-surface-variant" />
            检查更新
          </button>
        )}

        {checking && (
          <div className="mt-8 flex h-14 w-full max-w-[760px] items-center gap-4 rounded-2xl bg-white px-7 text-[17px] font-medium text-on-surface shadow-sm">
            <Loader2 className="h-5 w-5 animate-spin text-primary" />
            正在检查更新
          </div>
        )}

        {isLatest && (
          <div className="mt-8 flex h-14 w-full max-w-[760px] items-center gap-4 rounded-2xl bg-white px-7 text-[17px] font-medium text-on-surface shadow-sm">
            <CheckCircle2 className="h-5 w-5 text-green-600" />
            已经是最新版本
          </div>
        )}

        {hasUpdate && !installing && (
          <>
            <div className="mt-5 rounded-full bg-white px-6 py-3 text-[17px] shadow-sm">
              <span className="font-mono text-on-surface-variant">{version}</span>
              <span className="mx-3 text-on-surface-variant">→</span>
              <span className="font-mono font-semibold text-on-surface">{result.version}</span>
            </div>

            <div className="mt-5 w-full max-w-[860px] rounded-2xl bg-white p-5 shadow-sm">
              <div className="mb-4 text-[15px] font-semibold text-on-surface">更新已就绪</div>
              <div className="max-h-[210px] overflow-y-auto rounded-2xl border border-border-subtle/70 bg-white px-5 py-4 text-sm leading-7 text-on-surface">
                <div className="whitespace-pre-wrap">{releaseNotes}</div>
              </div>
            </div>

            <Button className="mt-4 h-11 min-w-[180px] rounded-xl text-[15px]" onClick={handleInstall}>
              <Download className="mr-2 h-4 w-4" />
              立即更新
            </Button>
          </>
        )}

        {installing && (
          <div className="mt-8 w-full max-w-[810px] rounded-2xl bg-white px-6 py-5 shadow-sm">
            <div className="mb-5 flex items-center gap-3 text-[15px] font-semibold text-on-surface">
              <Download className="h-4 w-4 text-primary" />
              正在下载更新
            </div>
            <div className="mb-4 text-center text-[17px]">
              <span className="font-mono text-on-surface-variant">{version}</span>
              <span className="mx-3 text-on-surface-variant">→</span>
              <span className="font-mono font-semibold text-on-surface">
                {hasUpdate ? result.version : version}
              </span>
            </div>
            <div className="h-1.5 overflow-hidden rounded-full bg-surface-container">
              <div
                className="h-full rounded-full bg-primary transition-all duration-300"
                style={{ width: `${progressPercent}%` }}
              />
            </div>
            <div className="mt-3 text-center text-sm text-on-surface-variant">
              {progress || `下载中... ${progressPercent}%`}
            </div>
          </div>
        )}
      </div>
    </ScrollArea>
  )
}
