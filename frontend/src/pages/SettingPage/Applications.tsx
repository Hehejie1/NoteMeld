import { useEffect, useState } from 'react'

import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { useBackendInitContext } from '@/contexts/BackendInitContext'
import {
  getApplicationWorkspaceSetting,
  setApplicationWorkspaceSetting,
  type ApplicationWorkspaceSetting,
} from '@/services/applications'

const ApplicationSettings = () => {
  const { backendReady } = useBackendInitContext()
  const [setting, setSetting] = useState<ApplicationWorkspaceSetting | null>(null)
  const [root, setRoot] = useState('')
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')

  const load = async () => {
    setError('')
    try {
      const next = await getApplicationWorkspaceSetting()
      setSetting(next)
      setRoot(next.root)
    } catch {
      setError('应用默认本地项目目录读取失败')
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
      setSetting(next)
      setRoot(next.root)
      setMessage('已保存。新建的应用实例会使用这个目录。')
    } catch {
      setError('目录保存失败，请确认目录是绝对路径且可写')
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
    </div>
  )
}

export default ApplicationSettings
