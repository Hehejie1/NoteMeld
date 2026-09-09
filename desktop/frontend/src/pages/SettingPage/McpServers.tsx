import { useCallback, useEffect, useMemo, useState } from 'react'
import { Loader2, Pencil, Plus, Trash2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { Switch } from '@/components/ui/switch'
import { ScrollArea } from '@/components/ui/scroll-area'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  deleteMcpServer,
  listMcpServers,
  upsertMcpServer,
  type McpAuthType,
  type McpServerConfig,
  type McpServerPayload,
  type McpTransport,
} from '@/services/mcpServers'

const SERVER_ID_REGEX = /^[A-Za-z0-9_-]{1,64}$/

interface FormState {
  serverId: string
  name: string
  transport: McpTransport
  enabled: boolean
  timeoutSeconds: string
  command: string
  args: string
  env: string
  cwd: string
  url: string
  headers: string
  authType: McpAuthType
  authToken: string
}

const emptyForm: FormState = {
  serverId: '',
  name: '',
  transport: 'stdio',
  enabled: false,
  timeoutSeconds: '',
  command: '',
  args: '',
  env: '',
  cwd: '',
  url: '',
  headers: '',
  authType: 'none',
  authToken: '',
}

const formFromConfig = (serverId: string, cfg: McpServerConfig): FormState => {
  const auth = (cfg.auth || {}) as Record<string, unknown>
  const authTypeRaw = typeof auth.type === 'string' ? auth.type : 'none'
  const authType: McpAuthType =
    authTypeRaw === 'bearer' || authTypeRaw === 'basic' ? authTypeRaw : 'none'
  return {
    serverId,
    name: cfg.name || '',
    transport: cfg.transport || 'stdio',
    enabled: Boolean(cfg.enabled),
    timeoutSeconds:
      typeof cfg.timeout_seconds === 'number' ? String(cfg.timeout_seconds) : '',
    command: cfg.command || '',
    args: Array.isArray(cfg.args) ? cfg.args.join('\n') : '',
    env: cfg.env
      ? Object.entries(cfg.env)
          .map(([k, v]) => `${k}=${v}`)
          .join('\n')
      : '',
    cwd: cfg.cwd || '',
    url: cfg.url || '',
    headers: cfg.headers
      ? Object.entries(cfg.headers)
          .map(([k, v]) => `${k}: ${v}`)
          .join('\n')
      : '',
    authType,
    authToken: '',
  }
}

const parseLines = (text: string): string[] =>
  text
    .split('\n')
    .map(line => line.trim())
    .filter(Boolean)

const parseArgs = (text: string): string[] => parseLines(text)

const parseEnv = (text: string): Record<string, string> => {
  const env: Record<string, string> = {}
  for (const line of parseLines(text)) {
    const idx = line.indexOf('=')
    if (idx <= 0) continue
    const key = line.slice(0, idx).trim()
    const val = line.slice(idx + 1).trim()
    if (key) env[key] = val
  }
  return env
}

const parseHeaders = (text: string): Record<string, string> => {
  const headers: Record<string, string> = {}
  for (const line of parseLines(text)) {
    const idx = line.indexOf(':')
    if (idx <= 0) continue
    const key = line.slice(0, idx).trim()
    const val = line.slice(idx + 1).trim()
    if (key) headers[key] = val
  }
  return headers
}

const buildPayload = (form: FormState): McpServerPayload | null => {
  if (!form.name.trim()) return null
  if (form.transport === 'stdio' && !form.command.trim()) return null
  if ((form.transport === 'http' || form.transport === 'sse') && !form.url.trim()) return null

  const timeoutNum = form.timeoutSeconds.trim()
    ? Number(form.timeoutSeconds.trim())
    : null
  const timeoutSeconds =
    timeoutNum !== null && Number.isFinite(timeoutNum) && timeoutNum > 0
      ? timeoutNum
      : null

  const payload: McpServerPayload = {
    name: form.name.trim(),
    transport: form.transport,
    enabled: form.enabled,
  }

  if (timeoutSeconds !== null) {
    payload.timeout_seconds = timeoutNum
  }

  if (form.transport === 'stdio') {
    payload.command = form.command.trim()
    const args = parseArgs(form.args)
    if (args.length) payload.args = args
    const env = parseEnv(form.env)
    if (Object.keys(env).length) payload.env = env
    if (form.cwd.trim()) payload.cwd = form.cwd.trim()
  } else {
    payload.url = form.url.trim()
    const headers = parseHeaders(form.headers)
    if (Object.keys(headers).length) payload.headers = headers
  }

  // auth：仅在用户输入新 token 时携带；省略时由后端保留已有凭证。
  if (form.authType !== 'none' && form.authToken.trim()) {
    payload.auth = { type: form.authType, token: form.authToken.trim() }
  }

  return payload
}

