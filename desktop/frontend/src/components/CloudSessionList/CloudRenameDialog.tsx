import { useEffect, useState } from 'react'
import { useCloudLocale } from '../../pages/CloudPage/cloudLocale'
import { Button, Input } from '@notemeld/ui-web'

// 会话重命名中间弹窗，参考图二：大标题、副标题、单个输入框、底部取消/保存。
export function CloudRenameDialog({
  title,
  onCancel,
  onSave,
}: {
  title: string
  onCancel: () => void
  onSave: (nextTitle: string) => Promise<void>
}) {
  const { t } = useCloudLocale()
  const [value, setValue] = useState(title)
  const [saving, setSaving] = useState(false)
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onCancel()
    }
    document.addEventListener('keydown', onKeyDown)
    return () => document.removeEventListener('keydown', onKeyDown)
  }, [onCancel])
  async function submit(event: React.FormEvent) {
    event.preventDefault()
    const next = value.trim()
    if (!next || saving) return
    setSaving(true)
    try {
      await onSave(next)
    } finally {
      setSaving(false)
    }
  }
  return (
    <div className="cloud-modal-scrim" role="presentation">
      <form
        role="dialog"
        aria-modal="true"
        aria-labelledby="cloud-rename-title"
        onSubmit={submit}
        className="w-[min(100%,28rem)] rounded-2xl border border-[var(--border-subtle)] bg-[var(--surface-container-lowest)] p-6 shadow-2xl"
      >
        <h1 id="cloud-rename-title" className="text-2xl font-bold">
          {t('session.rename-title', '重命名聊天')}
        </h1>
        <p className="mt-2 text-sm text-[var(--on-surface-variant)]">
          {t('session.rename-subtitle', '保持简短且易于识别')}
        </p>
        <Input
          autoFocus
          value={value}
          onValueChange={setValue}
          maxLength={200}
          className="mt-5 w-full rounded-lg border-2 border-[var(--primary)] bg-transparent px-4 py-3 text-sm outline-none"
        />
        <div className="mt-6 flex justify-end gap-3">
          <Button
            type="button"
            variant="outline"
            onClick={onCancel}
            className="rounded-xl border-[var(--border-subtle)] px-6 py-2.5 text-sm font-medium hover:bg-[var(--surface-container)]"
          >
            {t('cancel', '取消')}
          </Button>
          <Button
            type="submit"
            disabled={saving || !value.trim()}
            variant="secondary"
            className="rounded-xl bg-white px-6 py-2.5 text-sm font-semibold text-black shadow disabled:opacity-50"
          >
            {t('save', '保存')}
          </Button>
        </div>
      </form>
    </div>
  )
}
