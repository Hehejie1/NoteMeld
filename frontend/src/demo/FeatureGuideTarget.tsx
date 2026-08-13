import { cloneElement, isValidElement, type MouseEvent, type ReactElement } from 'react'
import { useFeatureGuide } from './FeatureGuideContext'
import { decideFeatureGuideAction } from './featureGuidePolicy'
import { isDemoMode } from './mode'

interface FeatureGuideTargetProps {
  featureId: string
  children: ReactElement<Record<string, unknown>>
  onExecute?: () => void
}

export const FeatureGuideTarget = ({ featureId, children, onExecute }: FeatureGuideTargetProps) => {
  const { guideMode, openGuide } = useFeatureGuide()
  if (!isDemoMode() || !isValidElement(children)) return children

  const originalOnClick = children.props.onClick as ((event: MouseEvent<HTMLElement>) => void) | undefined
  const originalClassName = children.props.className
  const className = guideMode
    ? typeof originalClassName === 'function'
      ? (...args: unknown[]) => `${originalClassName(...args)} outline outline-1 outline-offset-2 outline-primary/35`
      : `${String(originalClassName || '')} outline outline-1 outline-offset-2 outline-primary/35`
    : originalClassName

  return cloneElement(children, {
    'data-feature-guide': featureId,
    onClick: (event: MouseEvent<HTMLElement>) => {
      if (decideFeatureGuideAction({ guideMode, button: event.button }) === 'explain') {
        event.preventDefault()
        event.stopPropagation()
        openGuide(featureId, onExecute || (originalOnClick ? () => originalOnClick(event) : undefined))
        return
      }
      if (onExecute) onExecute()
      else originalOnClick?.(event)
    },
    onContextMenu: (event: MouseEvent<HTMLElement>) => {
      event.preventDefault()
      event.stopPropagation()
      openGuide(featureId, onExecute || (originalOnClick ? () => originalOnClick(event) : undefined))
    },
    className,
  })
}
