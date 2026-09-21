import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type PropsWithChildren } from 'react'
import { createDeferredFeatureAction } from './featureGuidePolicy'
import { getFeatureGuide, type FeatureGuideEntry } from './featureGuideCatalog'
import { isDemoMode } from './mode'

const delegatedTargets = [
  { selector: '[aria-label="发送"]', featureId: 'composer-submit' },
  { selector: 'a[href="/settings/model"]', featureId: 'settings-model' },
  { selector: 'a[href="/settings/transcriber"]', featureId: 'settings-transcriber' },
  { selector: 'a[href="/settings/download"]', featureId: 'settings-download' },
  { selector: 'a[href="/settings/data-migration"]', featureId: 'settings-migration' },
  { selector: 'a[href="/settings/usage"]', featureId: 'settings-usage' },
  { selector: 'a[href="/settings/monitor"]', featureId: 'settings-monitor' },
  { selector: 'a[href="/settings/mcp-servers"]', featureId: 'settings-mcp' },
  { selector: 'a[href="/settings/research-search"]', featureId: 'settings-research' },
] as const

interface FeatureGuideContextValue {
  guideMode: boolean
  setGuideMode(value: boolean): void
  selectedGuide: FeatureGuideEntry | null
  openGuide(featureId: string, execute?: () => void): void
  closeGuide(): void
  executeSelectedFeature(): void
}

const FeatureGuideContext = createContext<FeatureGuideContextValue | null>(null)

export const FeatureGuideProvider = ({ children }: PropsWithChildren) => {
  const [guideMode, setGuideMode] = useState(false)
  const [selectedGuide, setSelectedGuide] = useState<FeatureGuideEntry | null>(null)
  const [deferredAction, setDeferredAction] = useState<ReturnType<typeof createDeferredFeatureAction> | null>(null)
  const replayingRef = useRef(false)

  const closeGuide = useCallback(() => {
    setSelectedGuide(null)
    setDeferredAction(null)
  }, [])

  const openGuide = useCallback((featureId: string, execute?: () => void) => {
    const entry = getFeatureGuide(featureId)
    if (!entry) return
    setSelectedGuide(entry)
    setDeferredAction(() => createDeferredFeatureAction(execute))
  }, [])

  useEffect(() => {
    if (!isDemoMode()) return
    const resolveTarget = (event: Event) => {
      const element = event.target instanceof Element ? event.target : null
      if (!element) return null
      return delegatedTargets.find(target => element.closest(target.selector)) || null
    }
    const explain = (event: MouseEvent) => {
      if (replayingRef.current) return
      const target = resolveTarget(event)
      if (!target || (event.type === 'click' && !guideMode)) return
      const element = (event.target as Element).closest(target.selector) as HTMLElement | null
      if (!element) return
      event.preventDefault()
      event.stopPropagation()
      openGuide(target.featureId, () => {
        replayingRef.current = true
        element.click()
        replayingRef.current = false
      })
    }
    document.addEventListener('click', explain, true)
    document.addEventListener('contextmenu', explain, true)
    return () => {
      document.removeEventListener('click', explain, true)
      document.removeEventListener('contextmenu', explain, true)
    }
  }, [guideMode, openGuide])

  const executeSelectedFeature = useCallback(() => {
    deferredAction?.execute()
    closeGuide()
  }, [closeGuide, deferredAction])

  const value = useMemo(() => ({
    guideMode,
    setGuideMode,
    selectedGuide,
    openGuide,
    closeGuide,
    executeSelectedFeature,
  }), [guideMode, selectedGuide, openGuide, closeGuide, executeSelectedFeature])

  return <FeatureGuideContext.Provider value={value}>{children}</FeatureGuideContext.Provider>
}

export const useFeatureGuide = () => {
  const context = useContext(FeatureGuideContext)
  if (!context) throw new Error('useFeatureGuide must be used within FeatureGuideProvider')
  return context
}
