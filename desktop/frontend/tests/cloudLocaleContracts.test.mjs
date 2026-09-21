import assert from 'node:assert/strict'
import fs from 'node:fs'
import test from 'node:test'

const locale = fs.readFileSync(new URL('../src/pages/CloudPage/cloudLocale.tsx', import.meta.url), 'utf8')
const modelList = fs.readFileSync(new URL('../src/components/CloudModelList/CloudModelList.tsx', import.meta.url), 'utf8')
const modelForm = fs.readFileSync(new URL('../src/components/CloudModelForm/CloudModelForm.tsx', import.meta.url), 'utf8')
const cloudPage = fs.readFileSync(new URL('../src/pages/CloudPage/index.tsx', import.meta.url), 'utf8')
const approvalList = fs.readFileSync(new URL('../src/components/CloudApprovalList/CloudApprovalList.tsx', import.meta.url), 'utf8')
const userList = fs.readFileSync(new URL('../src/components/CloudUserList/CloudUserList.tsx', import.meta.url), 'utf8')
const userForm = fs.readFileSync(new URL('../src/components/CloudUserForm/CloudUserForm.tsx', import.meta.url), 'utf8')
const sessionList = fs.readFileSync(new URL('../src/components/CloudSessionList/CloudSessionList.tsx', import.meta.url), 'utf8')
const sessionPanel = fs.readFileSync(new URL('../src/components/CloudSessionPanel/CloudSessionPanel.tsx', import.meta.url), 'utf8')

test('Cloud model list keeps user-visible English states in the locale catalog', () => {
  for (const key of [
    'models.default',
    'models.credential-unreadable',
    'models.credential-repair-required',
    'models.api-key-repair',
    'models.credential-repair-help',
    'models.api-key-repair-placeholder',
    'models.credential-unavailable',
    'models.credential-saved',
    'models.credential-missing',
    'models.saved-count',
    'models.close',
  ]) {
    assert.match(locale, new RegExp(`['"]${key.replace('.', '\\.')}`))
  }
  assert.match(modelList, /models\.credential-unreadable/)
  assert.match(modelList, /models\.saved-count/)
  assert.doesNotMatch(modelList, /setNotice\('模型已保存/)
  assert.match(modelForm, /const defaultName = t\('models\.provider-volcengine'/)
  assert.match(modelForm, /const \[preset, setPreset\]/)
  assert.match(modelForm, /value=\{preset\} onChange=/)
  assert.match(modelForm, /credentialNeedsRepair/)
  assert.match(modelForm, /models\.credential-repair-required/)
  for (const key of ['cloud.home-label', 'cloud.navigation', 'cloud.theme-toggle', 'workbench.load-failed']) {
    assert.match(locale, new RegExp(`['"]${key.replace('.', '\\.')}`))
    assert.match(cloudPage, new RegExp(`t\\('${key.replace('.', '\\.')}'`))
  }
})

test('Chinese fallback copy does not leak English error states', () => {
  for (const source of [approvalList, userList, userForm]) {
    assert.doesNotMatch(source, /Unable to (load|resolve|save|delete|review)/)
  }
})

test('Cloud session errors are localized instead of exposing backend English', () => {
  for (const key of ['session.transport-failed', 'session.provider-unavailable', 'session.device-inactive', 'cloud.permission-denied', 'cloud.request-failed', 'cloud.config-conflict']) {
    assert.match(locale, new RegExp(`['"]${key.replace('.', '\\.')}`))
  }
  assert.match(locale, /function localizeCloudError/)
  assert.match(sessionList, /localizeCloudError\(error\.message, t\)/)
  assert.match(sessionPanel, /localizeCloudError\(error\.message, t\)/)
  assert.match(sessionPanel, /localizeCloudError\(reason instanceof Error \? reason\.message : 'send failed', t\)/)
})
