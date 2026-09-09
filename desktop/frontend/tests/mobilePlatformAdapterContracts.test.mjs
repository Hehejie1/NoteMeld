import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { test } from 'node:test'
import path from 'node:path'

const root = path.resolve(new URL('../../..', import.meta.url).pathname)
const files = {
  android: 'android/src/main/kotlin/com/notemeld/mobile/MobileSurfaceState.kt',
  ios: 'ios/Sources/NoteMeldMobile/MobileSurfaceState.swift',
  harmony: 'harmony/entry/src/main/ets/model/MobileSurfaceState.ets',
}
const surfaces = {
  android: 'android/src/main/kotlin/com/notemeld/mobile/MobileSurface.kt',
  ios: 'ios/Sources/NoteMeldMobile/MobileSurface.swift',
  harmony: 'harmony/entry/src/main/ets/pages/MobileSurface.ets',
}

test('Android, iOS and Harmony expose the same mobile surface state contract', async () => {
  const sources = await Promise.all(Object.values(files).map(file => readFile(path.join(root, file), 'utf8')))
  for (const source of sources) {
    for (const token of ['HOME', 'SESSION', 'SETTINGS', 'MEMORY', 'STORAGE', 'drawer', 'sheet', 'sending', 'permission']) {
      assert.match(source.toLowerCase(), new RegExp(token.toLowerCase()), token)
    }
    assert.match(source, /reduceMobileSurface/, 'all adapters must use one reducer contract')
  }
})

test('native mobile surfaces expose navigation, model sheet and permission controls', async () => {
  const sources = await Promise.all(Object.values(surfaces).map(file => readFile(path.join(root, file), 'utf8')))
  for (const source of sources) {
    for (const token of ['MobileSurface', 'state', 'permission', 'reduceMobileSurface', '发送']) {
      assert.match(source, new RegExp(token), token)
    }
  }
})

