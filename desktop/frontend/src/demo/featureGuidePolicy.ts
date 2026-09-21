export type FeatureGuideDecision = 'execute' | 'explain'

export const decideFeatureGuideAction = ({
  guideMode,
  button,
}: {
  guideMode: boolean
  button: number
}): FeatureGuideDecision => button === 2 || guideMode ? 'explain' : 'execute'

export const createDeferredFeatureAction = (action?: () => void) => {
  let executed = false
  return {
    execute: () => {
      if (executed) return
      executed = true
      action?.()
    },
  }
}
