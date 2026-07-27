import type { EvidenceAnchor, IngestionSourceAsset } from '@/services/ingestion'

type EvidenceSourceDrawerProps = {
  anchor: EvidenceAnchor | null
  source: IngestionSourceAsset | null
  onClose: () => void
}

export default function EvidenceSourceDrawer({
  anchor,
  source,
  onClose,
}: EvidenceSourceDrawerProps) {
  if (!anchor) return null

  return (
    <aside className="fixed inset-y-0 right-0 z-50 flex w-full max-w-xl flex-col border-l border-border-subtle bg-white shadow-2xl">
      <div className="flex items-center justify-between border-b border-border-subtle px-5 py-4">
        <div>
          <h2 className="text-sm font-semibold text-on-surface">原始来源</h2>
          <p className="mt-1 text-xs text-on-surface-variant">{source?.file_name || '未知文件'}</p>
        </div>
        <button
          type="button"
          onClick={onClose}
          className="rounded-lg px-2 py-1 text-sm text-on-surface-variant hover:bg-surface"
        >
          关闭
        </button>
      </div>

      <div className="min-h-0 flex-1 space-y-4 overflow-auto p-5">
        {source?.file_url && (
          <a
            href={source.file_url}
            target="_blank"
            rel="noreferrer"
            className="inline-flex rounded-lg bg-primary px-3 py-2 text-sm font-medium text-white"
          >
            打开源文件
          </a>
        )}
        <div className="rounded-2xl border border-border-subtle bg-surface p-4">
          <div className="mb-2 text-xs font-semibold text-on-surface-variant">Evidence Anchor</div>
          <dl className="grid grid-cols-2 gap-3 text-sm">
            <div>
              <dt className="text-on-surface-variant">page_number</dt>
              <dd className="font-mono text-on-surface">{anchor.page_number || '-'}</dd>
            </div>
            <div>
              <dt className="text-on-surface-variant">bbox</dt>
              <dd className="font-mono text-on-surface">{anchor.bbox?.join(', ') || '-'}</dd>
            </div>
          </dl>
        </div>
        <blockquote className="rounded-2xl border-l-4 border-primary bg-primary-light p-4 text-sm leading-6 text-on-surface">
          {anchor.text_quote || '无引用文本'}
        </blockquote>
      </div>
    </aside>
  )
}
