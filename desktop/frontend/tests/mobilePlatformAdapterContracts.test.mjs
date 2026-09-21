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

test('Android M01-M06 consume the independent ui-core design system', async () => {
  const uiCore = await readFile(path.join(root, 'android/ui-core/src/main/kotlin/com/notemeld/ui/NoteMeldUi.kt'), 'utf8')
  const surface = await readFile(path.join(root, surfaces.android), 'utf8')
  const activity = await readFile(path.join(root, 'android/app/src/main/kotlin/com/notemeld/mobile/MainActivity.kt'), 'utf8')
  const gradle = await readFile(path.join(root, 'android/app/build.gradle.kts'), 'utf8')
  assert.match(gradle, /implementation\(project\(":ui-core"\)\)/)
  for (const token of ['NoteMeldTheme', 'NoteMeldTokens', 'NoteMeldEmptyState', 'NoteMeldOfflineState', 'NoteMeldLoadingState', 'NoteMeldErrorState', 'NoteMeldSnackbar', 'NoteMeldProgress', 'NoteMeldField', 'NoteMeldSwitchRow', 'darkColorScheme', 'isSystemInDarkTheme']) assert.match(uiCore, new RegExp(token))
  assert.match(surface, /com\.notemeld\.ui\.NoteMeldEmptyState/)
  assert.match(surface, /com\.notemeld\.ui\.NoteMeldOfflineState/)
  assert.match(surface, /com\.notemeld\.ui\.NoteMeldField/)
  assert.match(surface, /com\.notemeld\.ui\.NoteMeldSwitchRow/)
  assert.match(surface, /com\.notemeld\.ui\.NoteMeldTheme/)
  assert.match(surface, /notemeld-mobile-root/)
  assert.match(surface, /notemeld-screen-\$\{state\.screen\.name\.lowercase\(\)\}/)
  assert.match(surface, /notemeld-session-detail/)
  assert.match(surface, /notemeld-settings/)
  assert.doesNotMatch(activity, /NoteMeldTheme/)
  assert.doesNotMatch(uiCore, /MobileSurfaceState|MobileMessage|CloudApi/)
})

test('Android quick actions use controlled vector icons instead of text glyph placeholders', async () => {
  const surface = await readFile(path.join(root, surfaces.android), 'utf8')
  assert.match(surface, /R\.drawable\.ic_document/)
  assert.match(surface, /R\.drawable\.ic_presentation/)
  assert.match(surface, /R\.drawable\.ic_work/)
  assert.match(surface, /R\.drawable\.ic_more/)
  assert.match(surface, /Icon\(painterResource\(icon\)/)
  assert.doesNotMatch(surface, /label\.take\(1\)/)
  assert.doesNotMatch(surface, /"···"/)
})

test('Android embedded LOCAL Provider adapter fails closed on malformed model responses', async () => {
  const adapter = await readFile(path.join(root, 'android/app/src/main/kotlin/com/notemeld/mobile/EmbeddedLocalAgent.kt'), 'utf8')
  for (const token of ['readBounded', 'response.optString("model", "")', 'choices.length() != 1', 'finishReason != "tool_calls"', 'finishReason != "stop"', 'seenCallIds', 'callId.isBlank()', 'JSONObject(rawArguments)']) {
    assert.ok(adapter.includes(token), token)
  }
  assert.doesNotMatch(adapter, /getOrElse \{ JSONObject\(\) \}/)
})

test('Android embedded LOCAL runtime restores bounded persisted history without duplicating the current input', async () => {
  const adapter = await readFile(path.join(root, 'android/app/src/main/kotlin/com/notemeld/mobile/EmbeddedLocalAgent.kt'), 'utf8')
  const store = await readFile(path.join(root, 'android/src/main/kotlin/com/notemeld/mobile/MobileLocalStore.kt'), 'utf8')
  const activity = await readFile(path.join(root, 'android/app/src/main/kotlin/com/notemeld/mobile/MainActivity.kt'), 'utf8')
  for (const token of ['MobileLocalStore.load(appContext).messages', 'persistedMessages.dropLast(1)', 'historyMessages.takeLast(200)', '.put("history", history)']) {
    assert.ok(adapter.includes(token), token)
  }
  for (const token of ['markLocalTurnPending', 'completeLocalTurn', 'recordLocalEvent', 'recoverInterruptedLocalTurn', 'pendingInput', 'MobileMessage("user", pendingInput)', 'turn.interrupted:needs_attention', '未知副作用未自动重放']) {
    assert.ok(store.includes(token), token)
  }
  for (const token of ['LOCAL_EVENT_CURSOR', 'pendingTurn != turnId', 'previousTurn != turnId', 'sequence', 'while (rows.length() > 200)', 'turn.succeeded', 'turn.interrupted']) {
    assert.ok(store.includes(token), token)
  }
  assert.match(store, /markLocalTurnPending[\s\S]*?\.commit\(\)/)
  assert.match(store, /completeLocalTurn[\s\S]*?\.commit\(\)/)
  assert.match(activity, /recoverInterruptedLocalTurn\(applicationContext\)/)
  assert.match(activity, /MobileLocalStore\.recordLocalEvent\(applicationContext, event\)/)
  assert.match(activity, /terminal != null\) MobileLocalStore\.completeLocalTurn/)
})

