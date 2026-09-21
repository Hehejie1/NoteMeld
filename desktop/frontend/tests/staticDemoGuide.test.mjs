import assert from 'node:assert/strict'

const { decideFeatureGuideAction, createDeferredFeatureAction } = await import('../src/demo/featureGuidePolicy.ts').catch(() => ({}))
const { featureGuideCatalog } = await import('../src/demo/featureGuideCatalog.ts').catch(() => ({}))

assert.equal(typeof decideFeatureGuideAction, 'function', 'guide event policy must be independently testable')
assert.equal(decideFeatureGuideAction({ guideMode: false, button: 0 }), 'execute')
assert.equal(decideFeatureGuideAction({ guideMode: true, button: 0 }), 'explain')
assert.equal(decideFeatureGuideAction({ guideMode: false, button: 2 }), 'explain')

let executions = 0
const deferred = createDeferredFeatureAction(() => { executions += 1 })
deferred.execute()
deferred.execute()
assert.equal(executions, 1, 'deferred original action must execute at most once')

for (const id of ['nav-new-note', 'nav-styles', 'nav-wiki', 'nav-settings', 'nav-about', 'composer-submit', 'wiki-view-mode', 'styles-create', 'settings-model', 'settings-transcriber', 'settings-download', 'about-update']) {
  const guide = featureGuideCatalog[id]
  assert.ok(guide, `guide catalog must include ${id}`)
  assert.ok(guide.productEvidence.length > 0, `${id} must cite product evidence`)
  assert.ok(guide.codeEvidence.length > 0, `${id} must cite code evidence`)
  for (const evidence of [...guide.productEvidence, ...guide.codeEvidence]) {
    assert.doesNotMatch(evidence.path, /^\//, `${id} evidence paths must be repository-relative`)
  }
}