const transportLabel = (t: McpTransport): string =>
  t === 'stdio' ? 'stdio' : t === 'http' ? 'http' : 'sse'

/** 从已脱敏的 cfg 构建切换 enabled 的 payload，凭证字段交给后端保留。 */
const buildTogglePayload = (cfg: McpServerConfig, enabled: boolean): McpServerPayload => {
  const payload: McpServerPayload = {
    name: cfg.name,
    transport: cfg.transport,
    enabled,
  }
  if (typeof cfg.timeout_seconds === 'number') payload.timeout_seconds = cfg.timeout_seconds
  if (cfg.command !== undefined) payload.command = cfg.command
  if (Array.isArray(cfg.args)) payload.args = cfg.args
  if (cfg.env) payload.env = cfg.env
  if (cfg.cwd !== undefined) payload.cwd = cfg.cwd
  if (cfg.url !== undefined) payload.url = cfg.url
  if (cfg.headers) payload.headers = cfg.headers
  // auth 刻意不传：GET 不回显凭证，后端会保留已有值。
  return payload
}

export default function McpServers() {
  const [servers, setServers] = useState<Record<string, McpServerConfig>>({})
  const [loading, setLoading] = useState(false)
  const [dialogOpen, setDialogOpen] = useState(false)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [form, setForm] = useState<FormState>(emptyForm)
  const [submitting, setSubmitting] = useState(false)
  const [deleteTarget, setDeleteTarget] = useState<{ id: string; name: string } | null>(null)
  const [deleting, setDeleting] = useState(false)

  const loadServers = useCallback(async () => {
    setLoading(true)
    try {
      const result = await listMcpServers()
      setServers(result?.servers || {})
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void loadServers()
  }, [loadServers])

  const serverList = useMemo(
    () => Object.entries(servers).map(([id, cfg]) => ({ id, cfg })),
    [servers],
  )

  const openCreate = () => {
    setEditingId(null)
    setForm(emptyForm)
    setDialogOpen(true)
  }

  const openEdit = (id: string, cfg: McpServerConfig) => {
    setEditingId(id)
    setForm(formFromConfig(id, cfg))
    setDialogOpen(true)
  }

  const handleSubmit = async () => {
    const isEdit = editingId !== null
    const serverId = isEdit ? editingId! : form.serverId.trim()
    if (!isEdit && !SERVER_ID_REGEX.test(serverId)) return
    const payload = buildPayload(form)
    if (!payload) return
    setSubmitting(true)
    try {
      await upsertMcpServer(serverId, payload)
      setDialogOpen(false)
      await loadServers()
    } finally {
      setSubmitting(false)
    }
  }

  const handleDelete = async () => {
    if (!deleteTarget) return
    setDeleting(true)
    try {
      await deleteMcpServer(deleteTarget.id)
      setDeleteTarget(null)
      await loadServers()
    } finally {
      setDeleting(false)
    }
  }

  const isEdit = editingId !== null
  const canSubmit = (() => {
    if (!form.name.trim()) return false
    if (!isEdit && !SERVER_ID_REGEX.test(form.serverId.trim())) return false
    if (form.transport === 'stdio' && !form.command.trim()) return false
    if ((form.transport === 'http' || form.transport === 'sse') && !form.url.trim()) return false
    return true
  })()

  return (
    <ScrollArea className="h-full overflow-y-auto bg-white">
      <div className="container mx-auto px-4 py-8">
        <div className="mb-6 flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold">MCP 服务器</h1>
            <p className="mt-1 text-sm text-muted-foreground">
              管理 Model Context Protocol 服务器，启用后 Agent 可调用其工具。
            </p>
          </div>
          <Button onClick={openCreate} disabled={loading}>
            <Plus className="mr-1.5 h-4 w-4" />
            新增 server
          </Button>
        </div>

        {loading ? (
          <div className="flex items-center gap-2 py-12 text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" />
            加载中...
          </div>
        ) : serverList.length === 0 ? (
          <Card>
            <CardContent className="py-12 text-center text-sm text-muted-foreground">
              暂未配置 MCP 服务器，点击右上角新增。
            </CardContent>
          </Card>
        ) : (
          <div className="space-y-3">
            {serverList.map(({ id, cfg }) => (
              <Card key={id}>
                <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-3">
                  <div className="min-w-0">
                    <CardTitle className="flex items-center gap-2 text-base">
                      <span className="truncate">{cfg.name || id}</span>
                      <span className="shrink-0 rounded bg-surface-container px-1.5 py-0.5 font-mono text-[11px] text-on-surface-variant">
                        {transportLabel(cfg.transport)}
                      </span>
                    </CardTitle>
                    <div className="mt-1 font-mono text-[11px] text-muted-foreground">{id}</div>
                  </div>
                  <div className="flex shrink-0 items-center gap-3">
                    <div className="flex items-center gap-2">
                      <Switch
                        checked={Boolean(cfg.enabled)}
                        onCheckedChange={async checked => {
                          try {
                            await upsertMcpServer(id, buildTogglePayload(cfg, checked))
                            await loadServers()
                          } catch {
                            /* 错误已由 request 拦截器 toast */
                          }
                        }}
                      />
                      <span className="text-[12px] text-on-surface-variant">
                        {cfg.enabled ? '已启用' : '未启用'}
                      </span>
                    </div>
                    <Button variant="outline" size="sm" onClick={() => openEdit(id, cfg)}>
                      <Pencil className="mr-1 h-3.5 w-3.5" />
                      编辑
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => setDeleteTarget({ id, name: cfg.name || id })}
                    >
                      <Trash2 className="mr-1 h-3.5 w-3.5" />
                      删除
                    </Button>
                  </div>
                </CardHeader>
                <CardContent className="pt-0 text-sm">
                  <div className="grid grid-cols-1 gap-2 text-[12px] text-muted-foreground md:grid-cols-2">
                    {cfg.transport === 'stdio' && (
                      <>
                        <div>
                          <span className="text-on-surface-variant/70">command：</span>
                          <span className="font-mono text-on-surface">{cfg.command || '-'}</span>
                        </div>
                        {cfg.cwd && (
                          <div>
                            <span className="text-on-surface-variant/70">cwd：</span>
                            <span className="font-mono text-on-surface">{cfg.cwd}</span>
                          </div>
                        )}
                      </>
                    )}
                    {(cfg.transport === 'http' || cfg.transport === 'sse') && cfg.url && (
                      <div className="md:col-span-2">
                        <span className="text-on-surface-variant/70">url：</span>
                        <span className="break-all font-mono text-on-surface">{cfg.url}</span>
                      </div>
                    )}
                    {typeof cfg.timeout_seconds === 'number' && (
                      <div>
                        <span className="text-on-surface-variant/70">超时：</span>
                        <span className="font-mono text-on-surface">{cfg.timeout_seconds}s</span>
                      </div>
                    )}
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        )}
      </div>

      {/* 新增/编辑 Dialog */}
      <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
        <DialogContent className="max-h-[90vh] max-w-[640px] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>{isEdit ? '编辑 MCP 服务器' : '新增 MCP 服务器'}</DialogTitle>
            <DialogDescription>
              {isEdit
                ? '敏感凭证不会回显；保留脱敏占位符或不输入新 token 时，原凭证保持不变。'
                : '配置 MCP 服务器，启用后 Agent 可调用此 server 的工具。'}
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4">
            {/* server_id */}
            <div className="space-y-1.5">
              <Label htmlFor="mcp-server-id">server_id</Label>
              <Input
                id="mcp-server-id"
                value={form.serverId}
                onChange={e => setForm(prev => ({ ...prev, serverId: e.target.value }))}
                placeholder="如 my_mcp_server"
                disabled={isEdit}
              />
              {!isEdit && (
                <p className="text-[11px] text-muted-foreground">
                  仅限字母、数字、下划线和连字符，1-64 字符，创建后不可修改。
                </p>
              )}
            </div>

            {/* name */}
            <div className="space-y-1.5">
              <Label htmlFor="mcp-name">名称</Label>
              <Input
                id="mcp-name"
                value={form.name}
                onChange={e => setForm(prev => ({ ...prev, name: e.target.value }))}
                placeholder="显示名称"
              />
            </div>

            {/* transport */}
            <div className="space-y-1.5">
              <Label>传输方式</Label>
              <Select
                value={form.transport}
                onValueChange={val => setForm(prev => ({ ...prev, transport: val as McpTransport }))}
              >
                <SelectTrigger className="w-full">
                  <SelectValue placeholder="选择传输方式" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="stdio">stdio</SelectItem>
                  <SelectItem value="http">http</SelectItem>
                  <SelectItem value="sse">sse</SelectItem>
                </SelectContent>
              </Select>
            </div>

            {/* enabled */}
            <div className="flex items-center justify-between rounded-md border border-border-subtle px-3 py-2">
              <div>
                <Label htmlFor="mcp-enabled">启用</Label>
                <p className="text-[11px] text-muted-foreground">启用后 Agent 可调用此 server 的工具</p>
              </div>
              <Switch
                id="mcp-enabled"
                checked={form.enabled}
                onCheckedChange={checked => setForm(prev => ({ ...prev, enabled: checked }))}
              />
            </div>

            {/* timeout_seconds */}
            <div className="space-y-1.5">
              <Label htmlFor="mcp-timeout">超时（秒）</Label>
              <Input
                id="mcp-timeout"
                type="number"
                min={1}
                value={form.timeoutSeconds}
                onChange={e => setForm(prev => ({ ...prev, timeoutSeconds: e.target.value }))}
                placeholder="缺省 60 秒"
              />
            </div>

            {/* stdio-only */}
            {form.transport === 'stdio' && (
              <>
                <div className="space-y-1.5">
                  <Label htmlFor="mcp-command">command</Label>
                  <Input
                    id="mcp-command"
                    value={form.command}
                    onChange={e => setForm(prev => ({ ...prev, command: e.target.value }))}
                    placeholder="如 npx"
                  />
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor="mcp-args">args（每行一个）</Label>
                  <Textarea
                    id="mcp-args"
                    value={form.args}
                    onChange={e => setForm(prev => ({ ...prev, args: e.target.value }))}
                    placeholder={'-y\n@modelcontextprotocol/server-filesystem\n/path'}
                    className="min-h-[80px] font-mono text-[12px]"
                  />
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor="mcp-env">env（每行一个 key=value）</Label>
                  <Textarea
                    id="mcp-env"
                    value={form.env}
                    onChange={e => setForm(prev => ({ ...prev, env: e.target.value }))}
                    placeholder={'API_KEY=xxx\nNODE_ENV=production'}
                    className="min-h-[80px] font-mono text-[12px]"
                  />
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor="mcp-cwd">cwd</Label>
                  <Input
                    id="mcp-cwd"
                    value={form.cwd}
                    onChange={e => setForm(prev => ({ ...prev, cwd: e.target.value }))}
                    placeholder="工作目录（可选）"
                  />
                </div>
              </>
            )}

            {/* http/sse-only */}
            {(form.transport === 'http' || form.transport === 'sse') && (
              <>
                <div className="space-y-1.5">
                  <Label htmlFor="mcp-url">url</Label>
                  <Input
                    id="mcp-url"
                    value={form.url}
                    onChange={e => setForm(prev => ({ ...prev, url: e.target.value }))}
                    placeholder="https://example.com/mcp"
                  />
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor="mcp-headers">headers（每行一个 key: value）</Label>
                  <Textarea
                    id="mcp-headers"
                    value={form.headers}
                    onChange={e => setForm(prev => ({ ...prev, headers: e.target.value }))}
                    placeholder={'X-Custom-Header: value\nAuthorization: Bearer xxx'}
                    className="min-h-[80px] font-mono text-[12px]"
                  />
                </div>
              </>
            )}

            {/* auth（http/sse 才有意义，但 stdio 也允许配置） */}
            <div className="space-y-1.5">
              <Label>鉴权方式</Label>
              <Select
                value={form.authType}
                onValueChange={val => setForm(prev => ({ ...prev, authType: val as McpAuthType }))}
              >
                <SelectTrigger className="w-full">
                  <SelectValue placeholder="选择鉴权方式" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="none">none</SelectItem>
                  <SelectItem value="bearer">bearer</SelectItem>
                  <SelectItem value="basic">basic</SelectItem>
                </SelectContent>
              </Select>
            </div>
            {form.authType !== 'none' && (
              <div className="space-y-1.5">
                <Label htmlFor="mcp-token">token</Label>
                <Input
                  id="mcp-token"
                  type="password"
                  value={form.authToken}
                  onChange={e => setForm(prev => ({ ...prev, authToken: e.target.value }))}
                  placeholder={isEdit ? '重新输入以更新（留空保留原 token）' : '输入 token'}
                />
                {isEdit && (
                  <p className="text-[11px] text-warning">
                    已保存 token 不会回显；只有输入新 token 时才会替换。
                  </p>
                )}
              </div>
            )}
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={() => setDialogOpen(false)} disabled={submitting}>
              取消
            </Button>
            <Button onClick={handleSubmit} disabled={!canSubmit || submitting}>
              {submitting && <Loader2 className="mr-1.5 h-4 w-4 animate-spin" />}
              {isEdit ? '保存' : '创建'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* 删除确认 */}
      <Dialog open={!!deleteTarget} onOpenChange={open => !open && setDeleteTarget(null)}>
        <DialogContent className="max-w-[420px]">
          <DialogHeader>
            <DialogTitle>删除 MCP 服务器</DialogTitle>
            <DialogDescription>
              确认删除「{deleteTarget?.name}」吗？此操作不可撤销。
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleteTarget(null)} disabled={deleting}>
              取消
            </Button>
            <Button variant="destructive" onClick={handleDelete} disabled={deleting}>
              {deleting && <Loader2 className="mr-1.5 h-4 w-4 animate-spin" />}
              删除
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </ScrollArea>
  )
}