test('Android release identity embeds the immutable git commit in UI semantics', async () => {
  const surface = await readFile(path.join(root, surfaces.android), 'utf8')
  const gradle = await readFile(path.join(root, 'android/app/build.gradle.kts'), 'utf8')
  assert.match(gradle, /NOTEMELD_ANDROID_BUILD_COMMIT/)
  assert.match(gradle, /buildConfigField\("String", "BUILD_COMMIT"/)
  assert.match(surface, /notemeld-build-commit:\$\{BuildConfig\.BUILD_COMMIT\}/)
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
  assert.match(activity, /MobileApi\.loadMemoryProjection\(\)/)
  assert.match(activity, /MobileApi\.createMemory\(content\)/)
  assert.match(api, /\/api\/mobile\/memories[\s\S]*requestMethod = "DELETE"/)
  assert.match(surface, /onAddMemory/)
  assert.match(surface, /onDeleteMemory/)
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

test('native mobile surfaces enforce offline read-only controls', async () => {
  const android = await readFile(path.join(root, surfaces.android), 'utf8')
  const androidState = await readFile(path.join(root, 'android/src/main/kotlin/com/notemeld/mobile/MobileSurfaceState.kt'), 'utf8')
  const androidActivity = await readFile(path.join(root, 'android/app/src/main/kotlin/com/notemeld/mobile/MainActivity.kt'), 'utf8')
  const androidManifest = await readFile(path.join(root, 'android/app/src/main/AndroidManifest.xml'), 'utf8')
  const ios = await readFile(path.join(root, surfaces.ios), 'utf8')
  const harmony = await readFile(path.join(root, surfaces.harmony), 'utf8')
  assert.match(androidState, /val networkAvailable: Boolean = true/)
  assert.match(androidState, /AgentLocation\.LOCAL -> state\.connection != ConnectionState\.OFFLINE[\s\S]*AgentLocation\.CLOUD, AgentLocation\.REMOTE -> state\.networkAvailable/)
  assert.match(android, /val canInteract = canInteractWithAgent\(s\)[\s\S]*notemeld-agent-offline-readonly[\s\S]*enabled = canInteract[\s\S]*添加文件/)
  assert.match(androidActivity, /registerDefaultNetworkCallback[\s\S]*SetNetworkAvailable|networkAvailable = connectivity\.activeNetwork != null/)
  assert.match(androidManifest, /android\.permission\.ACCESS_NETWORK_STATE/)
  assert.match(ios, /Button\("添加文件"\)[\s\S]*disabled\(state\.connection == \.offline \|\| !state\.permissionGranted\)/)
  assert.match(harmony, /Button\('添加文件'\)\.enabled\(this\.state\.connection !== ConnectionState\.Offline && this\.state\.permissionGranted\)/)
  assert.match(harmony, /permissionButton\(\)[\s\S]*if \(this\.state\.connection !== ConnectionState\.Offline\)/)
})

test('mobile agent submission requires an explicit permission grant', async () => {
  const android = await readFile(path.join(root, surfaces.android), 'utf8')
  const ios = await readFile(path.join(root, surfaces.ios), 'utf8')
  const harmony = await readFile(path.join(root, surfaces.harmony), 'utf8')
  assert.match(android, /Button\(enabled = canInteract && s\.permissionGranted/)
  assert.match(ios, /guard !input\.isEmpty, state\.permissionGranted else \{ return \}/)
  assert.match(harmony, /\.enabled\(this\.state\.connection !== ConnectionState\.Offline && this\.state\.permissionGranted/)
})

test('Android Agent events stay visible across projection refreshes and update Compose state on main', async () => {
  const activity = await readFile(path.join(root, 'android/app/src/main/kotlin/com/notemeld/mobile/MainActivity.kt'), 'utf8')
  const api = await readFile(path.join(root, 'android/src/main/kotlin/com/notemeld/mobile/MobileApi.kt'), 'utf8')
  const state = await readFile(path.join(root, 'android/src/main/kotlin/com/notemeld/mobile/MobileSurfaceState.kt'), 'utf8')
  const surface = await readFile(path.join(root, 'android/src/main/kotlin/com/notemeld/mobile/MobileSurface.kt'), 'utf8')
  assert.match(api, /listOf\("delta", "answer", "content", "output"\)/)
  assert.match(activity, /scope\.launch\(Dispatchers\.IO\)[\s\S]*scope\.launch \{ onEvent\(content, terminalType\) \}/)
  assert.match(surface, /remember \{ mutableStateOf\(initialState\) \}[\s\S]*LaunchedEffect\(initialState\.connection, initialState\.networkAvailable, initialState\.memories,[\s\S]*state = state\.copy\(connection = initialState\.connection, networkAvailable = initialState\.networkAvailable, memories = initialState\.memories/)
  assert.match(surface, /AgentLocation\.LOCAL to "本机"[\s\S]*AgentLocation\.CLOUD to "Cloud"[\s\S]*AgentLocation\.REMOTE to "远程"/)
  assert.match(surface, /notemeld-agent-location-\$\{location\.name\.lowercase\(\)\}/)
  assert.match(surface, /notemeld-open-settings[\s\S]*notemeld-close-settings[\s\S]*notemeld-back-settings/)
  assert.match(state, /OpenSettings -> state\.copy\(settingsReturnScreen = state\.screen[\s\S]*CloseSettings -> state\.copy\(screen = state\.settingsReturnScreen/)
  assert.match(state, /AppendAssistantContent[\s\S]*last\.copy\(content = last\.content \+ action\.value\)/)
  assert.match(state, /ResetAgentTerminals[\s\S]*RecordAgentTerminal/)
  assert.match(surface, /notemeld-agent-terminal:\$\{s\.terminalEvents\.last\(\)\}:\$\{s\.terminalEvents\.size\}/)
  assert.doesNotMatch(api, /eventType\.startsWith\("turn\."\)/)
  assert.match(api, /eventType in setOf\("turn\.succeeded", "turn\.failed", "turn\.cancelled", "turn\.interrupted"\)/)
})

test('Android LOCAL session exposes canonical cancel and steer controls', async () => {
  const surface = await readFile(path.join(root, surfaces.android), 'utf8')
  const activity = await readFile(path.join(root, 'android/app/src/main/kotlin/com/notemeld/mobile/MainActivity.kt'), 'utf8')
  const adapter = await readFile(path.join(root, 'android/app/src/main/kotlin/com/notemeld/mobile/EmbeddedLocalAgent.kt'), 'utf8')
  assert.ok(surface.includes('onCancelLocal') && surface.includes('取消'))
  assert.ok(surface.includes('onSteerLocal') && surface.includes('调整方向'))
  assert.ok(activity.includes('activeLocalToken') && activity.includes('embeddedLocalAgent::cancel'))
  assert.match(activity, /embeddedLocalAgent\.steer\(it, JSONObject\(\)\.put\("text", value\)\)/)
  assert.match(adapter, /fun cancel\(token: Long\) = runtime\.cancel\(token\)/)
  assert.match(adapter, /fun steer\(token: Long, payload: JSONObject\) = runtime\.steer\(token, payload\)/)
})

test('native mobile memory writes are disabled while offline', async () => {
  const android = await readFile(path.join(root, surfaces.android), 'utf8')
  const ios = await readFile(path.join(root, surfaces.ios), 'utf8')
  const harmony = await readFile(path.join(root, surfaces.harmony), 'utf8')
  assert.match(android, /OutlinedTextField\(s\.memoryDraft[\s\S]*enabled = s\.connection != ConnectionState\.OFFLINE/)
  assert.match(ios, /添加我的记忆[\s\S]*state\.connection == \.offline/)
  assert.match(harmony, /Button\('添加我的记忆'\)\.enabled\(this\.state\.connection !== ConnectionState\.Offline/)
})

test('native destructive actions re-check offline and permission state', async () => {
  const android = await readFile(path.join(root, surfaces.android), 'utf8')
  const ios = await readFile(path.join(root, surfaces.ios), 'utf8')
  const harmony = await readFile(path.join(root, surfaces.harmony), 'utf8')
  assert.match(android, /TextButton\(enabled = s\.connection != ConnectionState\.OFFLINE && s\.permissionGranted[\s\S]*删除对话/)
  assert.match(ios, /guard state\.connection != \.offline, let id = state\.activeTaskID/)
  assert.match(harmony, /if \(this\.state\.connection === ConnectionState\.Offline \|\| !this\.state\.permissionGranted\) return/)
})

test('native reducers reject new input while offline but retain terminal callback messages', async () => {
  const androidState = await readFile(path.join(root, files.android), 'utf8')
  const iosState = await readFile(path.join(root, files.ios), 'utf8')
  const harmonyState = await readFile(path.join(root, files.harmony), 'utf8')
  assert.match(androidState, /SetInputText -> if \(canInteractWithAgent\(state\)\) state\.copy\(inputText = action\.value\) else state/)
  assert.match(androidState, /AddMessage -> state\.copy\(messages = state\.messages \+ action\.value\)/)
  assert.match(androidState, /AppendAssistantContent -> if \(action\.value\.isBlank\(\)\) state else/)
  assert.match(iosState, /setInputText\(value\): if next\.connection != \.offline/)
  assert.match(iosState, /addMessage\(value\): if next\.connection != \.offline/)
  assert.match(harmonyState, /setInputText'.*if \(state\.connection !== ConnectionState\.Offline\)/)
  assert.match(harmonyState, /addMessage'.*if \(state\.connection !== ConnectionState\.Offline\)/)
})

test('native reducers reject memory writes while offline', async () => {
  const androidState = await readFile(path.join(root, files.android), 'utf8')
  const iosState = await readFile(path.join(root, files.ios), 'utf8')
  const harmonyState = await readFile(path.join(root, files.harmony), 'utf8')
  assert.match(androidState, /AddMemory -> if \(state\.connection == ConnectionState\.OFFLINE \|\| state\.memoryDraft\.isBlank\(\)\)/)
  assert.match(iosState, /addMemory: if next\.connection != \.offline && !next\.memoryDraft/)
  assert.match(harmonyState, /'addMemory'.*state\.connection !== ConnectionState\.Offline/)
})

test('native remote transports authenticate, bind nonce into AAD and decrypt receipts/events', async () => {
  const android = await readFile(path.join(root, 'android/src/main/kotlin/com/notemeld/mobile/AndroidRemoteRelay.kt'), 'utf8')
  const ios = await readFile(path.join(root, 'ios/Sources/NoteMeldMobile/RemoteRelayTransport.swift'), 'utf8')
  const harmony = await readFile(path.join(root, 'harmony/entry/src/main/ets/services/HarmonyRemoteTransport.ets'), 'utf8')
  assert.match(android, /updateAAD\(arJson\(metadata\)/)
  assert.match(android, /frame_type.*receipt[\s\S]*decryptPayload/)
  assert.match(android, /relay_ready/)
  assert.match(android, /next_sequence/)
  assert.match(android, /pendingFrameId[\s\S]*remote command receipt timeout/)
  assert.match(ios, /AES\.GCM\.open[\s\S]*authenticating: Data\(Self\.json\(metadata\)/)
  assert.match(ios, /pending\[frameID\]/)
  assert.match(harmony, /HarmonyRemoteCrypto\.decrypt\(this\.sessionKey, HarmonyRemoteTransport\.decode\(nonce\), HarmonyRemoteTransport\.decode\(ciphertext\)/)
  assert.match(harmony, /frame_type.*receipt[\s\S]*decryptFrame/)
})

test('Android remote control creates a grant, proves its device key, uses a device token, and completes on a terminal event', async () => {
  const android = await readFile(path.join(root, 'android/src/main/kotlin/com/notemeld/mobile/CloudApi.kt'), 'utf8')
  const activity = await readFile(path.join(root, 'android/app/src/main/kotlin/com/notemeld/mobile/MainActivity.kt'), 'utf8')
  const relay = await readFile(path.join(root, 'android/src/main/kotlin/com/notemeld/mobile/AndroidRemoteRelay.kt'), 'utf8')
  const surface = await readFile(path.join(root, 'android/src/main/kotlin/com/notemeld/mobile/MobileSurface.kt'), 'utf8')
  assert.match(android, /ensureRemoteGrant/)
  assert.match(android, /\/v1\/grants/)
  assert.match(android, /notemeld-device-proof-v1/)
  assert.match(android, /challenge\/verify/)
  assert.match(android, /revoke_source_token.*false/)
  assert.match(android, /AndroidRemoteRelay\(baseUrl, deviceToken/)
  assert.match(android, /remote_session_[\s\S]*syncState\.getString\(remoteSessionKey, null\)[\s\S]*putString\(remoteSessionKey/)
  assert.match(android, /account_state[\s\S]*syncState\.edit\(\)\.clear\(\)/)
  assert.match(android, /CountDownLatch/)
  assert.match(android, /turn\.succeeded/)
  assert.match(android, /onTransport\(transport\.activeTransport[\s\S]*transport\.relayCursorStart/)
  assert.match(android, /type == "approval\.required"[\s\S]*Android 控制端不能代为批准/)
  assert.match(relay, /activeTransport = if \(lan\) "lan" else "relay"/)
  assert.match(relay, /sequence = waitForRelayReady\(\); relayCursorStart = sequence/)
  assert.match(activity, /hasAccountToken\(\)[\s\S]*listDevices\(initialState\.cloudUrl/)
  assert.match(surface, /notemeld-remote-host[\s\S]*notemeld-remote-transport[\s\S]*notemeld-remote-cursor/)
  assert.doesNotMatch(android, /Thread\.sleep\(60_000\)/)
})

test('native remote transports use the same RFC 5869 absent-salt convention', async () => {
  const android = await readFile(path.join(root, 'android/src/main/kotlin/com/notemeld/mobile/AndroidRemoteRelay.kt'), 'utf8')
  const ios = await readFile(path.join(root, 'ios/Sources/NoteMeldMobile/RemoteRelayTransport.swift'), 'utf8')
  const harmony = await readFile(path.join(root, 'harmony/entry/src/main/ets/services/HarmonyRemoteCrypto.ets'), 'utf8')
  assert.match(android, /SecretKeySpec\(ByteArray\(32\), "HmacSHA256"\)/)
  assert.match(ios, /salt:\s*Data\(repeating:\s*0,\s*count:\s*32\)/)
  assert.match(harmony, /salt:\s*new Uint8Array\(32\)/)
})
