import { useEffect, useState } from 'react'

import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { useBackendInitContext } from '@/contexts/BackendInitContext'
import {
  getApplicationWorkspaceSetting,
  getApplicationPermissions,
  listApplications,
  setApplicationPermissions,
  setExternalApplicationReadRoots,
  setApplicationWorkspaceSetting,
  type ApplicationWorkspaceSetting,
} from '@/services/applications'

const ApplicationSettings = () => {
  const { backendReady } = useBackendInitContext()
  const [setting, setSetting] = useState<ApplicationWorkspaceSetting | null>(null)
  const [root, setRoot] = useState('')
  const [externalRoots, setExternalRoots] = useState('')
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const [permissions, setPermissions] = useState<Record<string, Record<string, { requested: boolean; granted: boolean }>>>({})

  const load = async () => {
    setError('')
    try {
      const next = await getApplicationWorkspaceSetting()
      setSetting(next)
      setRoot(next.root)
      setExternalRoots((next.external_read_roots || []).join('\n'))
      const apps = await listApplications()
      const states = await Promise.all(apps.map(async app => [app.id, await getApplicationPermissions(app.id)] as const))
      setPermissions(Object.fromEntries(states))
    } catch {
      setError('应用默认本地项目目录读取失败')
    }
  }

  const togglePermission = async (appId: string, permission: string, granted: boolean) => {
    try {
      const next = await setApplicationPermissions(appId, { [permission]: granted })
      setPermissions(current => ({ ...current, [appId]: next }))
    } catch {
      setError('权限保存失败')
    }
  }

  useEffect(() => {
    if (backendReady) void load()
  }, [backendReady])

  const save = async () => {
    if (!root.trim()) return
    setBusy(true)
    setMessage('')
    setError('')
    try {
      const next = await setApplicationWorkspaceSetting(root.trim())
      await setExternalApplicationReadRoots(externalRoots.split('\n').map(item => item.trim()).filter(Boolean))
      setSetting(next)
      setRoot(next.root)
      setMessage('已保存。新建的应用实例会使用这个目录。')
    } catch {
      setError('目录保存失败，请确认目录是绝对路径且可写')
    } finally {
      setBusy(false)
    }
  }

  const saveExternalRoots = async () => {
    setBusy(true)
    setMessage('')
    setError('')
    try {
      await setExternalApplicationReadRoots(externalRoots.split('\n').map(item => item.trim()).filter(Boolean))
      setMessage('外部文件读取目录已保存。')
    } catch {
      setError('外部文件目录保存失败，请确认每行都是绝对路径')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="flex h-full flex-col gap-5 overflow-y-auto p-5 md:p-8">
      <div>
        <h1 className="text-xl font-semibold text-on-surface">应用设置</h1>
        <p className="mt-1 text-sm text-on-surface-variant">管理应用实例默认使用的本地项目目录。每个应用实例会在此目录下获得独立子目录。</p>
      </div>
      <Card>
        <CardHeader><CardTitle>默认本地项目目录</CardTitle></CardHeader>
        <CardContent className="space-y-4">
          <div>
            <Label htmlFor="application-workspace-root">目录路径</Label>
            <Input id="application-workspace-root" value={root} onChange={event => setRoot(event.target.value)} disabled={!backendReady || busy} placeholder="/Users/你的用户名/NoteMeld Applications" />
            <p className="mt-2 text-xs text-on-surface-variant">当前状态：{setting?.configured ? '已自定义' : '使用 NoteMeld 默认目录'}</p>
          </div>
          {message && <p role="status" className="text-sm text-emerald-700">{message}</p>}
          {error && <p role="alert" className="text-sm text-red-700">{error}</p>}
            <Button disabled={!backendReady || busy || !root.trim()} onClick={() => void save()}>{busy ? '保存中…' : '保存目录'}</Button>
        </CardContent>
      </Card>
      <Card>
        <CardHeader><CardTitle>外部文件读取目录</CardTitle></CardHeader>
        <CardContent className="space-y-4">
          <div><Label htmlFor="application-external-roots">授权目录（每行一个绝对路径）</Label><textarea id="application-external-roots" value={externalRoots} onChange={event => setExternalRoots(event.target.value)} disabled={!backendReady || busy} className="mt-1 min-h-24 w-full rounded-md border border-border-subtle bg-white px-3 py-2 text-sm" placeholder="/Users/你的用户名/Documents" /><p className="mt-2 text-xs text-on-surface-variant">应用只能读取这些目录中的文件，不能读取未授权路径。</p></div>
          <Button disabled={!backendReady || busy} onClick={() => void saveExternalRoots()}>{busy ? '保存中…' : '保存授权目录'}</Button>
        </CardContent>
      </Card>
      <Card>
        <CardHeader><CardTitle>应用权限</CardTitle></CardHeader>
        <CardContent className="space-y-5">
          {Object.entries(permissions).map(([appId, state]) => <div key={appId} className="space-y-2"><p className="text-sm font-medium text-on-surface">{appId}</p>{Object.entries(state).map(([permission, value]) => <label key={permission} className="flex items-center gap-2 text-sm text-on-surface-variant"><input type="checkbox" checked={value.granted} disabled={busy} onChange={event => void togglePermission(appId, permission, event.target.checked)} />{permission}{!value.requested && <span className="text-xs">（默认能力）</span>}</label>)}</div>)}
          {Object.keys(permissions).length === 0 && <p className="text-sm text-on-surface-variant">暂无可配置的应用权限。</p>}
        </CardContent>
      </Card>
    </div>
  )
}

export default ApplicationSettings
