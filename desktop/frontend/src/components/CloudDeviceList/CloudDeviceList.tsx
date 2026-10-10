import { useEffect, useState } from 'react'
import CloudClient, { CloudDevice, CloudDevicePermissions } from '../../services/cloud'
import { EmptyState, ErrorState, LoadingState } from '../ui/feedback'
import { Button } from '../ui/button'
import { Checkbox } from '../ui/checkbox'
import { useCloudLocale } from '../../pages/CloudPage/cloudLocale'
import { Settings } from 'lucide-react'
import { CloudPairingPanel } from '../CloudPairingPanel'
import { CloudGrantPanel } from '../CloudGrantPanel'

export function CloudDeviceList({ client, onRevoke }: { client: CloudClient; onRevoke?: (device: CloudDevice) => void }) {
  const { t } = useCloudLocale()
  const [devices, setDevices] = useState<CloudDevice[]>([])
  const [scope, setScope] = useState<'devices' | 'runtime'>('devices')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<Error | null>(null)
  const [busy, setBusy] = useState<string | null>(null)
  const [editing, setEditing] = useState<string | null>(null)
  const [pairingOpen, setPairingOpen] = useState(false)
  const [securityOpen, setSecurityOpen] = useState(false)
  const [permissions, setPermissions] = useState<CloudDevicePermissions>({ workspace_read: true, remote_execute: false, session_read: true, artifact_download: true, approval_required: true })
  const [permissionMessage, setPermissionMessage] = useState<string | null>(null)
  useEffect(() => {
    let active = true
    const refresh = () => { void client.listDevices().then(value => { if (active) setDevices(value as CloudDevice[]) }).catch(reason => { if (active) setError(reason instanceof Error ? reason : new Error(String(reason))) }).finally(() => { if (active) setLoading(false) }) }
    refresh()
    const timer = window.setInterval(refresh, 15000)
    return () => { active = false; window.clearInterval(timer) }
  }, [client])
  if (loading) return <LoadingState title={t('devices.reading', '正在读取设备')} className="min-h-24 border-0 p-3" aria-busy="true" />
  if (error) return <ErrorState role="alert" title={t('devices.read-failed', '设备列表读取失败')} description={error.message} className="min-h-24 border-0 p-3 text-[var(--error)]" />
  async function openPermissions(device: CloudDevice) { setEditing(device.id); setPermissionMessage(null); setBusy(device.id); try { setPermissions(await client.getDevicePermissions(device.id)) } catch (reason) { setPermissionMessage(reason instanceof Error ? reason.message : t('devices.permissions-read-failed', '无法读取设备权限')) } finally { setBusy(null) } }
  async function savePermissions(deviceId: string) { setBusy(deviceId); setPermissionMessage(null); try { await client.updateDevicePermissions(deviceId, permissions); setPermissionMessage(t('devices.permissions-saved', '设备权限已保存。')) } catch (reason) { setPermissionMessage(reason instanceof Error ? reason.message : t('devices.permissions-save-failed', '设备权限保存失败，请重试。')) } finally { setBusy(null) } }
  const permissionFields = [['workspace_read', t('devices.workspace-read', '访问 Workspace 文件')], ['session_read', t('devices.session-read', '读取云端会话')], ['artifact_download', t('devices.artifact-download', '下载产物')], ['remote_execute', t('devices.remote-execute', '远程执行')], ['approval_required', t('devices.approval-required', '高风险操作仍需审批')]] as const
  return <section>
    <div role="tablist" aria-label={t('devices.scope-tabs', '设备范围')} className="mb-3 flex items-center justify-between gap-2 border-b border-[var(--border-subtle)] pb-2">
      <div className="flex gap-2">
        <Button type="button" role="tab" aria-selected={scope === 'devices'} variant={scope === 'devices' ? 'default' : 'ghost'} className={scope === 'devices' ? 'rounded bg-[var(--primary)] px-3 py-1.5 text-xs text-white' : 'rounded px-3 py-1.5 text-xs text-[var(--on-surface-variant)] hover:bg-[var(--surface-container)]'} onClick={() => setScope('devices')}>{t('devices.scope-devices', '可信设备')}</Button>
        <Button type="button" role="tab" aria-selected={scope === 'runtime'} variant={scope === 'runtime' ? 'default' : 'ghost'} className={scope === 'runtime' ? 'rounded bg-[var(--primary)] px-3 py-1.5 text-xs text-white' : 'rounded px-3 py-1.5 text-xs text-[var(--on-surface-variant)] hover:bg-[var(--surface-container)]'} onClick={() => setScope('runtime')}>{t('devices.scope-runtime', '运行节点')}</Button>
      </div>
      <div className="flex items-center gap-2">
        <Button type="button" variant="secondary" size="icon" className="grid h-8 w-8 place-items-center rounded border border-[var(--border-subtle)] text-[var(--on-surface-variant)] transition-colors hover:bg-[var(--surface-container)]" aria-label={t('devices.security-title', '设备安全')} onClick={() => setSecurityOpen(true)}><Settings className="h-4 w-4" /></Button>
        <Button type="button" variant="default" className="rounded-lg bg-[var(--primary)] px-3 py-2 text-xs font-medium text-white transition hover:brightness-110" onClick={() => setPairingOpen(true)}>{t('pairing.title', '添加设备')}</Button>
      </div>
    </div>
    {scope === 'runtime' ? <EmptyState title={t('devices.runtime-empty', '暂无运行节点')} description={t('devices.runtime-empty-description', '当前 Cloud 数据模型仅包含可信用户设备，运行节点将在接入后显示。')} className="min-h-24 border-0 p-4 text-[var(--on-surface-variant)]" />
      : !devices.length ? <EmptyState title={t('devices.empty', '暂无已连接设备')} className="min-h-24 border-0 p-4 text-[var(--on-surface-variant)]" />
        : <ul role="list" aria-label={t('nav.devices', 'Connected devices')} className="space-y-2">{devices.map(device => <li key={device.id} className="rounded border border-[var(--border-subtle)] p-3 transition-colors hover:bg-[var(--surface-container)]"><div className="flex items-center justify-between gap-3"><div className="min-w-0"><p className="truncate text-sm font-medium text-[var(--on-surface)]">{device.display_name}</p><p className="text-xs text-[var(--on-surface-variant)]">{device.platform} · {device.online ? t('devices.online', '在线') : t('devices.offline', '离线')}</p>{device.connectivity?.lan_endpoints?.length ? <p className="truncate text-xs text-[var(--on-surface-variant)]">{t('devices.lan', '局域网')}：{device.connectivity.lan_endpoints.join(', ')}</p> : null}</div><div className="flex shrink-0 gap-2"><Button type="button" variant="secondary" disabled={busy === device.id} className="rounded border border-[var(--border-subtle)] px-2 py-1 text-xs text-[var(--on-surface)] transition-colors hover:bg-[var(--surface-container-high)] disabled:opacity-50" onClick={() => void openPermissions(device)}>{t('devices.permissions', '权限')}</Button><Button type="button" variant="danger" disabled={busy === device.id} className="rounded border border-red-300 px-2 py-1 text-xs text-red-600 transition-colors hover:bg-red-950/30 disabled:opacity-50" onClick={async () => { setBusy(device.id); setError(null); try { await client.revokeDevice(device.id); onRevoke?.(device); setDevices(items => items.filter(item => item.id !== device.id)) } catch (reason) { setError(reason instanceof Error ? reason : new Error(String(reason))) } finally { setBusy(null) } }}>{t('devices.revoke', '撤销')}</Button></div></div>{editing === device.id ? <fieldset className="mt-3 space-y-2 border-t border-[var(--border-subtle)] pt-3"><legend className="text-sm font-medium">{t('devices.permissions-title', '设备权限')}</legend>{permissionFields.map(([key, label]) => <label key={key} className="flex items-center gap-2 text-sm text-[var(--on-surface-variant)]"><Checkbox checked={permissions[key]} onCheckedChange={checked => setPermissions(current => ({ ...current, [key]: checked }))} />{label}</label>)}<div className="flex items-center gap-2"><Button type="button" variant="default" disabled={busy === device.id} onClick={() => void savePermissions(device.id)} className="rounded bg-[var(--primary)] px-3 py-1.5 text-xs text-white disabled:opacity-50">{busy === device.id ? t('devices.saving-permissions', '保存中…') : t('devices.save-permissions', '保存设备权限')}</Button><Button type="button" variant="secondary" onClick={() => setEditing(null)} className="rounded border border-[var(--border-subtle)] px-3 py-1.5 text-xs">{t('cancel', '取消')}</Button></div>{permissionMessage ? <p role="status" className="text-xs text-[var(--on-surface-variant)]">{permissionMessage}</p> : null}</fieldset> : null}</li>)}</ul>}
    {pairingOpen ? (
      <div className="cloud-modal-scrim" role="presentation">
        <div role="dialog" aria-modal="true" aria-labelledby="cloud-pairing-title" className="cloud-dialog">
          <Button type="button" variant="ghost" className="cloud-modal-close" onClick={() => setPairingOpen(false)} aria-label={t('cancel', '关闭')}>×</Button>
          <CloudPairingPanel client={client} onPaired={() => setPairingOpen(false)} />
        </div>
      </div>
    ) : null}
    {securityOpen ? (
      <div className="cloud-modal-scrim" role="presentation">
        <div role="dialog" aria-modal="true" aria-labelledby="cloud-security-title" className="cloud-dialog flex max-h-[80dvh] flex-col">
          <Button type="button" variant="ghost" className="cloud-modal-close" onClick={() => setSecurityOpen(false)} aria-label={t('cancel', '关闭')}>×</Button>
          <h2 id="cloud-security-title" className="px-5 pt-4 text-base font-semibold">{t('devices.security-title', '设备安全')}</h2>
          <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4">
            <p className="text-sm text-[var(--on-surface-variant)]">{t('devices.security-description', '一次性配对凭证短时有效，撤销后立即失效；配对、撤销和权限变更会进入审计日志。')}</p>
            <div className="mt-4 border-t border-[var(--border-subtle)] pt-3">
              <h3 className="mb-3 text-sm font-medium">{t('grants.title', '设备授权')}</h3>
              <CloudGrantPanel client={client} />
            </div>
          </div>
        </div>
      </div>
    ) : null}
  </section>
}