test('mobile Cloud password fields never render as plain text', async () => {
  const android = await readFile(path.join(root, surfaces.android), 'utf8')
  const ios = await readFile(path.join(root, surfaces.ios), 'utf8')
  const harmony = await readFile(path.join(root, surfaces.harmony), 'utf8')
  assert.match(android, /cloudPassword[\s\S]*PasswordVisualTransformation/)
  assert.match(ios, /SecureField\("密码"/)
  assert.match(harmony, /placeholder:\s*'密码'[\s\S]*InputType\.Password/)
})

test('mobile task menus do not seed fake conversation titles', async () => {
  const sources = await Promise.all(Object.values(surfaces).map(file => readFile(path.join(root, file), 'utf8')))
  for (const source of sources) {
    assert.doesNotMatch(source, /检查系统架构|整理研究报告|云端项目规划|远程设备排查/)
  }
})

test('native mobile surfaces bind Cloud sessions and secure token stores', async () => {
  const sources = await Promise.all([
    readFile(path.join(root, 'android/src/main/kotlin/com/notemeld/mobile/CloudApi.kt'), 'utf8'),
    readFile(path.join(root, 'ios/Sources/NoteMeldMobile/MobileSurface.swift'), 'utf8'),
    readFile(path.join(root, 'harmony/entry/src/main/ets/pages/MobileSurface.ets'), 'utf8'),
  ])
  assert.match(sources[0], /AndroidKeyStore/)
  assert.match(sources[0], /\/v1\/sessions/)
  assert.match(sources[1], /KeychainToken/)
  assert.match(sources[1], /\/v1\/sessions/)
  assert.match(sources[2], /security\.huks/)
  assert.match(sources[2], /HarmonyTokenStore/)
  assert.match(sources[2], /\/v1\/sessions/)
})

test('Harmony ships a launchable UIAbility and scrollable Cloud settings surface', async () => {
  const module = await readFile(path.join(root, 'harmony/entry/src/main/module.json5'), 'utf8')
  const ability = await readFile(path.join(root, 'harmony/entry/src/main/ets/entryability/EntryAbility.ets'), 'utf8')
  const surface = await readFile(path.join(root, 'harmony/entry/src/main/ets/pages/MobileSurface.ets'), 'utf8')
  assert.match(module, /mainElement.*EntryAbility/)
  assert.match(module, /"name":\s*"EntryAbility"/)
  assert.match(ability, /loadContent\('pages\/MobileSurface'\)/)
  assert.match(surface, /@Builder settings\(\)[\s\S]*Scroll\(\)/)
  assert.match(surface, /placeholder:\s*'密码'[\s\S]*InputType\.Password/)
})

test('mobile Cloud adapters persist a session identity and resume event pagination', async () => {
  const android = await readFile(path.join(root, 'android/src/main/kotlin/com/notemeld/mobile/CloudApi.kt'), 'utf8')
  const ios = await readFile(path.join(root, 'ios/Sources/NoteMeldMobile/MobileSurface.swift'), 'utf8')
  const iosState = await readFile(path.join(root, 'ios/Sources/NoteMeldMobile/MobileSurfaceState.swift'), 'utf8')
  const harmony = await readFile(path.join(root, 'harmony/entry/src/main/ets/pages/MobileSurface.ets'), 'utf8')
  assert.match(android, /session_id/)
  assert.match(android, /event_sequence/)
  assert.match(android, /after.*event_sequence/)
  assert.match(ios, /notemeld\.cloud\.sessionID/)
  assert.match(ios, /notemeld\.cloud\.eventSequence/)
  assert.match(ios, /events\?after=/)
  assert.match(harmony, /notemeld-cloud-sync/)
  assert.match(harmony, /event_sequence/)
  assert.match(harmony, /events\?after=/)
})

test('Android memory actions use the real projection API and only update after save', async () => {
  const activity = await readFile(path.join(root, 'android/app/src/main/kotlin/com/notemeld/mobile/MainActivity.kt'), 'utf8')
  const surface = await readFile(path.join(root, 'android/src/main/kotlin/com/notemeld/mobile/MobileSurface.kt'), 'utf8')
  const api = await readFile(path.join(root, 'android/src/main/kotlin/com/notemeld/mobile/MobileApi.kt'), 'utf8')
  assert.match(activity, /MobileApi\.loadProjection\(\)/)
  assert.match(activity, /MobileApi\.createMemory\(content\)/)
  assert.match(api, /\/api\/mobile\/memories/)
  assert.match(surface, /onAddMemory/)
  assert.match(surface, /if \(saved\) d\(MobileSurfaceAction\.AddMemory\)/)
})

test('native session actions bind the current task and delete through the real API', async () => {
  const android = await readFile(path.join(root, 'android/src/main/kotlin/com/notemeld/mobile/MobileSurface.kt'), 'utf8')
  const androidState = await readFile(path.join(root, 'android/src/main/kotlin/com/notemeld/mobile/MobileSurfaceState.kt'), 'utf8')
  const androidApi = await readFile(path.join(root, 'android/src/main/kotlin/com/notemeld/mobile/MobileApi.kt'), 'utf8')
  const ios = await readFile(path.join(root, 'ios/Sources/NoteMeldMobile/MobileSurface.swift'), 'utf8')
  const iosState = await readFile(path.join(root, 'ios/Sources/NoteMeldMobile/MobileSurfaceState.swift'), 'utf8')
  const harmony = await readFile(path.join(root, 'harmony/entry/src/main/ets/pages/MobileSurface.ets'), 'utf8')
  assert.match(androidState, /activeTaskId[\s\S]*OpenTask\(val id: String\?/) 
  assert.match(androidApi, /api\/conversations[\s\S]*requestMethod = "DELETE"/)
  assert.match(android, /onDeleteTask[\s\S]*MobileSurfaceAction\.DeleteConversation/)
  assert.match(iosState, /activeTaskID/)
  assert.match(ios, /api\/conversations[\s\S]*httpMethod = "DELETE"/)
  assert.match(harmony, /activeTaskId[\s\S]*RequestMethod\.DELETE[\s\S]*api\/conversations/)
  for (const source of [android, ios, harmony]) {
    assert.match(source, /全部产物/)
    assert.match(source, /删除对话/)
  }
})

test('mobile home refreshes the server projection while the app is active', async () => {
  const android = await readFile(path.join(root, 'android/app/src/main/kotlin/com/notemeld/mobile/MainActivity.kt'), 'utf8')
  const ios = await readFile(path.join(root, 'ios/Sources/NoteMeldMobile/MobileSurface.swift'), 'utf8')
  const harmony = await readFile(path.join(root, 'harmony/entry/src/main/ets/pages/MobileSurface.ets'), 'utf8')
  assert.match(android, /while \(true\)[\s\S]*MobileApi\.loadTasks\(\)[\s\S]*delay\(5000\)/)
  assert.match(ios, /while !Task\.isCancelled[\s\S]*await loadTasks\(\)[\s\S]*Task\.sleep/)
  assert.match(harmony, /setInterval\(\(\) => this\.loadTasks\(\), 5000\)/)
})

test('mobile projection reads persist the server-side device cursor', async () => {
  const android = await readFile(path.join(root, 'android/src/main/kotlin/com/notemeld/mobile/MobileApi.kt'), 'utf8')
  const ios = await readFile(path.join(root, 'ios/Sources/NoteMeldMobile/MobileSurface.swift'), 'utf8')
  const harmony = await readFile(path.join(root, 'harmony/entry/src/main/ets/pages/MobileSurface.ets'), 'utf8')
  assert.match(android, /recordProjectionCursor[\s\S]*api\/mobile\/sync-cursor[\s\S]*snapshot_revision/)
  assert.match(ios, /saveProjectionCursor[\s\S]*api\/mobile\/sync-cursor[\s\S]*snapshot_revision/)
  assert.match(harmony, /recordProjectionCursor[\s\S]*api\/mobile\/sync-cursor[\s\S]*snapshot_revision/)
})

test('mobile adapters recover from offline to ready after a successful refresh', async () => {
  const ios = await readFile(path.join(root, 'ios/Sources/NoteMeldMobile/MobileSurface.swift'), 'utf8')
  const harmony = await readFile(path.join(root, 'harmony/entry/src/main/ets/pages/MobileSurface.ets'), 'utf8')
  assert.match(ios, /decode\(ConversationEnvelope\.self[\s\S]*setConnection\(\.ready\)/)
  assert.match(harmony, /this\.state\.tasks = rows\.map[\s\S]*ConnectionState\.Ready/)
})

test('native remote transports authenticate, bind nonce into AAD and decrypt receipts/events', async () => {
  const android = await readFile(path.join(root, 'android/src/main/kotlin/com/notemeld/mobile/AndroidRemoteRelay.kt'), 'utf8')
  const ios = await readFile(path.join(root, 'ios/Sources/NoteMeldMobile/RemoteRelayTransport.swift'), 'utf8')
  const harmony = await readFile(path.join(root, 'harmony/entry/src/main/ets/services/HarmonyRemoteTransport.ets'), 'utf8')
  assert.match(android, /updateAAD\(arJson\(metadata\)/)
  assert.match(android, /frame_type.*receipt[\s\S]*decryptPayload/)
  assert.match(android, /pendingFrameId[\s\S]*remote command receipt timeout/)
  assert.match(ios, /AES\.GCM\.open[\s\S]*authenticating: Data\(Self\.json\(metadata\)/)
  assert.match(ios, /pending\[frameID\]/)
  assert.match(harmony, /HarmonyRemoteCrypto\.decrypt\(this\.sessionKey, HarmonyRemoteTransport\.decode\(nonce\), HarmonyRemoteTransport\.decode\(ciphertext\)/)
  assert.match(harmony, /frame_type.*receipt[\s\S]*decryptFrame/)
})

test('native remote transports use the same RFC 5869 absent-salt convention', async () => {
  const android = await readFile(path.join(root, 'android/src/main/kotlin/com/notemeld/mobile/AndroidRemoteRelay.kt'), 'utf8')
  const ios = await readFile(path.join(root, 'ios/Sources/NoteMeldMobile/RemoteRelayTransport.swift'), 'utf8')
  const harmony = await readFile(path.join(root, 'harmony/entry/src/main/ets/services/HarmonyRemoteCrypto.ets'), 'utf8')
  assert.match(android, /SecretKeySpec\(ByteArray\(32\), "HmacSHA256"\)/)
  assert.match(ios, /salt:\s*Data\(repeating:\s*0,\s*count:\s*32\)/)
  assert.match(harmony, /salt:\s*new Uint8Array\(32\)/)
})
