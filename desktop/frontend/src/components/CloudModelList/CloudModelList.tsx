import { useEffect, useState } from 'react'
import CloudClient, { type CatalogProvider } from '../../services/cloud'
import { CloudModelForm } from '../CloudModelForm'
import { EmptyState, ErrorState, LoadingState } from '../ui/feedback'
import { useCloudLocale } from '../../pages/CloudPage/cloudLocale'
import { Button, Checkbox, Badge } from '@notemeld/ui-web'

export function CloudModelList({
  client,
  refreshKey = 0,
  onCreated,
}: {
  client: CloudClient
  refreshKey?: number
  onCreated?: () => void
}) {
  const { t } = useCloudLocale()
  const [providers, setProviders] = useState<CatalogProvider[]>([])
  const [readOnly, setReadOnly] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [open, setOpen] = useState(false)
  const [editingProvider, setEditingProvider] = useState<CatalogProvider | null>(null)
  const [localRevision, setLocalRevision] = useState(0)
  const [notice, setNotice] = useState<string | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)

  useEffect(() => {
    let active = true
    setLoading(true)
    setError(null)
    void Promise.all([client.listCatalogProviders(), client.me().catch(() => null)])
      .then(([items, profile]) => {
        if (!active) return
        setProviders(items)
        setReadOnly(profile?.organization_role === 'member')
      })
      .catch(reason => {
        if (active) setError(reason instanceof Error ? reason.message : t('models.read-failed', '模型列表加载失败'))
      })
      .finally(() => {
        if (active) setLoading(false)
      })
    return () => {
      active = false
    }
  }, [client, refreshKey, localRevision])

  function fail(reason: unknown) {
    setActionError(reason instanceof Error ? reason.message : t('models.action-failed', '模型操作失败，请重试。'))
  }

  function toggleModelEnabled(providerId: string, rowId: string, enabled: boolean) {
    setActionError(null)
    // 乐观更新：禁用某模型时若其为默认则同时取消默认标记
    setProviders(current =>
      current.map(provider =>
        provider.id !== providerId
          ? provider
          : {
              ...provider,
              models: (provider.models ?? []).map(model =>
                model.id === rowId
                  ? { ...model, enabled, is_default: enabled ? model.is_default : false }
                  : model
              ),
            }
      )
    )
    void client
      .updateCatalogModel(rowId, { enabled })
      .then(() => {
        setNotice(t('models.updated', '模型已更新。'))
        setLocalRevision(value => value + 1)
      })
      .catch(reason => fail(reason))
  }

  if (loading) return <LoadingState title={t('models.reading', '正在加载云端模型')} className="min-h-24 border-0 p-3" />
  if (error)
    return (
      <ErrorState
        title={t('models.read-failed', '模型列表加载失败')}
        description={error}
        className="min-h-24 border-0 p-3 text-red-700"
      />
    )

  return (
    <section aria-labelledby="model-list-title">
      <div className="mb-2 flex items-center justify-between gap-3">
        <h2 id="model-list-title" className="text-base font-semibold">
          {t('models.configured', '已配置模型')}
        </h2>
        {!readOnly ? (
          <Button
            type="button"
            onClick={() => {
              setNotice(null)
              setActionError(null)
              setEditingProvider(null)
              setOpen(true)
            }}
            size="sm"
            className="rounded-lg px-3 py-2 text-xs font-medium transition hover:brightness-110"
          >
            {t('models.add', '添加模型')}
          </Button>
        ) : (
          <span className="text-xs text-[var(--muted)]">{t('models.read-only-tag', '只读')}</span>
        )}
      </div>
      {notice ? (
        <p
          role="status"
          className="mb-3 rounded border border-emerald-300/50 bg-emerald-500/10 px-3 py-2 text-sm text-emerald-700 dark:text-emerald-300"
        >
          {notice}
        </p>
      ) : null}
      {actionError ? <p role="alert" className="mb-3 rounded border border-[var(--error)]/40 bg-[var(--error)]/10 px-3 py-2 text-sm text-[var(--error)]">{actionError}</p> : null}
      {providers.length ? (
        <ul role="list" className="space-y-3">
          {providers.map(provider => {
            const providerModels = provider.models ?? []
            return (
              <li
                key={provider.id}
                className="rounded border border-[var(--border-subtle)] p-3"
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <p className="truncate text-sm font-semibold">
                      {provider.display_name}
                      <span className="ml-2 rounded bg-[var(--surface-container)] px-1.5 py-0.5 text-[10px] font-normal text-[var(--muted)]">{provider.vendor_id}</span>
                    </p>
                    <p className="mt-0.5 truncate text-xs text-[var(--on-surface-variant)]">
                      {provider.protocol} · {provider.base_url || '—'}
                    </p>
                    <p className="mt-0.5 text-xs">
                      <span className={provider.has_api_key ? 'text-emerald-700' : 'text-[var(--error)]'}>
                        {provider.has_api_key
                          ? t('models.credential-saved', '凭据已保存')
                          : t('models.credential-missing', '未配置凭据')}
                      </span>
                    </p>
                  </div>
                  {!readOnly ? (
                    <div className="flex shrink-0 items-center gap-1">
                      <Button type="button" variant="outline" size="sm" className="cloud-model-row-button" onClick={() => { setActionError(null); setEditingProvider(provider); setOpen(true) }}>{t('models.edit', '编辑')}</Button>
                      <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        className="cloud-model-row-button cloud-model-row-danger"
                        onClick={() => {
                          if (!window.confirm(t('models.delete-provider-confirm', '删除厂商将同时移除其下全部模型，确定继续？'))) return
                          setActionError(null)
                          void client.deleteCatalogProvider(provider.id).then(() => {
                            setNotice(t('models.deleted', '已删除。'))
                            setLocalRevision(value => value + 1)
                          }).catch(reason => fail(reason))
                        }}
                      >
                        {t('models.delete', '删除')}
                      </Button>
                    </div>
                  ) : null}
                </div>
                {providerModels.length ? (
                  <ul role="list" className="mt-2 space-y-1 border-t border-[var(--border-subtle)] pt-2">
                    {providerModels.map(model => (
                      <li key={model.id} className="flex items-center gap-2 text-sm">
                        <Checkbox
                          checked={model.enabled}
                          disabled={readOnly}
                          onCheckedChange={checked => toggleModelEnabled(provider.id, model.id, checked)}
                        />
                        <span className="min-w-0 flex-1 truncate">
                          {model.display_name}
                          <span className="ml-1 text-xs text-[var(--muted)]">{model.model_id}</span>
                          {model.is_default ? <Badge className="cloud-model-default-badge">{t('models.default', '默认')}</Badge> : null}
                        </span>
                        <span className="hidden w-24 shrink-0 text-right text-[10px] text-[var(--muted)] sm:block">{(model.context_window ?? 0).toLocaleString()}</span>
                        {model.test_status && model.test_status !== 'unknown' ? (
                          <span className={`shrink-0 text-[10px] ${model.test_status === 'ok' ? 'text-emerald-700' : model.test_status === 'failed' ? 'text-[var(--error)]' : 'text-[var(--muted)]'}`}>
                            {model.test_status === 'ok' ? t('models.test-ok-short', '连通') : model.test_status === 'failed' ? t('models.test-failed-short', '失败') : t('models.testing-short', '测试中')}
                          </span>
                        ) : null}
                        {!readOnly && !model.is_default ? (
                          <Button
                            type="button"
                            variant="outline"
                            size="sm"
                            className="cloud-model-row-button"
                            onClick={() => {
                              setActionError(null)
                              void client.setCatalogDefaultModel(model.id).then(() => {
                                setNotice(t('models.default-saved', '默认模型已更新。'))
                                setLocalRevision(value => value + 1)
                              }).catch(reason => fail(reason))
                            }}
                          >
                            {t('models.make-default', '设为默认')}
                          </Button>
                        ) : null}
                        {!readOnly ? (
                          <Button
                            type="button"
                            variant="outline"
                            size="sm"
                            className="cloud-model-row-button cloud-model-row-danger"
                            onClick={() => {
                              if (!window.confirm(t('models.delete-confirm', '确定删除此模型？'))) return
                              setActionError(null)
                              void client.deleteCatalogModel(model.id).then(() => {
                                setNotice(t('models.deleted', '模型已删除。'))
                                setLocalRevision(value => value + 1)
                              }).catch(reason => fail(reason))
                            }}
                          >
                            {t('models.remove', '移除')}
                          </Button>
                        ) : null}
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="mt-2 border-t border-[var(--border-subtle)] pt-2 text-xs text-[var(--muted)]">{t('models.no-models-under-provider', '该厂商下尚无模型。')}</p>
                )}
              </li>
            )
          })}
        </ul>
      ) : (
        <EmptyState
          title={t('models.empty', '尚未配置云端模型')}
          className="min-h-24 border-0 p-4 text-[var(--on-surface-variant)]"
        />
      )}
      {open ? (
        <div className="cloud-modal-scrim" role="presentation">
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby="model-form-title"
            className="cloud-dialog"
          >
            <Button
              type="button"
              variant="ghost"
              className="cloud-modal-close"
              onClick={() => setOpen(false)}
              aria-label={t('models.close', '关闭')}
            >
              ×
            </Button>
            <CloudModelForm
              client={client}
              providerToEdit={editingProvider ?? undefined}
              readOnly={readOnly}
              onCreated={() => {
                setOpen(false)
                setEditingProvider(null)
                setNotice(t('models.saved-count', '配置已保存，列表已刷新。'))
                setLocalRevision(value => value + 1)
                onCreated?.()
              }}
            />
          </div>
        </div>
      ) : null}
    </section>
  )
}
