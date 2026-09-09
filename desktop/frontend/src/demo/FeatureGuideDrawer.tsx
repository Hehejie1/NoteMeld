import { useEffect, useRef, type ReactNode } from 'react'
import { BookOpenCheck, Code2, Database, ExternalLink, X } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { ScrollArea } from '@/components/ui/scroll-area'
import { useFeatureGuide } from './FeatureGuideContext'

const EvidenceList = ({ title, icon, items }: { title: string; icon: ReactNode; items: Array<{ label: string; path: string; section?: string }> }) => (
  <section className="space-y-2">
    <h3 className="flex items-center gap-2 text-sm font-semibold text-on-surface">{icon}{title}</h3>
    <div className="space-y-2">
      {items.map(item => (
        <div key={`${item.path}-${item.section || ''}`} className="rounded-xl bg-surface-container-low p-3">
          <div className="text-xs font-medium text-on-surface">{item.label}</div>
          <code className="mt-1 block break-all text-[11px] leading-5 text-on-surface-variant">{item.path}{item.section ? ` · ${item.section}` : ''}</code>
        </div>
      ))}
    </div>
  </section>
)

export const FeatureGuideDrawer = () => {
  const { selectedGuide, closeGuide, executeSelectedFeature } = useFeatureGuide()
  const closeButtonRef = useRef<HTMLButtonElement>(null)

  useEffect(() => {
    if (!selectedGuide) return
    closeButtonRef.current?.focus()
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') closeGuide()
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [closeGuide, selectedGuide])

  if (!selectedGuide) return null

  return (
    <div className="fixed inset-0 z-[110] bg-black/20" onMouseDown={event => event.target === event.currentTarget && closeGuide()}>
      <aside role="dialog" aria-modal="true" aria-labelledby="feature-guide-title" className="absolute inset-y-0 right-0 flex w-full max-w-[520px] flex-col border-l border-border-subtle bg-white shadow-2xl">
        <header className="flex items-start justify-between border-b border-border-subtle px-6 py-5">
          <div className="pr-4">
            <div className="mb-1 text-xs font-medium text-primary">功能讲解 · 需求与代码双重依据</div>
            <h2 id="feature-guide-title" className="text-xl font-bold text-on-surface">{selectedGuide.title}</h2>
            <p className="mt-1 text-sm leading-6 text-on-surface-variant">{selectedGuide.summary}</p>
          </div>
          <button ref={closeButtonRef} type="button" className="rounded-xl p-2 hover:bg-surface-container" onClick={closeGuide} aria-label="关闭功能讲解"><X className="h-5 w-5" /></button>
        </header>
        <ScrollArea className="min-h-0 flex-1">
          <div className="space-y-6 px-6 py-5">
            <section className="rounded-2xl bg-primary-light p-4">
              <h3 className="text-sm font-semibold text-primary-strong">它解决什么问题</h3>
              <p className="mt-2 text-sm leading-6 text-on-surface">{selectedGuide.userValue}</p>
            </section>
            <section>
              <h3 className="mb-2 text-sm font-semibold text-on-surface">当前行为</h3>
              <ul className="space-y-2 text-sm leading-6 text-on-surface-variant">
                {selectedGuide.behavior.map(item => <li key={item} className="flex gap-2"><span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-primary" />{item}</li>)}
              </ul>
            </section>
            <EvidenceList title="产品依据" icon={<BookOpenCheck className="h-4 w-4 text-primary" />} items={selectedGuide.productEvidence} />
            <EvidenceList title="代码依据" icon={<Code2 className="h-4 w-4 text-primary" />} items={selectedGuide.codeEvidence} />
            <section>
              <h3 className="mb-2 flex items-center gap-2 text-sm font-semibold text-on-surface"><Database className="h-4 w-4 text-primary" />数据与状态</h3>
              <div className="flex flex-wrap gap-2">{selectedGuide.dataAndStates.map(item => <span key={item} className="rounded-full border border-border-subtle px-3 py-1 text-xs text-on-surface-variant">{item}</span>)}</div>
            </section>
            <section className="rounded-2xl border border-amber-200 bg-amber-50 p-4">
              <h3 className="text-sm font-semibold text-amber-900">静态演示限制</h3>
              <p className="mt-2 text-sm leading-6 text-amber-900/80">{selectedGuide.demoLimit}</p>
            </section>
          </div>
        </ScrollArea>
        <footer className="flex items-center justify-end gap-3 border-t border-border-subtle px-6 py-4">
          <Button variant="outline" onClick={closeGuide}>关闭</Button>
          <Button onClick={executeSelectedFeature}>执行此功能 <ExternalLink className="ml-2 h-4 w-4" /></Button>
        </footer>
      </aside>
    </div>
  )
}
