import { useCallback, useEffect, useMemo, useRef, useState, type ChangeEvent, type DragEvent, type KeyboardEvent } from 'react'
import { Database, Loader2, PackageOpen, RefreshCw, Upload } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Checkbox } from '@/components/ui/checkbox'
import { Label } from '@/components/ui/label'
import {
  startMigrationExport,
  startMigrationImport,
  getMigrationJob,
  getMigrationPackageDownloadUrl,
  uploadMigrationPackage,
  rebuildMigrationIndexes,
  type MigrationJobPayload,
} from '@/services/migration'
import { selectMigrationPackagePath, selectExportPackagePath, canUseNativeFileDialog, preloadDesktopFileDialog } from '@/utils/fileDialog'
import { useTaskStore } from '@/store/taskStore'

const MIGRATION_POLL_INTERVAL_MS = 1500
const ACTIVE_MIGRATION_JOB_STATUSES = new Set(['pending', 'running'])

function shouldPollMigrationJob(status?: string): boolean {
  return ACTIVE_MIGRATION_JOB_STATUSES.has(String(status || '').trim().toLowerCase())
}

function buildDefaultPackageName(): string {
  return `migration-${new Date().toISOString().slice(0, 19).replace(/[:T]/g, '-')}`
}

function buildDefaultExportFileName(): string {
  return `${buildDefaultPackageName()}.zip`
}

function ensureZipPath(path: string): string {
  const trimmedPath = path.trim()
  return isZipPath(trimmedPath) ? trimmedPath : `${trimmedPath}.zip`
}

function isZipPath(path: string): boolean {
  return /\.zip$/i.test(path.trim())
}

function fileNameFromPath(path: string): string {
  return path.split(/[\\/]/).pop() || path
}

function packageNameFromPath(path: string): string | undefined {
  const fileName = fileNameFromPath(path).replace(/\.zip$/i, '').trim()
  return fileName || undefined
}

function pathFromDroppedFile(file: File): string {
  const fileWithPath = file as File & { path?: string }
  return typeof fileWithPath.path === 'string' ? fileWithPath.path : ''
}

function jobStatusLabel(status?: string): string {
  switch (String(status || '').trim().toLowerCase()) {
    case 'completed':
      return '已完成'
    case 'failed':
      return '失败'
    case 'running':
      return '进行中'
    default:
      return '等待中'
  }
}

function jobStatusVariant(status?: string): 'default' | 'secondary' | 'destructive' | 'outline' {
  switch (String(status || '').trim().toLowerCase()) {
    case 'completed':
      return 'default'
    case 'failed':
      return 'destructive'
    case 'running':
      return 'secondary'
    default:
      return 'outline'
  }
}

function isStoragePressureMessage(message?: string): boolean {
  return /存储空间不足|磁盘空间不足|内存不足|释放磁盘空间|清除缓存/.test(String(message || ''))
}

function showStoragePressureAlert(message?: string): void {
  window.alert(
    message
      || '导入迁移包失败：当前系统存储空间或内存不足。建议清除缓存、释放磁盘空间后再重新导入。',
  )
}

