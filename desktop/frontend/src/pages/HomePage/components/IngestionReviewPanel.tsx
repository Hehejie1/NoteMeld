import { useEffect, useState } from 'react'
import { AlertTriangle, CheckCircle2, Database, FileSearch, Layers3, Quote } from 'lucide-react'

import {
  getIngestionChunks,
  getIngestionEvidence,
  getIngestionReport,
  getIngestionSource,
  type EvidenceAnchor,
  type IngestionSourceAsset,
  type IngestionParseReport,
  type KnowledgeChunk,
} from '@/services/ingestion'
import { ScrollArea } from '@/components/ui/scroll-area'
import EvidenceSourceDrawer from '@/pages/HomePage/components/EvidenceSourceDrawer'

type IngestionReviewPanelProps = {
  taskId: string
}

const formatPercent = (value?: number) => {
  if (typeof value !== 'number') return '未知'
  return `${Math.round(value * 100)}%`
}

const compactText = (text: string, maxLength = 180) => {
  if (!text) return '无文本'
  return text.length > maxLength ? `${text.slice(0, maxLength)}…` : text
}

export default function IngestionReviewPanel({ taskId }: IngestionReviewPanelProps) {
  const [report, setReport] = useState<IngestionParseReport | null>(null)
  const [evidence, setEvidence] = useState<EvidenceAnchor[]>([])
  const [chunks, setChunks] = useState<KnowledgeChunk[]>([])
  const [source, setSource] = useState<IngestionSourceAsset | null>(null)
  const [selectedAnchor, setSelectedAnchor] = useState<EvidenceAnchor | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    if (!taskId) {
      setReport(null)
      setEvidence([])
      setChunks([])
      setSource(null)
      setSelectedAnchor(null)
      setError('')
      return
    }

    let canceled = false
    setLoading(true)
    setError('')

    Promise.all([
      getIngestionReport(taskId),
      getIngestionEvidence(taskId),
      getIngestionChunks(taskId),
      getIngestionSource(taskId),
    ])
      .then(([nextReport, nextEvidence, nextChunks, nextSource]) => {
        if (canceled) return
        setReport(nextReport)
        setEvidence(nextEvidence)
        setChunks(nextChunks)
        setSource(nextSource)
      })
      .catch(err => {
        if (canceled) return
        setReport(null)
        setEvidence([])
        setChunks([])
        setSource(null)
        setError(err?.msg || '解析报告加载失败')
      })
      .finally(() => {
        if (!canceled) setLoading(false)
      })

    return () => {
      canceled = true
    }
  }, [taskId])

  if (!taskId) {
    return (
      <div className="flex h-full items-center justify-center bg-surface px-6 text-center">
        <div className="max-w-sm rounded-2xl border border-dashed border-border-subtle bg-white p-6">
          <FileSearch className="mx-auto mb-3 h-8 w-8 text-on-surface-variant" />
          <h3 className="text-sm font-semibold text-on-surface">暂无可审阅文档</h3>
          <p className="mt-2 text-xs leading-5 text-on-surface-variant">
            请选择一篇已生成的上传文档笔记，再查看解析报告与证据链。
          </p>
        </div>
      </div>
    )
  }

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center bg-surface text-sm text-on-surface-variant">
        正在读取解析报告…
      </div>
    )
  }

  if (error) {
    return (
      <div className="flex h-full items-center justify-center bg-surface px-6">
        <div className="max-w-sm rounded-2xl border border-status-error/20 bg-status-error/5 p-6 text-center">
          <AlertTriangle className="mx-auto mb-3 h-8 w-8 text-status-error" />
          <h3 className="text-sm font-semibold text-status-error">解析报告不可用</h3>
          <p className="mt-2 text-xs leading-5 text-on-surface-variant">{error}</p>
        </div>
      </div>
    )
  }

  if (!report) {
    return null
  }

  const parserBackend = report.parser?.backend || report.parser?.name || 'unknown'
  const topEvidence = evidence.slice(0, 8)
  const topChunks = chunks.slice(0, 6)

  return (
    <ScrollArea className="h-full bg-surface">
      <div className="mx-auto max-w-5xl space-y-4 px-4 py-4 md:px-6 md:py-6">
        <section className="overflow-hidden rounded-3xl border border-border-subtle bg-white shadow-[0_18px_60px_rgba(15,23,42,0.06)]">
          <div className="border-b border-border-subtle/70 bg-gradient-to-r from-slate-950 to-slate-800 px-5 py-5 text-white">
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div>
                <div className="mb-2 inline-flex items-center gap-1.5 rounded-full bg-white/10 px-2.5 py-1 text-[11px] font-medium text-white/80">
                  <FileSearch className="h-3.5 w-3.5" />
                  Parse Report
                </div>
                <h2 className="text-xl font-semibold tracking-tight">{report.title || '未命名文档'}</h2>
                <p className="mt-1 text-xs text-white/60">task · {report.task_id}</p>
              </div>
              <div className="rounded-2xl bg-white/10 px-3 py-2 text-right">
                <div className="text-[11px] text-white/60">Parser Backend</div>
                <div className="font-mono text-sm">{parserBackend}</div>
              </div>
            </div>
          </div>

          <div className="grid gap-3 p-4 md:grid-cols-4">
            <MetricCard label="页数" value={report.page_count} icon={<FileSearch className="h-4 w-4" />} />
            <MetricCard label="证据锚点" value={report.evidence_count} icon={<Quote className="h-4 w-4" />} />
            <MetricCard label="知识切片" value={report.chunk_count} icon={<Layers3 className="h-4 w-4" />} />
            <MetricCard
              label="向量索引"
              value={report.vector_indexed ? '完成' : '未完成'}
              icon={<Database className="h-4 w-4" />}
              tone={report.vector_indexed ? 'success' : 'warning'}
            />
          </div>
        </section>

        {report.warnings?.length > 0 && (
          <section className="rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3">
            <div className="mb-2 flex items-center gap-2 text-sm font-semibold text-amber-800">
              <AlertTriangle className="h-4 w-4" />
              解析警告
            </div>
            <div className="flex flex-wrap gap-2">
              {report.warnings.map(warning => (
                <span key={warning} className="rounded-full bg-white px-2.5 py-1 font-mono text-[11px] text-amber-800">
                  {warning}
                </span>
              ))}
            </div>
          </section>
        )}

        <section className="grid gap-4 xl:grid-cols-[1fr_0.9fr]">
          <div className="rounded-2xl border border-border-subtle bg-white p-4">
            <div className="mb-3 flex items-center justify-between">
              <h3 className="text-sm font-semibold text-on-surface">证据锚点</h3>
              <span className="text-[11px] text-on-surface-variant">展示前 {topEvidence.length} 条</span>
            </div>
            <div className="space-y-3">
              {topEvidence.length ? topEvidence.map(anchor => (
                <article
                  key={anchor.id}
                  onClick={() => setSelectedAnchor(anchor)}
                  className="cursor-pointer rounded-xl border border-border-subtle/70 bg-surface px-3 py-3 transition-colors hover:border-primary/30 hover:bg-primary-light/40"
                >
                  <div className="mb-2 flex flex-wrap items-center gap-2 text-[11px] text-on-surface-variant">
                    <span className="rounded-full bg-white px-2 py-0.5">page {anchor.page_number || '-'}</span>
                    <span className="rounded-full bg-white px-2 py-0.5">{anchor.granularity || 'anchor'}</span>
                    <span className="rounded-full bg-white px-2 py-0.5">confidence {formatPercent(anchor.confidence)}</span>
                  </div>
                  <p className="text-sm leading-6 text-on-surface">{compactText(anchor.text_quote)}</p>
                </article>
              )) : (
                <EmptyLine text="暂无证据锚点" />
              )}
            </div>
          </div>

          <div className="rounded-2xl border border-border-subtle bg-white p-4">
            <div className="mb-3 flex items-center justify-between">
              <h3 className="text-sm font-semibold text-on-surface">知识切片</h3>
              <span className="text-[11px] text-on-surface-variant">展示前 {topChunks.length} 条</span>
            </div>
            <div className="space-y-3">
              {topChunks.length ? topChunks.map(chunk => (
                <article key={chunk.id} className="rounded-xl border border-border-subtle/70 bg-surface px-3 py-3">
                  <div className="mb-2 flex items-center justify-between gap-2">
                    <span className="font-mono text-[11px] text-on-surface-variant">chunk {chunk.chunk_index ?? '-'}</span>
                    <span className="rounded-full bg-white px-2 py-0.5 text-[11px] text-on-surface-variant">
                      anchors {chunk.anchor_ids?.length || 0}
                    </span>
                  </div>
                  <p className="text-sm leading-6 text-on-surface">{compactText(chunk.content, 220)}</p>
                </article>
              )) : (
                <EmptyLine text="暂无知识切片" />
              )}
            </div>
          </div>
        </section>

        <section className="rounded-2xl border border-border-subtle bg-white p-4">
          <div className="mb-3 flex items-center gap-2 text-sm font-semibold text-on-surface">
            <CheckCircle2 className="h-4 w-4 text-status-success" />
            解析质量
          </div>
          <pre className="max-h-52 overflow-auto rounded-xl bg-slate-950 p-3 text-xs leading-5 text-slate-100">
            {JSON.stringify(report.quality || {}, null, 2)}
          </pre>
        </section>
        <EvidenceSourceDrawer
          anchor={selectedAnchor}
          source={source}
          onClose={() => setSelectedAnchor(null)}
        />
      </div>
    </ScrollArea>
  )
}

function MetricCard({
  label,
  value,
  icon,
  tone = 'neutral',
}: {
  label: string
  value: string | number
  icon: JSX.Element
  tone?: 'neutral' | 'success' | 'warning'
}) {
  const toneClass =
    tone === 'success'
      ? 'bg-status-success/10 text-status-success'
      : tone === 'warning'
        ? 'bg-amber-100 text-amber-700'
        : 'bg-primary-light text-primary'

  return (
    <div className="rounded-2xl border border-border-subtle bg-surface px-4 py-3">
      <div className={`mb-3 flex h-8 w-8 items-center justify-center rounded-xl ${toneClass}`}>
        {icon}
      </div>
      <div className="text-[12px] text-on-surface-variant">{label}</div>
      <div className="mt-1 text-2xl font-semibold tracking-tight text-on-surface">{value}</div>
    </div>
  )
}

function EmptyLine({ text }: { text: string }) {
  return (
    <div className="rounded-xl border border-dashed border-border-subtle bg-surface px-3 py-6 text-center text-sm text-on-surface-variant">
      {text}
    </div>
  )
}
