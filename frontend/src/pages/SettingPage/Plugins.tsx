import { useEffect, useState } from 'react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import { activatePlugin, disablePlugin, enablePlugin, installPlugin, listPlugins, rollbackPlugin, type PluginInstallation } from '@/services/plugins'
import { useBackendInitContext } from '@/contexts/BackendInitContext'

const permissions = ['note.read', 'note.write', 'network', 'workspace.read', 'workspace.write']

export default function Plugins() {
  const { backendReady } = useBackendInitContext()
  const [plugins, setPlugins] = useState<PluginInstallation[]>([])
  const [sourceUrl, setSourceUrl] = useState('')
  const [sha256, setSha256] = useState('')
  const [grants, setGrants] = useState<string[]>([])
  const [busy, setBusy] = useState(false)
  const refresh = async () => setPlugins((await listPlugins()).plugins)
  useEffect(() => { if (backendReady) void refresh() }, [backendReady])
  const install = async () => { if (!sourceUrl.trim()) return; setBusy(true); try { await installPlugin({ source_url: sourceUrl.trim(), expected_sha256: sha256.trim() || undefined, granted_permissions: grants }); setSourceUrl(''); setSha256(''); await refresh() } finally { setBusy(false) } }
  return <div className="flex h-full flex-col gap-5 overflow-y-auto p-5 md:p-8" aria-busy={!backendReady}>
    {!backendReady && <div role="status" className="rounded-lg border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900">后端尚未 ready，插件请求已暂停。</div>}
    <div><h1 className="text-xl font-semibold text-on-surface">插件安装与运行</h1><p className="mt-1 text-sm text-on-surface-variant">仅接受 HTTPS GitHub/Gitee Release ZIP；安装脚本永不执行。</p></div>
    <Card><CardHeader><CardTitle>安装 Release</CardTitle></CardHeader><CardContent className="space-y-4">
      <div><Label htmlFor="plugin-source">Release ZIP URL</Label><Input id="plugin-source" value={sourceUrl} onChange={e => setSourceUrl(e.target.value)} placeholder="https://github.com/org/plugin/releases/download/v1/plugin.zip" /></div>
      <div><Label htmlFor="plugin-sha">SHA-256（可选但推荐）</Label><Input id="plugin-sha" value={sha256} onChange={e => setSha256(e.target.value)} /></div>
      <div><Label>授予权限</Label><div className="mt-2 flex flex-wrap gap-3">{permissions.map(permission => <label key={permission} className="flex items-center gap-2 text-sm"><input type="checkbox" checked={grants.includes(permission)} onChange={e => setGrants(old => e.target.checked ? [...old, permission] : old.filter(item => item !== permission))} />{permission}</label>)}</div></div>
      <Button disabled={!backendReady || busy || !sourceUrl.trim()} onClick={() => void install()}>{busy ? '安装中…' : '安装并校验'}</Button>
    </CardContent></Card>
    <div className="grid gap-4">{plugins.map(plugin => <Card key={plugin.plugin_id}><CardHeader><CardTitle className="flex items-center justify-between"><span>{plugin.plugin_id}</span><span className="text-sm font-normal text-on-surface-variant">{plugin.runtime_status}</span></CardTitle></CardHeader><CardContent className="space-y-3"><div className="flex items-center gap-3"><Switch checked={plugin.enabled} onCheckedChange={checked => void (checked ? enablePlugin(plugin.plugin_id) : disablePlugin(plugin.plugin_id)).then(refresh)} /><span>{plugin.enabled ? '已启用' : '已禁用'} · active {plugin.active_version || '未激活'}</span></div><div className="flex flex-wrap gap-2">{plugin.versions.map(version => <Button key={version.version} variant={version.version === plugin.active_version ? 'default' : 'outline'} size="sm" onClick={() => void (version.version === plugin.active_version ? rollbackPlugin(plugin.plugin_id, version.version) : activatePlugin(plugin.plugin_id, version.version)).then(refresh)}>{version.version}{version.version === plugin.active_version ? '（回滚）' : '激活'}</Button>)}</div><p className="text-xs text-on-surface-variant">权限：{plugin.granted_permissions.join(', ') || '无'}；旧版本保留。</p></CardContent></Card>)}</div>
  </div>
}
