import { useEffect, useMemo, useState } from 'react'
import CloudClient, { CloudAccessRequest, CloudUser } from '../../services/cloud'
import { CloudUserForm } from '../CloudUserForm'
import { EmptyState, ErrorState, LoadingState } from '../ui/feedback'
import { Button } from '../ui/button'
import { Input } from '../ui/input'
import { Select, SelectItem } from '../ui/select'
import { useCloudLocale } from '../../pages/CloudPage/cloudLocale'

export function CloudUserList({
  client,
  onChanged,
}: {
  client: CloudClient
  onChanged?: () => void
}) {
  const { t } = useCloudLocale()
  const [users, setUsers] = useState<CloudUser[]>([])
  const [requests, setRequests] = useState<CloudAccessRequest[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState<string | null>(null)
  const [query, setQuery] = useState('')
  const [status, setStatus] = useState<'all' | 'active' | 'disabled'>('all')
  const [tab, setTab] = useState<'joined' | 'pending'>('joined')
  const [editing, setEditing] = useState<CloudUser | null>(null)
  const [adding, setAdding] = useState(false)
  async function refresh() {
    setLoading(true)
    try {
      const [nextUsers, nextRequests] = await Promise.all([
        client.listUsers(),
        client.listAccessRequests('pending'),
      ])
      setUsers(nextUsers)
      setRequests(nextRequests)
      setError(null)
    } catch (reason) {
      setError(
        reason instanceof Error ? reason.message : t('users.read-failed', '无法读取成员列表')
      )
    } finally {
      setLoading(false)
    }
  }
  useEffect(() => {
    void refresh()
  }, [client])
  async function remove(user: CloudUser) {
    if (user.role === 'admin') return
    setBusy(user.id)
    try {
      await client.deleteUser(user.id)
      await refresh()
      onChanged?.()
    } catch (reason) {
      setError(
        reason instanceof Error
          ? reason.message
          : t('users.delete-failed', '成员删除失败')
      )
    } finally {
      setBusy(null)
    }
  }
  async function review(request: CloudAccessRequest, decision: 'approved' | 'rejected') {
    setBusy(request.id)
    setError(null)
    try {
      await client.reviewAccessRequest(request.id, decision)
      await refresh()
      onChanged?.()
    } catch (reason) {
      setError(
        reason instanceof Error
          ? reason.message
          : t('users.request-failed', '访问申请处理失败')
      )
    } finally {
      setBusy(null)
    }
  }
  const visibleUsers = useMemo(
    () =>
      users.filter(
        user =>
          (!query.trim() || user.username.toLowerCase().includes(query.trim().toLowerCase())) &&
          (status === 'all' || (status === 'disabled' ? user.disabled : !user.disabled))
      ),
    [query, status, users]
  )
  if (loading)
    return (
      <LoadingState title={t('users.loading', '正在读取成员')} className="min-h-24 border-0 p-3" />
    )
  if (error && !users.length)
    return (
      <ErrorState
        title={t('users.read-failed', '成员列表读取失败')}
        description={error}
        className="min-h-24 border-0 p-3 text-red-700"
      />
    )
  return (
    <section aria-label={t('users.title', '成员管理')}>
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2 border-b border-[var(--border-subtle)] pb-2">
        <div role="tablist" aria-label={t('users.title', '成员管理')} className="flex gap-2">
          <Button
            type="button"
            role="tab"
            aria-selected={tab === 'joined'}
            variant={tab === 'joined' ? 'default' : 'ghost'}
            className={
              tab === 'joined'
                ? 'rounded bg-[var(--primary)] px-3 py-1.5 text-xs text-white'
                : 'rounded px-3 py-1.5 text-xs text-[var(--on-surface-variant)] hover:bg-[var(--surface-container)]'
            }
            onClick={() => setTab('joined')}
          >
            {t('users.title', '已加入成员')}
          </Button>
          <Button
            type="button"
            role="tab"
            aria-selected={tab === 'pending'}
            variant={tab === 'pending' ? 'default' : 'ghost'}
            className={
              tab === 'pending'
                ? 'rounded bg-[var(--primary)] px-3 py-1.5 text-xs text-white'
                : 'rounded px-3 py-1.5 text-xs text-[var(--on-surface-variant)] hover:bg-[var(--surface-container)]'
            }
            onClick={() => setTab('pending')}
          >
            {t('users.requests', '待审核')}
            {requests.length ? (
              <span className="ml-1 rounded-full bg-white/25 px-1.5 text-[10px]">{requests.length}</span>
            ) : null}
          </Button>
        </div>
        <Button
          type="button"
          variant="default"
          onClick={() => setAdding(true)}
          className="rounded-lg bg-[var(--primary)] px-3 py-2 text-xs font-medium text-white transition hover:brightness-110"
        >
          {t('users.add', '添加用户')}
        </Button>
      </div>

      {tab === 'pending' ? (
        requests.length ? (
          <ul className="space-y-2">
            {requests.map(request => (
              <li
                key={request.id}
                className="rounded border border-[var(--border-subtle)] bg-[var(--surface-container)] p-3"
              >
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div>
                    <p className="text-sm font-medium">
                      {request.display_name} · {request.email}
                    </p>
                    <p className="mt-1 text-xs text-[var(--on-surface-variant)]">
                      {request.reason || t('users.no-reason', '未填写申请理由')}
                    </p>
                  </div>
                  <div className="flex gap-2">
                    <Button
                      type="button"
                      variant="secondary"
                      disabled={busy === request.id}
                      onClick={() => void review(request, 'approved')}
                      className="rounded border border-emerald-300 px-2 py-1 text-xs text-emerald-700 transition hover:bg-emerald-50 disabled:opacity-50"
                    >
                      {t('users.approve', '通过')}
                    </Button>
                    <Button
                      type="button"
                      variant="danger"
                      disabled={busy === request.id}
                      onClick={() => void review(request, 'rejected')}
                      className="rounded border border-red-300 px-2 py-1 text-xs text-red-700 transition hover:bg-red-50 disabled:opacity-50"
                    >
                      {t('users.reject', '拒绝')}
                    </Button>
                  </div>
                </div>
              </li>
            ))}
          </ul>
        ) : (
          <p role="status" className="py-5 text-xs text-[var(--on-surface-variant)]">
            {t('users.none-pending', '暂无待审核申请。')}
          </p>
        )
      ) : (
        <>
          <div className="mb-3 flex flex-wrap gap-2">
            <Input
              aria-label={t('users.search', '搜索成员')}
              value={query}
              onValueChange={setQuery}
              placeholder={t('users.search', '搜索用户名')}
              className="min-w-48 flex-1 rounded border border-[var(--border-subtle)] bg-[var(--surface)] px-3 py-2 text-sm"
            />
            <Select
              value={status}
              onValueChange={value => setStatus(value as typeof status)}
            >
              <SelectItem value="all">{t('users.all-statuses', '全部状态')}</SelectItem>
              <SelectItem value="active">{t('users.active', '正常')}</SelectItem>
              <SelectItem value="disabled">{t('users.disabled', '已停用')}</SelectItem>
            </Select>
          </div>
          {users.length ? (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[560px] text-left text-sm">
                <thead>
                  <tr className="border-b border-[var(--border-subtle)] text-xs text-[var(--on-surface-variant)]">
                    <th className="px-3 py-2">{t('users.member', '成员')}</th>
                    <th className="px-3 py-2">{t('users.role', '角色')}</th>
                    <th className="px-3 py-2">{t('users.status', '状态')}</th>
                    <th className="sticky right-0 bg-[var(--surface)] px-3 py-2 text-right">
                      {t('users.actions', '操作')}
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {visibleUsers.map(user => (
                    <tr key={user.id} className="border-b border-[var(--border-subtle)]">
                      <td className="px-3 py-3 font-medium">{user.username}</td>
                      <td className="px-3 py-3 text-[var(--on-surface-variant)]">
                        {user.role === 'admin'
                          ? t('users.admin', '管理员')
                          : t('users.standard', '普通用户')}
                      </td>
                      <td className="px-3 py-3 text-[var(--on-surface-variant)]">
                        {user.disabled ? t('users.disabled', '已停用') : t('users.active', '正常')}
                      </td>
                      <td className="sticky right-0 bg-[var(--surface)] px-3 py-3 text-right whitespace-nowrap">
                        <Button
                          type="button"
                          variant="link"
                          disabled={user.role === 'admin'}
                          onClick={() => setEditing(user)}
                          className="mr-3 text-xs text-[var(--on-surface)] underline disabled:text-[var(--on-surface-variant)]"
                        >
                          {t('users.edit', '编辑')}
                        </Button>
                        {user.role === 'user' ? (
                          <Button
                            type="button"
                            variant="link"
                            disabled={busy === user.id}
                            onClick={() => void remove(user)}
                            className="text-xs text-[var(--error)] underline disabled:opacity-50"
                          >
                            {t('users.delete', '删除')}
                          </Button>
                        ) : (
                          <span className="text-xs text-[var(--on-surface-variant)]">
                            {t('users.protected', '受保护')}
                          </span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <EmptyState
              title={t('users.empty', '暂无云端成员')}
              className="min-h-24 border-0 p-4 text-[var(--on-surface-variant)]"
            />
          )}
          {users.length && !visibleUsers.length ? (
            <p role="status" className="py-5 text-sm text-[var(--on-surface-variant)]">
              {t('users.no-match', '没有匹配的成员。')}
            </p>
          ) : null}
        </>
      )}

      {editing && (
        <div className="mt-3 rounded border border-[var(--border-subtle)] bg-[var(--surface-container)]">
          <CloudUserForm
            client={client}
            user={editing}
            onSaved={() => {
              setEditing(null)
              void refresh()
              onChanged?.()
            }}
          />
        </div>
      )}
      {adding && (
        <div className="cloud-modal-scrim" role="presentation">
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby="user-form-title"
            className="cloud-dialog"
          >
            <Button
              type="button"
              variant="ghost"
              className="cloud-modal-close"
              onClick={() => setAdding(false)}
              aria-label={t('cancel', '关闭')}
            >
              ×
            </Button>
            <CloudUserForm
              client={client}
              onSaved={() => {
                setAdding(false)
                void refresh()
                onChanged?.()
              }}
            />
          </div>
        </div>
      )}
      {error ? (
        <p role="alert" className="mt-2 text-sm text-[var(--error)]">
          {error}
        </p>
      ) : null}
    </section>
  )
}
