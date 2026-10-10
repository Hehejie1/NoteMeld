import { useEffect, useMemo, useState } from 'react'
import {
  Archive,
  CheckCircle2,
  Copy,
  Download,
  Loader2,
  MoreVertical,
  Pencil,
  Trash2,
  XCircle,
} from 'lucide-react'
import CloudClient, { CloudSession } from '../../services/cloud'
import { EmptyState, ErrorState, LoadingState } from '../ui/feedback'
import { localizeCloudError, useCloudLocale } from '../../pages/CloudPage/cloudLocale'
import { CloudRenameDialog } from './CloudRenameDialog'
import { Button, Input } from '@notemeld/ui-web'

type ListCommand = {
  id: string
  sequence: number
  input_text?: string
  status: string
  created_at: number
}

// 会话状态三分类映射：完成 / 对话中 / 报错。
function statusKind(status?: string): 'done' | 'running' | 'error' {
  if (status === 'failed' || status === 'error') return 'error'
  if (status === 'running' || status === 'queued' || status === 'waiting_approval')
    return 'running'
  return 'done'
}

export function CloudSessionList({
  client,
  archived = false,
  selectedId,
  reloadKey,
  onSelect,
  onChanged,
}: {
  client: CloudClient
  archived?: boolean
  selectedId?: string
  reloadKey?: number
  onSelect: (session: CloudSession) => void
  onChanged?: () => void
}) {
  const { t } = useCloudLocale()
  const [sessions, setSessions] = useState<CloudSession[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<Error | null>(null)
  const [query, setQuery] = useState('')
  const [menuId, setMenuId] = useState<string | null>(null)
  const [renaming, setRenaming] = useState<CloudSession | null>(null)
  const [busyId, setBusyId] = useState<string | null>(null)
  const [showAll, setShowAll] = useState(false)

  async function refresh() {
    setLoading(true)
    try {
      setSessions(await client.listSessions(archived))
      setError(null)
    } catch (reason) {
      setError(reason instanceof Error ? reason : new Error(String(reason)))
    } finally {
      setLoading(false)
    }
  }
  useEffect(() => {
    void refresh()
  }, [client, archived, reloadKey])

  const filtered = useMemo(() => {
    const q = query.trim().toLocaleLowerCase()
    if (!q) return sessions
    return sessions.filter(session =>
      `${session.title ?? ''} ${session.status ?? ''}`.toLocaleLowerCase().includes(q)
    )
  }, [query, sessions])

  // 默认只展示前 3 个会话，点击“查看全部”展开。
  const visible = showAll ? filtered : filtered.slice(0, 3)

  async function runAction(session: CloudSession, action: () => Promise<void>) {
    setBusyId(session.id)
    try {
      await action()
      onChanged?.()
      await refresh()
    } catch (reason) {
      setError(reason instanceof Error ? reason : new Error(String(reason)))
    } finally {
      setBusyId(null)
      setMenuId(null)
    }
  }

  // 导出：把该会话全部命令（用户输入）与执行状态拼成 Markdown 复制到剪切板。
  async function exportMarkdown(session: CloudSession) {
    const commands = (await client.listCommands(session.id, 0, 500)) as ListCommand[]
    const lines = [
      `# ${session.title || t('session.untitled', '未命名会话')}`,
      '',
      ...commands.flatMap(command => [
        `## ${t('session.user', '用户')}`,
        command.input_text ?? '',
        '',
        `> ${t('session.status-' + command.status, command.status)}`,
        '',
      ]),
    ]
    await navigator.clipboard.writeText(lines.join('\n'))
    setMenuId(null)
  }

  if (loading)
    return <LoadingState title={t('session.reading', '正在读取会话')} className="min-h-24 border-0 p-3" />
  if (error && !sessions.length)
    return (
      <ErrorState
        title={t('session.read-failed', '会话读取失败')}
        description={localizeCloudError(error.message, t)}
        action={
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="rounded border-[var(--border-subtle)] px-3 py-1.5 text-xs"
            onClick={() => void refresh()}
          >
            {t('session.retry', '重试')}
          </Button>
        }
        className="min-h-24 border-0 p-3 text-[var(--error)]"
      />
    )

  const statusMeta = {
    done: { icon: CheckCircle2, label: t('session.state-done', '完成'), cls: 'text-emerald-600' },
    running: { icon: Loader2, label: t('session.state-running', '对话中'), cls: 'text-[var(--primary)]' },
    error: { icon: XCircle, label: t('session.state-error', '报错'), cls: 'text-[var(--error)]' },
  }

  return (
    <div className="flex min-h-0 flex-col">
      <label className="cloud-session-search mx-2 mt-2">
        <Input
          value={query}
          onChange={event => setQuery(event.target.value)}
          onValueChange={setQuery}
          placeholder={t('session.search', '搜索会话')}
        />
      </label>
      {!filtered.length ? (
        <EmptyState
          title={archived ? t('session.archived', '暂无已归档会话') : t('session.active', '暂无活动会话')}
          className="min-h-24 border-0 p-4 text-[var(--on-surface-variant)]"
        />
      ) : (
        <nav aria-label={t('sessions.sidebar-title', '会话')} className="min-h-0 flex-1 overflow-auto px-2 py-2">
          <ul role="list" className="space-y-1">
            {visible.map(session => {
              const kind = statusKind(session.status)
              const meta = statusMeta[kind]
              const StatusIcon = meta.icon
              return (
                <li
                  key={session.id}
                  className={`group relative flex items-center gap-1 rounded-lg px-1 ${selectedId === session.id ? 'bg-[var(--surface-container-high)]' : 'hover:bg-[var(--surface-container)]'}`}
                >
                  <Button
                    type="button"
                    variant="ghost"
                    aria-current={selectedId === session.id ? 'page' : undefined}
                    className="min-w-0 flex-1 flex-col items-stretch justify-start rounded-md px-2 py-2 text-left"
                    onClick={() => onSelect(session)}
                  >
                    <span className="block truncate text-sm font-medium">
                      {session.title || t('session.untitled', '未命名会话')}
                    </span>
                    <span className={`mt-0.5 flex items-center gap-1 text-[11px] ${meta.cls}`}>
                      <StatusIcon className={`h-3 w-3 ${kind === 'running' ? 'animate-spin' : ''}`} />
                      {meta.label}
                    </span>
                  </Button>
                  {/* hover 显示：归档图标 + 三点菜单 */}
                  <div className="flex shrink-0 items-center opacity-0 transition-opacity group-hover:opacity-100">
                    <Button
                      type="button"
                      variant="ghost"
                      size="icon"
                      title={archived ? t('session.restore', '恢复') : t('session.archive', '归档')}
                      disabled={busyId === session.id}
                      className="grid h-7 w-7 place-items-center rounded text-[var(--on-surface-variant)] hover:bg-[var(--surface-container-high)] disabled:opacity-50"
                      onClick={() =>
                        void runAction(session, () =>
                          archived
                            ? client.restoreSession(session.id)
                            : client.archiveSession(session.id)
                        )
                      }
                    >
                      <Archive className="h-3.5 w-3.5" />
                    </Button>
                    <Button
                      type="button"
                      variant="ghost"
                      size="icon"
                      title={t('session.more', '更多操作')}
                      className="grid h-7 w-7 place-items-center rounded text-[var(--on-surface-variant)] hover:bg-[var(--surface-container-high)]"
                      onClick={() => setMenuId(menuId === session.id ? null : session.id)}
                    >
                      <MoreVertical className="h-3.5 w-3.5" />
                    </Button>
                  </div>
                  {menuId === session.id ? (
                    <div
                      role="menu"
                      className="absolute top-9 right-1 z-30 w-40 overflow-hidden rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-container-lowest)] py-1 text-xs shadow-lg"
                    >
                      <Button
                        type="button"
                        variant="ghost"
                        role="menuitem"
                        className="flex w-full items-center justify-start gap-2 rounded-none px-3 py-2 text-left text-[var(--on-surface)] font-normal hover:bg-[var(--surface-container)]"
                        onClick={() => {
                          setMenuId(null)
                          setRenaming(session)
                        }}
                      >
                        <Pencil className="h-3.5 w-3.5" />
                        {t('session.rename', '重命名')}
                      </Button>
                      <Button
                        type="button"
                        variant="ghost"
                        role="menuitem"
                        className="flex w-full items-center justify-start gap-2 rounded-none px-3 py-2 text-left text-[var(--on-surface)] font-normal hover:bg-[var(--surface-container)]"
                        onClick={() => void exportMarkdown(session)}
                      >
                        <Download className="h-3.5 w-3.5" />
                        {t('session.export', '导出')}
                      </Button>
                      <Button
                        type="button"
                        variant="ghost"
                        role="menuitem"
                        className="flex w-full items-center justify-start gap-2 rounded-none px-3 py-2 text-left text-[var(--on-surface)] font-normal hover:bg-[var(--surface-container)]"
                        disabled={busyId === session.id}
                        onClick={() =>
                          void runAction(session, async () => {
                            const copy = await client.copySession(session.id)
                            onSelect(copy)
                          })
                        }
                      >
                        <Copy className="h-3.5 w-3.5" />
                        {t('session.copy-branch', '复制分支')}
                      </Button>
                      <Button
                        type="button"
                        variant="ghost"
                        role="menuitem"
                        className="flex w-full items-center justify-start gap-2 rounded-none px-3 py-2 text-left text-[var(--error)] font-normal hover:bg-[var(--surface-container)]"
                        disabled={busyId === session.id}
                        onClick={() => {
                          if (!window.confirm(t('sessions.delete-confirm', '永久删除此会话？'))) return
                          void runAction(session, () => client.deleteSession(session.id))
                        }}
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                        {t('session.delete', '永久删除')}
                      </Button>
                    </div>
                  ) : null}
                </li>
              )
            })}
          </ul>
          {filtered.length > 3 ? (
            <Button
              type="button"
              variant="ghost"
              size="sm"
              className="w-full rounded-md px-2 py-2 text-xs text-[var(--primary)] font-normal hover:bg-[var(--surface-container)]"
              onClick={() => setShowAll(value => !value)}
            >
              {showAll
                ? t('session.collapse', '收起')
                : t('session.view-all', `查看全部 ${filtered.length} 个会话`)}
            </Button>
          ) : null}
        </nav>
      )}
      {renaming ? (
        <CloudRenameDialog
          title={renaming.title || ''}
          onCancel={() => setRenaming(null)}
          onSave={async nextTitle => {
            await client.renameSession(renaming.id, nextTitle)
            setRenaming(null)
            onChanged?.()
            await refresh()
          }}
        />
      ) : null}
    </div>
  )
}
