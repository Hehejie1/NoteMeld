import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { test } from 'node:test'
import path from 'node:path'

const root = path.resolve(new URL('..', import.meta.url).pathname)
const app = await readFile(path.join(root, 'src/App.tsx'), 'utf8')
const mobile = await readFile(path.join(root, 'src/pages/MobilePage/index.tsx'), 'utf8')
const cloud = await readFile(path.join(root, 'src/pages/CloudPage/index.tsx'), 'utf8')
const cloudSessionPanel = await readFile(path.join(root, 'src/components/CloudSessionPanel/CloudSessionPanel.tsx'), 'utf8')
const capabilities = await readFile(path.join(root, 'src/pages/CapabilityCenter/index.tsx'), 'utf8')
const settingsLayout = await readFile(path.join(root, 'src/layouts/SettingLayout.tsx'), 'utf8')
const composer = await readFile(path.join(root, 'src/pages/HomePage/components/ChatComposer.tsx'), 'utf8')
const home = await readFile(path.join(root, 'src/pages/HomePage/Home.tsx'), 'utf8')

test('new product routes are registered in the formal app', () => {
  for (const route of ['/new', '/notes/:taskId', '/applications', '/settings', '/cloud', '/mobile/*']) {
    assert.match(app, new RegExp(`path=["']${route.replace(/[/*:?]/g, '\\$&')}["']`), route)
  }
})

test('mobile screens provide required stateful interactions', () => {
  for (const token of ['mobile-iphone-shell', 'createAgentSession', 'startAgentTurn', 'setPermission', 'mobile-bottom-sheet', 'notemeld-font-size', 'navigator.clipboard', 'window.confirm']) {
    assert.match(mobile, new RegExp(token), token)
  }
})

test('mobile web surface uses the real projection and browser storage instead of seeded business data', () => {
  for (const token of ['getMobileProjection', 'createMobileMemory', 'refreshProjection', 'refreshStorage', 'localStorage.removeItem']) {
    assert.match(mobile, new RegExp(token), token)
  }
  assert.doesNotMatch(mobile, /const memorySeed\s*=/)
  assert.doesNotMatch(mobile, /cache:\s*4\.34/)
  assert.doesNotMatch(mobile, /检查系统架构.*整理研究报告.*云端项目规划/)
  assert.doesNotMatch(mobile, /架构分析报告.*风险清单.*Workspace 引用/)
})

test('cloud views share a header and existing CloudClient-backed controls', () => {
  for (const token of ['CloudHeader', 'cloudNavigation', 'CloudFocusedView', 'cloud-profile-modal', 'CloudSessionPanel', 'CloudUserList', 'CloudDeviceList', 'CloudModelList', 'CloudPairingPanel']) {
    assert.match(cloud, new RegExp(token), token)
  }
})

test('cloud sessions expose file, model and full-access composer controls', () => {
  for (const token of ['attachment', 'model', 'fullAccess', 'commandInput', 'controller.send']) {
    assert.match(cloudSessionPanel, new RegExp(token.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')), token)
  }
})

test('desktop D06 exposes one capability center for plugins, skills, connectors and applications', () => {
  for (const token of ['CapabilityTab', 'plugins', 'skills', 'connectors', 'applications', 'Plugins', 'ApplicationList']) {
    assert.match(capabilities, new RegExp(token), token)
  }
})

test('desktop D09 keeps setting navigation separate from the content outlet', () => {
  assert.match(settingsLayout, /desktop-settings-sidebar/)
  assert.match(settingsLayout, /<Outlet\s*\/>/)
})

test('desktop D01 and D03 retain the shared agent composer and split workspace panels', () => {
  for (const token of ['workspace', 'workspaceRefs', 'effectiveContextRefs', 'workspace_id', 'modelOpen', 'upload', 'submitChat', 'startAgentTurn', 'streamAgentEvents', 'resolveAgentApproval']) {
    assert.match(composer.toLowerCase(), new RegExp(token.toLowerCase()), token)
  }
  for (const token of ['ChatComposer layout="hero"', 'ChatComposer layout="bottom"', 'PanelRightOpen', 'WhiteboardPanel']) {
    assert.match(home, new RegExp(token.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')), token)
  }
})