export default function DataMigration() {
  const [importPath, setImportPath] = useState('')
  const [rebuildAfterImport, setRebuildAfterImport] = useState(true)
  const [jobId, setJobId] = useState('')
  const [job, setJob] = useState<MigrationJobPayload | null>(null)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [localMessage, setLocalMessage] = useState('')
  const [manualReindexRunning, setManualReindexRunning] = useState(false)
  const [pendingBrowserDownloadJobId, setPendingBrowserDownloadJobId] = useState('')
  const [browserImportFile, setBrowserImportFile] = useState<File | null>(null)
  const importDropZoneRef = useRef<HTMLDivElement | null>(null)
  const browserImportInputRef = useRef<HTMLInputElement | null>(null)
  const isTauriDraggingOverImportRef = useRef(false)
  const lastStorageAlertJobIdRef = useRef('')
  const lastImportedJobRefreshRef = useRef('')
  const loadConversations = useTaskStore(state => state.loadConversations)

  const supportsNativeFileDialog = canUseNativeFileDialog()
  const importPathLooksLikeArchive = useMemo(() => isZipPath(importPath), [importPath])

  const pollMigrationJob = useCallback(async (targetJobId: string) => {
    const nextJob = await getMigrationJob(targetJobId)
    setJob(nextJob)
    if (nextJob.job_id) {
      setJobId(nextJob.job_id)
    }
  }, [])

  useEffect(() => {
    preloadDesktopFileDialog()
  }, [])

  useEffect(() => {
    if (!jobId || !shouldPollMigrationJob(job?.status)) {
      return
    }

    const timer = window.setInterval(() => {
      void pollMigrationJob(jobId)
    }, MIGRATION_POLL_INTERVAL_MS)

    return () => window.clearInterval(timer)
  }, [job?.status, jobId, pollMigrationJob])

  useEffect(() => {
    if (!supportsNativeFileDialog) {
      return
    }

    let disposed = false
    let cleanup: (() => void) | undefined

    void import('@tauri-apps/api/webview')
      .then(async ({ getCurrentWebview }) => {
        cleanup = await getCurrentWebview().onDragDropEvent(event => {
          if (disposed) {
            return
          }

          const payload = event.payload
          if (payload.type === 'over') {
            const rect = importDropZoneRef.current?.getBoundingClientRect()
            isTauriDraggingOverImportRef.current = Boolean(
              rect &&
                payload.position.x >= rect.left &&
                payload.position.x <= rect.right &&
                payload.position.y >= rect.top &&
                payload.position.y <= rect.bottom
            )
            return
          }

          if (payload.type === 'drop') {
            const [path] = payload.paths
            if (isTauriDraggingOverImportRef.current && path) {
              if (isZipPath(path)) {
                setImportPath(path)
                setLocalMessage('')
              } else {
                setLocalMessage('当前仅支持导入 .zip 迁移包。')
              }
            }
            isTauriDraggingOverImportRef.current = false
            return
          }

          isTauriDraggingOverImportRef.current = false
        })
      })
      .catch(() => {
        cleanup = undefined
      })

    return () => {
      disposed = true
      cleanup?.()
    }
  }, [supportsNativeFileDialog])

  useEffect(() => {
    if (!pendingBrowserDownloadJobId || job?.job_id !== pendingBrowserDownloadJobId) {
      return
    }

    const status = String(job.status || '').trim().toLowerCase()
    if (status === 'completed') {
      setPendingBrowserDownloadJobId('')
      const link = document.createElement('a')
      link.href = getMigrationPackageDownloadUrl(pendingBrowserDownloadJobId)
      link.download = ''
      link.style.display = 'none'
      document.body.appendChild(link)
      link.click()
      document.body.removeChild(link)
      setLocalMessage('导出任务已完成，浏览器下载已开始。')
      return
    }

    if (status === 'failed') {
      setPendingBrowserDownloadJobId('')
    }
  }, [job, pendingBrowserDownloadJobId])

  useEffect(() => {
    if (!job) {
      return
    }
    if (
      String(job.status || '').trim().toLowerCase() !== 'failed'
      || !isStoragePressureMessage(job.error)
      || lastStorageAlertJobIdRef.current === job.job_id
    ) {
      return
    }

    lastStorageAlertJobIdRef.current = job.job_id
    showStoragePressureAlert(job.error)
  }, [job, job?.error, job?.job_id, job?.status])

  useEffect(() => {
    if (
      !job
      || String(job.status || '').trim().toLowerCase() !== 'completed'
      || !String(job.job_id || '').startsWith('migration-import-')
      || lastImportedJobRefreshRef.current === job.job_id
    ) {
      return
    }

    lastImportedJobRefreshRef.current = job.job_id
    loadConversations()
      .then(() => {
        setLocalMessage('导入任务已完成，笔记列表已刷新。')
      })
      .catch(error => {
        console.error('导入完成后刷新笔记列表失败', error)
        setLocalMessage('导入任务已完成，但刷新笔记列表失败，请手动刷新页面。')
      })
  }, [job, loadConversations])

  const handleSelectMigrationPackage = useCallback(async () => {
    if (!supportsNativeFileDialog) {
      browserImportInputRef.current?.click()
      return
    }

    const path = await selectMigrationPackagePath()
    if (path) {
      setImportPath(path)
      setBrowserImportFile(null)
      setLocalMessage('')
    }
  }, [supportsNativeFileDialog])

  const acceptBrowserImportFile = useCallback((file: File) => {
    if (!isZipPath(file.name)) {
      setLocalMessage('当前仅支持导入 .zip 迁移包。')
      return
    }

    setBrowserImportFile(file)
    setImportPath(file.name)
    setLocalMessage('')
  }, [])

  const handleBrowserImportFileChange = useCallback((event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]
    event.target.value = ''
    if (file) {
      acceptBrowserImportFile(file)
    }
  }, [acceptBrowserImportFile])

  const handleDropMigrationPackage = useCallback((event: DragEvent<HTMLDivElement>) => {
    event.preventDefault()
    event.stopPropagation()

    const file = event.dataTransfer.files?.[0]
    if (!file) {
      return
    }
    if (!isZipPath(file.name)) {
      setLocalMessage('当前仅支持导入 .zip 迁移包。')
      return
    }

    if (!supportsNativeFileDialog) {
      acceptBrowserImportFile(file)
      return
    }

    const droppedPath = pathFromDroppedFile(file)
    if (!droppedPath) {
      setLocalMessage('未读取到拖拽文件的系统路径，请点击选择 zip 迁移包。')
      return
    }

    setImportPath(droppedPath)
    setBrowserImportFile(null)
    setLocalMessage('')
  }, [acceptBrowserImportFile, supportsNativeFileDialog])

  const handleImportDropZoneKeyDown = useCallback((event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault()
      void handleSelectMigrationPackage()
    }
  }, [handleSelectMigrationPackage])

  const handleStartExport = useCallback(async () => {
    let targetPath = ''
    let packageName = buildDefaultPackageName()

    if (supportsNativeFileDialog) {
      const selectedPath = await selectExportPackagePath(buildDefaultExportFileName())
      if (!selectedPath) {
        setLocalMessage('已取消导出。')
        return
      }
      targetPath = ensureZipPath(selectedPath)
      packageName = packageNameFromPath(targetPath) || packageName
    }

    setIsSubmitting(true)
    setLocalMessage('')
    try {
      const nextJob = await startMigrationExport({
        package_name: packageName,
        target_path: targetPath || undefined,
      })
      setJob(nextJob)
      setJobId(nextJob.job_id)
      if (supportsNativeFileDialog) {
        setLocalMessage('导出任务已启动，产物将写入您选择的位置。')
      } else {
        setPendingBrowserDownloadJobId(nextJob.job_id)
        setLocalMessage('导出任务已启动，完成后会自动触发浏览器下载。')
      }
    } catch {
      setLocalMessage('启动导出任务失败，请检查后端是否可用。')
    } finally {
      setIsSubmitting(false)
    }
  }, [supportsNativeFileDialog])

  const handleStartImport = useCallback(async () => {
    if (!importPath.trim() && !browserImportFile) {
      setLocalMessage('请先拖拽或选择 zip 迁移包。')
      return
    }
    if (browserImportFile && !isZipPath(browserImportFile.name)) {
      setLocalMessage('当前仅支持导入 .zip 迁移包。')
      return
    }
    if (!browserImportFile && !importPathLooksLikeArchive) {
      setLocalMessage('当前仅支持导入 .zip 迁移包。')
      return
    }

    setIsSubmitting(true)
    setLocalMessage('')
    try {
      const packagePath = browserImportFile
        ? (await uploadMigrationPackage(browserImportFile)).package_path
        : importPath.trim()
      const nextJob = await startMigrationImport({
        package_path: packagePath,
        rebuild_indexes: rebuildAfterImport,
      })
      setJob(nextJob)
      setJobId(nextJob.job_id)
      setLocalMessage('导入任务已启动，页面会自动轮询进度。')
    } catch (error) {
      const message = String((error as { msg?: string })?.msg || '')
      if (isStoragePressureMessage(message)) {
        showStoragePressureAlert(message)
      }
      setLocalMessage(message || '启动导入任务失败，请检查路径和后端状态。')
    } finally {
      setIsSubmitting(false)
    }
  }, [browserImportFile, importPath, importPathLooksLikeArchive, rebuildAfterImport])

  const handleRefreshJob = useCallback(async () => {
    if (!jobId) {
      setLocalMessage('当前没有可刷新的迁移任务。')
      return
    }
    try {
      await pollMigrationJob(jobId)
      setLocalMessage('')
    } catch {
      setLocalMessage('刷新迁移任务状态失败。')
    }
  }, [jobId, pollMigrationJob])

  const handleManualReindex = useCallback(async () => {
    setManualReindexRunning(true)
    setLocalMessage('')
    try {
      await rebuildMigrationIndexes({ task_ids: [] })
      setLocalMessage('索引重建入口已触发。')
    } catch {
      setLocalMessage('触发索引重建失败。')
    } finally {
      setManualReindexRunning(false)
    }
  }, [])

  const latestEvent = job?.events?.length ? job.events[job.events.length - 1] : null
  const shouldShowJobError = String(job?.status || '').trim().toLowerCase() === 'failed' && job?.error

  return (
    <div className="h-full overflow-y-auto bg-white">
      <div className="mx-auto flex max-w-5xl flex-col gap-6 px-4 py-8">
        <div className="space-y-2">
          <h1 className="text-2xl font-bold">数据与迁移</h1>
          <p className="text-muted-foreground text-sm">支持导出 zip 迁移包、导入 zip 迁移包，并轮询后端迁移进度。</p>
          {!supportsNativeFileDialog && (
            <p className="text-muted-foreground text-sm">
              当前为浏览器模式：导出完成后会触发普通下载，导入仍需使用桌面端选择或拖拽本地 zip。
            </p>
          )}
        </div>

        <div className="grid gap-6 lg:grid-cols-2">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Database className="h-5 w-5 text-primary" />
                导出整库
              </CardTitle>
              <CardDescription>
                桌面端会打开系统保存弹窗；浏览器端会在导出完成后触发普通下载。
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="rounded-lg border border-dashed border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-600">
                {supportsNativeFileDialog
                  ? '系统会先弹出保存窗口，您可以选择保存目录，并在窗口顶部直接修改迁移包名称。'
                  : '浏览器无法直接写入任意系统路径；系统会先导出迁移包，完成后自动触发浏览器下载。'}
              </div>
              <Button onClick={() => void handleStartExport()} disabled={isSubmitting}>
                {isSubmitting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Upload className="h-4 w-4" />}
                {supportsNativeFileDialog ? '选择保存位置并导出' : '导出并下载'}
              </Button>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <PackageOpen className="h-5 w-5 text-primary" />
                导入迁移包
              </CardTitle>
              <CardDescription>
                支持拖拽 zip 迁移包到卡片内，或点击打开系统文件选择弹窗。
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div
                ref={importDropZoneRef}
                role="button"
                tabIndex={0}
                onClick={() => void handleSelectMigrationPackage()}
                onKeyDown={handleImportDropZoneKeyDown}
                onDragOver={event => {
                  event.preventDefault()
                  event.stopPropagation()
                }}
                onDrop={handleDropMigrationPackage}
                className="cursor-pointer rounded-xl border border-dashed border-slate-300 bg-slate-50 px-4 py-8 text-center transition-colors hover:border-primary hover:bg-primary/5"
              >
                <PackageOpen className="mx-auto mb-3 h-8 w-8 text-primary" />
                <div className="font-medium text-slate-800">
                  {importPath ? fileNameFromPath(importPath) : '拖拽 zip 迁移包到这里'}
                </div>
                <div className="mt-1 text-xs text-slate-500">
                  {importPath ? importPath : '或点击此区域选择 zip 文件'}
                </div>
              </div>
              <input
                ref={browserImportInputRef}
                type="file"
                accept=".zip,application/zip"
                className="hidden"
                onChange={handleBrowserImportFileChange}
              />
              <div className="flex items-center gap-3">
                <Checkbox
                  id="migration-rebuild-indexes"
                  checked={rebuildAfterImport}
                  onCheckedChange={checked => setRebuildAfterImport(Boolean(checked))}
                />
                <Label htmlFor="migration-rebuild-indexes">导入完成后自动重建索引</Label>
              </div>
              <Button onClick={() => void handleStartImport()} disabled={isSubmitting}>
                {isSubmitting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Upload className="h-4 w-4" />}
                开始导入
              </Button>
            </CardContent>
          </Card>
        </div>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <RefreshCw className="h-5 w-5 text-primary" />
              任务进度
            </CardTitle>
            <CardDescription>轮询展示当前迁移任务状态、阶段、警告与结果摘要。</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex flex-wrap items-center gap-3">
              <Badge variant={jobStatusVariant(job?.status)}>{jobStatusLabel(job?.status)}</Badge>
              <span className="text-sm text-slate-600">Job ID: {jobId || '暂无'}</span>
              <span className="text-sm text-slate-600">阶段: {job?.stage || latestEvent?.stage || '未开始'}</span>
              <span className="text-sm text-slate-600">进度: {job?.progress ?? 0}%</span>
            </div>

            <div className="h-2 overflow-hidden rounded-full bg-slate-100">
              <div
                className="h-full rounded-full bg-primary transition-all"
                style={{ width: `${Math.max(0, Math.min(100, job?.progress ?? 0))}%` }}
              />
            </div>

            {latestEvent && (
              <div className="rounded-lg border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-700">
                最新事件：{latestEvent.message}
              </div>
            )}

            {localMessage && (
              <div className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-700">
                {localMessage}
              </div>
            )}

            {shouldShowJobError && (
              <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
                错误信息：{job.error}
              </div>
            )}

            {job?.warnings?.length ? (
              <div className="rounded-lg border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-700">
                <div className="mb-2 font-medium">警告</div>
                <ul className="list-disc space-y-1 pl-5">
                  {job.warnings.map(item => (
                    <li key={item}>{item}</li>
                  ))}
                </ul>
              </div>
            ) : null}

            {job?.summary ? (
              <pre className="overflow-x-auto rounded-lg border border-slate-200 bg-slate-950 p-4 text-xs text-slate-100">
                {JSON.stringify(job.summary, null, 2)}
              </pre>
            ) : null}

            <div className="flex flex-wrap gap-2">
              <Button type="button" variant="outline" onClick={() => void handleRefreshJob()} disabled={!jobId}>
                <RefreshCw className="h-4 w-4" />
                刷新任务状态
              </Button>
              <Button
                type="button"
                variant="outline"
                onClick={() => void handleManualReindex()}
                disabled={manualReindexRunning}
              >
                {manualReindexRunning ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
                仅触发索引重建
              </Button>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
