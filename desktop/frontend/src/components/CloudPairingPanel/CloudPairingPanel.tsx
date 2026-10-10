import { useState } from 'react'
import CloudClient from '../../services/cloud'
import { useCloudLocale } from '../../pages/CloudPage/cloudLocale'
import { Button } from '../ui/button'
import { Input } from '../ui/input'

export function CloudPairingPanel({
  client,
  onPaired,
}: {
  client: CloudClient
  onPaired?: () => void
}) {
  const { t } = useCloudLocale()
  const [code, setCode] = useState('')
  const [deviceId, setDeviceId] = useState('')
  const [displayName, setDisplayName] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [message, setMessage] = useState<string | null>(null)
  async function start() {
    setBusy(true)
    setError(null)
    setMessage(null)
    try {
      const result = await client.startPairing()
      setCode(result.code)
      setMessage(t('pairing.code-created', '配对码已生成，请在要连接的设备上使用。'))
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : t('pairing.start-failed', '无法生成配对码'))
    } finally {
      setBusy(false)
    }
  }
  async function confirm() {
    setBusy(true)
    setError(null)
    setMessage(null)
    try {
      await client.confirmPairing(code, deviceId, 'web', displayName)
      setMessage(t('pairing.success', '设备已配对。'))
      onPaired?.()
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : t('pairing.confirm-failed', '无法确认配对'))
    } finally {
      setBusy(false)
    }
  }
  return (
    <section aria-labelledby="cloud-pairing-title" className="flex max-w-md flex-col gap-4 p-4">
      <div>
        <h2 id="cloud-pairing-title" className="text-lg font-semibold text-[var(--on-surface)]">
          {t('pairing.title', '添加设备')}
        </h2>
        <p className="text-sm text-[var(--on-surface-variant)]">
          {t('pairing.description', '使用短时有效的配对码连接另一台 NoteMeld 设备。')}
        </p>
      </div>
      <Button
        type="button"
        variant="secondary"
        disabled={busy}
        onClick={() => void start()}
        className="rounded border border-[var(--border-subtle)] bg-[var(--surface)] px-3 py-2 text-sm text-[var(--on-surface)] transition-colors hover:border-[var(--primary)] hover:bg-[var(--surface-container)]"
      >
        {busy ? t('pairing.generating', '生成中…') : t('pairing.generate', '生成配对码')}
      </Button>
      {code ? (
        <output
          aria-label="Pairing code"
          className="rounded bg-[var(--surface-container)] p-3 text-center font-mono text-xl tracking-widest text-[var(--on-surface)]"
        >
          {code}
        </output>
      ) : null}
      <div className="flex flex-col gap-2">
        <label htmlFor="pairing-code" className="text-sm font-medium text-[var(--on-surface)]">
          {t('pairing.code', '配对码')}
        </label>
        <Input
          id="pairing-code"
          value={code}
          onValueChange={setCode}
          className="rounded border border-[var(--border-subtle)] bg-[var(--surface)] px-3 py-2 text-[var(--on-surface)]"
        />
        <label htmlFor="pairing-device" className="text-sm font-medium text-[var(--on-surface)]">
          {t('pairing.device-id', '目标设备 ID')}
        </label>
        <Input
          id="pairing-device"
          required
          value={deviceId}
          onValueChange={setDeviceId}
          className="rounded border border-[var(--border-subtle)] bg-[var(--surface)] px-3 py-2 text-[var(--on-surface)]"
        />
        <label htmlFor="pairing-name" className="text-sm font-medium text-[var(--on-surface)]">
          {t('pairing.display-name', '显示名称')}
        </label>
        <Input
          id="pairing-name"
          required
          value={displayName}
          onValueChange={setDisplayName}
          className="rounded border border-[var(--border-subtle)] bg-[var(--surface)] px-3 py-2 text-[var(--on-surface)]"
        />
        <Button
          type="button"
          variant="default"
          disabled={busy || !code || !deviceId || !displayName}
          onClick={() => void confirm()}
          className="rounded bg-[var(--primary)] px-3 py-2 text-sm text-white transition hover:brightness-110 disabled:opacity-50"
        >
          {t('pairing.confirm', '确认配对')}
        </Button>
      </div>
      {message ? (
        <p role="status" className="text-sm text-[var(--on-surface-variant)]">
          {message}
        </p>
      ) : null}
      {error ? (
        <p role="alert" className="text-sm text-[var(--error)]">
          {error}
        </p>
      ) : null}
    </section>
  )
}
