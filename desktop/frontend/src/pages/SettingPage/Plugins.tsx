import { useCallback, useEffect, useMemo, useState } from 'react'
import { Check, Plus, Search, ShieldCheck, Sparkles, X } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { activatePlugin, BUILTIN_PLUGIN_CATALOG, disablePlugin, enablePlugin, installPlugin, listPlugins, rollbackPlugin, type BuiltinPluginCatalogItem, type PluginInstallation } from '@/services/plugins'
import { useBackendInitContext } from '@/contexts/BackendInitContext'

const permissions = ['note.read', 'note.write', 'network', 'workspace.read', 'workspace.write']
const targetLabels: Record<string, string> = { 'host-ready': '当前可用', 'contract-ready': '协议就绪', unverified: '待验证', unsupported: '暂不支持' }

function statusLabel(plugin?: PluginInstallation) {
  if (!plugin) return '未安装'
  if (plugin.runtime_status === 'crashed') return '运行异常'
  if (!plugin.enabled) return '已禁用'
  return plugin.runtime_status === 'running' ? '运行中' : plugin.runtime_status
}

export default function Plugins() {
  const { backendReady } = useBackendInitContext()
  const [plugins, setPlugins] = useState<PluginInstallation[]>([])
  const [activeTab, setActiveTab] = useState<'catalog' | 'installed'>('catalog')
  const [query, setQuery] = useState('')
  const [category, setCategory] = useState('全部')
  const [detail, setDetail] = useState<BuiltinPluginCatalogItem | PluginInstallation | null>(null)
  const [addOpen, setAddOpen] = useState(false)
  const [sourceUrl, setSourceUrl] = useState('')
  const [sha256, setSha256] = useState('')
  const [grants, setGrants] = useState<string[]>([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const refresh = useCallback(async () => {
    if (!backendReady) return
    try { setError(''); setPlugins((await listPlugins()).plugins) } catch { setError('插件状态加载失败，请稍后重试。') }
  }, [backendReady])
  useEffect(() => { void refresh() }, [refresh])

  const installedById = useMemo(() => new Map(plugins.map(plugin => [plugin.plugin_id, plugin])), [plugins])
  const categories = useMemo(() => ['全部', ...new Set(BUILTIN_PLUGIN_CATALOG.map(item => item.category))], [])
  const filteredCatalog = useMemo(() => BUILTIN_PLUGIN_CATALOG.filter(item => {
    const text = `${item.name} ${item.plugin_id} ${item.description} ${item.capabilities.join(' ')}`.toLowerCase()
    return (category === '全部' || item.category === category) && (!query.trim() || text.includes(query.trim().toLowerCase()))
  }), [category, query])
  const filteredInstalled = useMemo(() => plugins.filter(item => `${item.plugin_id} ${item.granted_permissions.join(' ')}`.toLowerCase().includes(query.trim().toLowerCase())), [plugins, query])

  const run = async (action: () => Promise<unknown>) => {
    if (!backendReady || busy) return
    setBusy(true); setError('')
    try { await action(); await refresh() } catch { setError('操作失败，插件状态未改变，请检查诊断信息后重试。') } finally { setBusy(false) }
  }
  const install = async () => {
    if (!backendReady || busy || !sourceUrl.trim()) return
    setBusy(true); setError('')
    try {
      await installPlugin({ source_url: sourceUrl.trim(), expected_sha256: sha256.trim() || undefined, granted_permissions: grants })
      setSourceUrl(''); setSha256(''); setGrants([]); setAddOpen(false); await refresh()
    } catch { setError('插件校验或安装失败：来源、版本、hash、许可证或权限未通过。') } finally { setBusy(false) }
  }
  const renderActions = (plugin: PluginInstallation) => <div className="flex flex-wrap gap-2">
    <Button size="sm" variant="outline" disabled={busy} onClick={() => void run(() => plugin.enabled ? disablePlugin(plugin.plugin_id) : enablePlugin(plugin.plugin_id))}>{plugin.enabled ? '禁用' : '启用'}</Button>
    {plugin.versions.map(version => <Button key={version.version} size="sm" variant={version.version === plugin.active_version ? 'secondary' : 'outline'} disabled={busy} onClick={() => void run(() => version.version === plugin.active_version ? rollbackPlugin(plugin.plugin_id, version.version) : activatePlugin(plugin.plugin_id, version.version))}>{version.version}{version.version === plugin.active_version ? ' · 回滚' : ' · 激活'}</Button>)}
  </div>

  return <div className="flex h-full flex-col gap-5 overflow-y-auto bg-surface p-5 md:p-8" aria-busy={!backendReady || busy}>
    {!backendReady && <div role="status" className="rounded-lg border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900">后端尚未 ready，插件请求已暂停。</div>}
    {error && <div role="alert" className="flex items-center justify-between rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-800"><span>{error}</span><button aria-label="关闭错误" onClick={() => setError('')}><X className="h-4 w-4" /></button></div>}
    <div className="flex flex-wrap items-start justify-between gap-4"><div><div className="flex items-center gap-2"><Sparkles className="h-5 w-5 text-primary" /><h1 className="text-xl font-semibold text-on-surface">插件与技能</h1></div><p className="mt-1 text-sm text-on-surface-variant">发现 NoteMeld 能力，安全添加你自己的标准插件。</p></div><Button disabled={!backendReady || busy} onClick={() => setAddOpen(true)}><Plus className="mr-1 h-4 w-4" />添加插件 / 内容</Button></div>
    <div className="flex flex-wrap items-center gap-2 border-b border-border-subtle"><button className={`px-3 py-2 text-sm ${activeTab === 'catalog' ? 'border-b-2 border-primary font-semibold text-primary' : 'text-on-surface-variant'}`} onClick={() => setActiveTab('catalog')}>插件目录 <span className="ml-1 text-xs">{BUILTIN_PLUGIN_CATALOG.length}</span></button><button className={`px-3 py-2 text-sm ${activeTab === 'installed' ? 'border-b-2 border-primary font-semibold text-primary' : 'text-on-surface-variant'}`} onClick={() => setActiveTab('installed')}>已安装 <span className="ml-1 text-xs">{plugins.length}</span></button></div>
    <div className="flex flex-wrap gap-3"><div className="relative min-w-[220px] flex-1"><Search className="absolute left-3 top-2.5 h-4 w-4 text-on-surface-variant" /><Input className="pl-9" value={query} onChange={event => setQuery(event.target.value)} placeholder="搜索插件、能力或简介" /></div>{activeTab === 'catalog' && <div className="flex flex-wrap gap-2">{categories.map(item => <Button key={item} size="sm" variant={category === item ? 'default' : 'outline'} onClick={() => setCategory(item)}>{item}</Button>)}</div>}</div>
    {activeTab === 'catalog' ? <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">{filteredCatalog.map(item => { const installed = installedById.get(item.plugin_id); return <Card key={item.plugin_id} className="flex flex-col"><CardHeader><CardTitle className="flex items-start justify-between gap-3 text-base"><span className="flex items-center gap-2"><span className="flex h-9 w-9 items-center justify-center rounded-xl bg-primary/10 text-primary"><Sparkles className="h-4 w-4" /></span>{item.name}</span><div className="flex flex-wrap justify-end gap-1">{item.recommended && <Badge variant="secondary">推荐</Badge>}<Badge variant={installed ? 'default' : 'outline'}>{statusLabel(installed)}</Badge></div></CardTitle></CardHeader><CardContent className="flex flex-1 flex-col gap-4"><p className="min-h-12 text-sm leading-6 text-on-surface-variant">{item.description}</p><div className="flex flex-wrap gap-1">{item.capabilities.map(capability => <Badge key={capability} variant="outline">{capability}</Badge>)}</div><div className="mt-auto flex items-center justify-between gap-3"><span className="text-xs text-on-surface-variant">{item.category} · {targetLabels[item.targets.desktop]}</span><Button size="sm" variant="outline" onClick={() => setDetail(item)}>{installed ? '查看详情' : '了解更多'}</Button></div></CardContent></Card> })}</div> : <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">{filteredInstalled.map(plugin => <Card key={plugin.plugin_id}><CardHeader><CardTitle className="flex items-center justify-between gap-3 text-base"><span>{plugin.plugin_id}</span><Badge variant={plugin.runtime_status === 'crashed' ? 'destructive' : 'secondary'}>{statusLabel(plugin)}</Badge></CardTitle></CardHeader><CardContent className="space-y-3"><p className="text-sm text-on-surface-variant">active version：{plugin.active_version || '未激活'}</p><p className="text-xs text-on-surface-variant">权限：{plugin.granted_permissions.join(', ') || '无'}</p>{renderActions(plugin)}<Button size="sm" variant="ghost" onClick={() => setDetail(plugin)}>查看详情</Button></CardContent></Card>)}</div>}
    {((activeTab === 'catalog' && !filteredCatalog.length) || (activeTab === 'installed' && !filteredInstalled.length)) && <div className="rounded-xl border border-dashed p-10 text-center text-sm text-on-surface-variant">{activeTab === 'installed' ? '还没有已安装插件。' : '没有匹配的插件。'}<div className="mt-3"><Button variant="outline" onClick={() => { setQuery(''); setCategory('全部') }}>清除筛选</Button></div></div>}
    <Dialog open={Boolean(detail)} onOpenChange={open => { if (!open) setDetail(null) }}><DialogContent><DialogHeader><DialogTitle>{detail && ('name' in detail ? detail.name : detail.plugin_id)}</DialogTitle><DialogDescription>{detail && ('description' in detail ? detail.description : '已安装插件运行详情')}</DialogDescription></DialogHeader>{detail && ('name' in detail ? <div className="space-y-4 text-sm"><div><Label>能力</Label><div className="mt-2 flex flex-wrap gap-1">{detail.capabilities.map(capability => <Badge key={capability} variant="outline">{capability}</Badge>)}</div></div><div><Label>权限与兼容性</Label><p className="mt-2 text-on-surface-variant">{detail.requested_permissions.join(', ') || '无权限'} · 桌面：{targetLabels[detail.targets.desktop]}</p></div><p className="text-xs text-on-surface-variant">许可证：{detail.license} · 内置目录项，未安装状态不会执行任何代码。</p></div> : <div className="space-y-3 text-sm"><p>运行状态：{statusLabel(detail)} · active version：{detail.active_version || '未激活'}</p><p className="text-on-surface-variant">请求权限：{detail.requested_permissions.join(', ') || '无'}<br />已授予权限：{detail.granted_permissions.join(', ') || '无'}</p><p className="text-xs text-on-surface-variant">版本：{detail.versions.map(version => `${version.version} (${version.license})`).join('、') || '无'}</p></div>)}</DialogContent></Dialog>
    <Dialog open={addOpen} onOpenChange={open => { if (!busy) setAddOpen(open) }}><DialogContent><DialogHeader><DialogTitle>添加插件 / 内容</DialogTitle><DialogDescription>仅支持 HTTPS GitHub/Gitee Release ZIP。安装脚本不会执行，最终校验由 NoteMeld 后端完成。</DialogDescription></DialogHeader><div className="space-y-4"><div><Label htmlFor="plugin-source">Release ZIP URL</Label><Input id="plugin-source" value={sourceUrl} onChange={event => setSourceUrl(event.target.value)} placeholder="https://github.com/org/plugin/releases/download/v1/plugin.zip" /></div><div><Label htmlFor="plugin-sha">SHA-256（可选但推荐）</Label><Input id="plugin-sha" value={sha256} onChange={event => setSha256(event.target.value)} /></div><div><Label>授予权限</Label><div className="mt-2 grid gap-2 sm:grid-cols-2">{permissions.map(permission => <label key={permission} className="flex items-center gap-2 text-sm"><input type="checkbox" checked={grants.includes(permission)} onChange={event => setGrants(old => event.target.checked ? [...old, permission] : old.filter(item => item !== permission))} /><span>{permission}</span></label>)}</div></div><div className="rounded-lg bg-muted/50 p-3 text-xs text-on-surface-variant"><ShieldCheck className="mr-1 inline h-4 w-4" />只有你明确授予的权限会传给安装请求。</div></div><DialogFooter><Button variant="outline" disabled={busy} onClick={() => setAddOpen(false)}>取消</Button><Button disabled={!backendReady || busy || !sourceUrl.trim()} onClick={() => void install()}>{busy ? '校验并安装中…' : <><Check className="mr-1 h-4 w-4" />确认安装</>}</Button></DialogFooter></DialogContent></Dialog>
  </div>
}
