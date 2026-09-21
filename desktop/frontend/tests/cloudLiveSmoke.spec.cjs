const { test, expect } = require('playwright/test')
const path = require('path')

const baseUrl = process.env.CLOUD_TEST_BASE_URL || 'http://127.0.0.1:18583'
const username = process.env.CLOUD_TEST_USERNAME || 'hehejie'
const password = process.env.CLOUD_TEST_PASSWORD

test.use({
  launchOptions: {
    executablePath: process.env.CHROME_EXECUTABLE || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
  },
})

test.describe('Cloud production bundle live smoke', () => {
  test.skip(!password, 'CLOUD_TEST_PASSWORD is required for live Cloud acceptance')

  test('logs in, opens C02-C06, saves a model, and completes a real Cloud turn', async ({ page, request }) => {
    // The real Provider turn is allowed to take up to 30s; keep cleanup and
    // the responsive evidence captures inside the test budget as well.
    test.setTimeout(90_000)
    const httpErrors = []
    const consoleErrors = []
    page.on('response', response => {
      if (response.status() >= 400 && response.url().includes('/v1/')) httpErrors.push(`${response.status()} ${response.url()}`)
    })
    page.on('console', message => {
      if (message.type() === 'error') consoleErrors.push(message.text())
    })

    await page.setViewportSize({ width: 1440, height: 960 })
    // Capture the persisted baseline before the browser login registers its
    // controller device. Otherwise every successful smoke run mistakes its
    // own new browser device for pre-existing user data and cannot clean it.
    const apiLogin = await request.post(`${baseUrl}/v1/auth/login`, { data: { username, password } })
    const apiLoginData = (await apiLogin.json()).data
    const apiToken = apiLoginData.access_token || apiLoginData.token
    const apiHeaders = { Authorization: `Bearer ${apiToken}` }
    const baselineSessionsResponse = await request.get(`${baseUrl}/v1/cloud/sessions`, { headers: apiHeaders })
    const baselineSessionsData = (await baselineSessionsResponse.json()).data
    const baselineSessionIds = new Set((Array.isArray(baselineSessionsData) ? baselineSessionsData : baselineSessionsData.items || []).map(item => item.id))
    const baselineDevicesResponse = await request.get(`${baseUrl}/v1/devices`, { headers: apiHeaders })
    const baselineDevicesData = (await baselineDevicesResponse.json()).data
    const baselineDeviceIds = new Set((Array.isArray(baselineDevicesData) ? baselineDevicesData : baselineDevicesData.items || []).map(item => item.id))
    await page.goto(`${baseUrl}/cloud/login?returnTo=%2Fcloud%2Fworkbench`)
    await page.getByLabel('邮箱或用户名').fill(username)
    await page.locator('#cloud-password').fill(password)
    await page.getByRole('button', { name: '登录' }).click()
    await expect(page).toHaveURL(/\/cloud\/workbench/)
    const grantController = `acceptance-controller-${Date.now()}`
    const grantHost = `acceptance-host-${Date.now()}`
    const revokeDevice = `acceptance-revoke-${Date.now()}`
    const revokeDisplayName = `Acceptance revoke device ${Date.now()}`
    const publicKey = 'A'.repeat(43)
    for (const [deviceId, displayName] of [[grantController, 'Acceptance controller'], [grantHost, 'Acceptance host'], [revokeDevice, revokeDisplayName]]) {
      const registered = await request.post(`${baseUrl}/v1/devices/register`, { headers: apiHeaders, data: { device_id: deviceId, platform: 'acceptance', display_name: displayName, public_key: publicKey } })
      expect(registered.ok()).toBeTruthy()
    }

    const accessContext = await page.context().browser().newContext()
    const accessPage = await accessContext.newPage()
    await accessPage.goto(`${baseUrl}/cloud/access-request`)
    await accessPage.getByLabel('邮箱或用户名').fill(`acceptance-${Date.now()}@example.com`)
    await accessPage.getByLabel('姓名或称呼').fill('Acceptance User')
    await accessPage.getByLabel('设置登录密码').fill('notemeld-access-123')
    await accessPage.getByLabel('确认密码').fill('notemeld-access-456')
    await accessPage.getByRole('button', { name: '提交申请' }).click()
    await expect(accessPage.getByRole('alert')).toContainText('密码不一致')
    await accessPage.screenshot({ path: '/tmp/notemeld-acceptance/cloud-c01-c06/c01-access-request-error-live-playwright.png', fullPage: true })
    const accessRequestUsername = `acceptance-request-${Date.now()}@example.com`
    await accessPage.getByLabel('邮箱或用户名').fill(accessRequestUsername)
    await accessPage.getByLabel('姓名或称呼').fill('Acceptance Request')
    await accessPage.getByLabel('设置登录密码').fill('notemeld-access-123')
    await accessPage.getByLabel('确认密码').fill('notemeld-access-123')
    await accessPage.getByRole('button', { name: '提交申请' }).click()
    await expect(accessPage.getByRole('alert')).toContainText('申请已提交')
    const accessRequestsResponse = await request.get(`${baseUrl}/v1/admin/access-requests`, { headers: apiHeaders })
    const accessRequestsData = (await accessRequestsResponse.json()).data
    const accessRequests = Array.isArray(accessRequestsData) ? accessRequestsData : accessRequestsData.items || []
    const accessRequest = accessRequests.find(item => item.email === accessRequestUsername || item.username === accessRequestUsername)
    expect(accessRequest).toBeTruthy()
    const reviewed = await request.post(`${baseUrl}/v1/admin/access-requests/${encodeURIComponent(accessRequest.id)}/review`, { headers: apiHeaders, data: { status: 'rejected' } })
    expect(reviewed.ok()).toBeTruthy()
    await accessContext.close()

    // Normalize the persisted server preference before language-specific UI assertions.
    await page.locator('a[href="/cloud/settings"]').click()
    await page.getByRole('button', { name: /通用|General/ }).click()
    await page.getByLabel(/Cloud 语言|Language/).selectOption('zh-CN')
    await page.getByRole('button', { name: /保存并同步|Save and sync/ }).click()
    await page.screenshot({ path: '/tmp/notemeld-acceptance/cloud-c01-c06/c06-settings-general-live-playwright.png', fullPage: true })
    await page.locator('a[href="/cloud/workbench"]').click()

    for (const path of ['sessions', 'people', 'devices', 'settings']) {
      await page.locator(`a[href="/cloud/${path}"]`).click()
      await expect(page).toHaveURL(new RegExp(`/cloud/${path}`))
    }

    await page.locator('a[href="/cloud/people"]').click()
    await page.getByRole('button', { name: '添加用户' }).click()
    await expect(page.getByRole('dialog')).toBeVisible()
    await page.screenshot({ path: '/tmp/notemeld-acceptance/cloud-c01-c06/c04-people-live-playwright.png', fullPage: true })
    await page.getByRole('button', { name: '关闭' }).click()
    const temporaryMemberUsername = `acceptance-member-${Date.now()}`
    await page.getByRole('button', { name: '添加用户' }).click()
    await page.getByRole('dialog').getByLabel('用户名或邮箱').fill(temporaryMemberUsername)
    await page.getByRole('dialog').getByLabel('临时密码').fill('acceptance-member-password')
    await page.getByRole('dialog').getByRole('button', { name: '发送邀请' }).click()
    const temporaryMemberRow = page.getByRole('row').filter({ hasText: temporaryMemberUsername })
    await expect(temporaryMemberRow).toBeVisible()
    await temporaryMemberRow.getByRole('button', { name: '编辑' }).click()
    await page.getByLabel('用户名或邮箱').fill(`${temporaryMemberUsername}-edited`)
    await page.getByLabel('已停用').check()
    await page.getByRole('button', { name: '保存成员' }).click()
    const editedMemberRow = page.getByRole('row').filter({ hasText: `${temporaryMemberUsername}-edited` })
    await expect(editedMemberRow).toContainText('已停用')
    await editedMemberRow.getByRole('button', { name: '删除' }).click()
    await expect(editedMemberRow).toHaveCount(0)
    const remainingUsersData = (await (await request.get(`${baseUrl}/v1/admin/users`, { headers: apiHeaders })).json()).data
    const remainingUsers = Array.isArray(remainingUsersData) ? remainingUsersData : remainingUsersData.items || []
    expect(remainingUsers.some(user => user.username === `${temporaryMemberUsername}-edited`)).toBeFalsy()

    await page.locator('a[href="/cloud/devices"]').click()
    await expect(page.getByText('添加设备')).toBeVisible()
    await page.getByRole('button', { name: /添加设备/ }).click()
    await expect(page.getByRole('button', { name: '生成配对码' })).toBeVisible()
    await page.getByRole('button', { name: '关闭' }).click()
    await page.getByRole('tab', { name: '运行节点' }).click()
    await expect(page.getByText('暂无运行节点')).toBeVisible()
    await page.getByRole('tab', { name: '可信设备' }).click()
    await page.getByRole('button', { name: /添加设备/ }).click()
    await page.getByRole('button', { name: '生成配对码' }).click()
    const pairingCode = page.getByLabel('Pairing code')
    await expect(pairingCode).toHaveText(/\S+/)
    const pairedDeviceId = `acceptance-paired-${Date.now()}`
    await page.getByLabel('目标设备 ID').fill(pairedDeviceId)
    await page.getByLabel('显示名称').fill('Acceptance paired device')
    await page.getByRole('button', { name: '确认配对' }).click()
    await expect(page.locator('section[aria-labelledby="cloud-pairing-title"]').getByText('设备已配对。', { exact: true })).toBeVisible()
    await page.getByRole('button', { name: '关闭' }).click()
    const pairedDeviceRow = page.getByRole('listitem').filter({ hasText: 'Acceptance paired device' }).last()
    await expect(pairedDeviceRow).toBeVisible()
    const pairedDeviceDeleted = await request.delete(`${baseUrl}/v1/devices/${encodeURIComponent(pairedDeviceId)}`, { headers: apiHeaders })
    expect(pairedDeviceDeleted.ok()).toBeTruthy()
    const permissionButton = page.getByRole('button', { name: '权限' }).first()
    await expect(permissionButton).toBeVisible()
    await permissionButton.click()
    await expect(page.getByRole('group', { name: '设备权限' })).toBeVisible()
    const remoteExecute = page.getByRole('group', { name: '设备权限' }).getByLabel('远程执行', { exact: true })
    await remoteExecute.check()
    await page.getByRole('group', { name: '设备权限' }).getByRole('button', { name: '保存设备权限' }).click()
    await expect(page.getByText('设备权限已保存。', { exact: true })).toBeVisible()
    await remoteExecute.uncheck()
    await page.getByRole('group', { name: '设备权限' }).getByRole('button', { name: '保存设备权限' }).click()
    await page.locator('section.cloud-device-security details summary').click()
    const grantSection = page.locator('section[aria-labelledby="grant-title"]')
    await grantSection.getByLabel('控制端设备 ID').fill(grantController)
    await grantSection.getByLabel('被控端设备 ID').fill(grantHost)
    await grantSection.getByRole('button', { name: '保存授权' }).click()
    await expect(grantSection.getByText('设备授权已保存。', { exact: true })).toBeVisible()
    await expect(grantSection.getByText(`${grantController} → ${grantHost}`, { exact: false })).toBeVisible()
    await grantSection.getByRole('button', { name: '撤销' }).click()
    await expect(grantSection.getByText('暂无已保存授权。', { exact: true })).toBeVisible()
    await request.delete(`${baseUrl}/v1/devices/${encodeURIComponent(grantController)}`, { headers: apiHeaders })
    await request.delete(`${baseUrl}/v1/devices/${encodeURIComponent(grantHost)}`, { headers: apiHeaders })
    const revokeRow = page.getByRole('listitem').filter({ hasText: revokeDisplayName })
    await expect(revokeRow).toBeVisible()
    await revokeRow.getByRole('button', { name: '撤销' }).click()
    await expect(revokeRow).toHaveCount(0)
    await page.evaluate(() => window.scrollTo(0, 0))
    await page.screenshot({ path: '/tmp/notemeld-acceptance/cloud-c01-c06/c05-devices-live-playwright.png', fullPage: true })

    await page.locator('a[href="/cloud/settings"]').click()
    await page.getByRole('button', { name: /通用|General/ }).click()
    await expect(page.getByLabel(/Cloud 语言|Language/)).toBeVisible()
    await expect(page.getByLabel(/默认 Workspace|Default Workspace/)).toBeVisible()
    await page.getByLabel(/Cloud 语言|Language/).selectOption('en-US')
    await expect(page.locator('html')).toHaveAttribute('lang', 'en-US')
    await page.getByRole('button', { name: /保存并同步|Save and sync/ }).click()
    await expect(page.getByText(/revision \d+/)).toBeVisible()
    await page.locator('a[href="/cloud/workbench"]').click()
    await expect(page.getByText(/Cloud status synced|云端状态已同步/)).toBeVisible()
    await expect(page.getByText(/Workspace usage|Workspace 用量/)).toBeVisible()
    await expect(page.getByText(/Last 7 days|近 7 日用量/)).toBeVisible()
    await page.locator('a[href="/cloud/settings"]').click()
    await page.getByRole('button', { name: /Models|模型配置/ }).click()
    await page.getByRole('button', { name: /Add model|添加模型/ }).click()
    await expect(page.getByLabel(/Display name|名称/)).toHaveValue(/Volcengine|火山云/)
    await page.getByRole('button', { name: /Close|关闭/ }).click()
    // Keep the C02 screenshot comparable with the Chinese new-product reference.
    // English remains covered by the assertions above; the preference is restored
    // before capture so language does not dominate the visual diff.
    await page.locator('a[href="/cloud/settings"]').click()
    await page.getByRole('button', { name: /通用|General/ }).click()
    await page.getByLabel(/Cloud 语言|Language/).selectOption('zh-CN')
    await page.getByRole('button', { name: '保存并同步' }).click()
    await page.locator('a[href="/cloud/workbench"]').click()
    await expect(page.getByText('云端状态已同步')).toBeVisible()
    await page.screenshot({ path: '/tmp/notemeld-acceptance/cloud-c01-c06/c02-workbench-live-playwright.png', fullPage: true })
    await page.locator('a[href="/cloud/settings"]').click()
    const existingBackupsResponse = await request.get(`${baseUrl}/v1/workspaces/default/backups`, { headers: apiHeaders })
    const existingBackupsData = (await existingBackupsResponse.json()).data
    const existingBackupIds = new Set((Array.isArray(existingBackupsData) ? existingBackupsData : existingBackupsData.items || []).map(item => item.backup_id))
    await page.getByRole('button', { name: '空间管理' }).click()
    await expect(page.getByRole('heading', { name: '工作区文件' })).toBeVisible()
    await page.getByRole('button', { name: '创建备份' }).click()
    await expect(page.getByText('暂无备份。')).not.toBeVisible()
    const currentBackupsResponse = await request.get(`${baseUrl}/v1/workspaces/default/backups`, { headers: apiHeaders })
    const currentBackupsData = (await currentBackupsResponse.json()).data
    const currentBackupItems = Array.isArray(currentBackupsData) ? currentBackupsData : currentBackupsData.items || []
    for (const item of currentBackupItems) {
      if (!existingBackupIds.has(item.backup_id)) await request.delete(`${baseUrl}/v1/workspaces/default/backups/${encodeURIComponent(item.backup_id)}`, { headers: apiHeaders })
    }
    await page.getByRole('button', { name: '日志排查' }).click()
    await expect(page.getByRole('heading', { name: '日志排查' })).toBeVisible()
    await page.getByRole('button', { name: '加载审计记录' }).click()
    await expect(page.locator('pre.cloud-audit-preview, [role="status"]')).toBeVisible()
    await page.getByRole('button', { name: '安全管理' }).click()
    await expect(page.getByRole('heading', { name: '安全管理' })).toBeVisible()
    await expect(page.getByText('高风险操作审批', { exact: true })).toBeVisible()
    await expect(page.getByText('登录设备', { exact: true })).toBeVisible()
    await expect(page.getByText('授权管理', { exact: true })).toBeVisible()
    await page.screenshot({ path: '/tmp/notemeld-acceptance/cloud-c01-c06/c06-security-live-playwright.png', fullPage: true })
    for (const category of ['通用', '空间管理', '模型配置', '安全管理', '日志排查']) {
      await page.getByRole('button', { name: category }).click()
      await expect(page.getByRole('button', { name: category })).toHaveClass(/active/)
    }
    await page.getByRole('button', { name: '模型配置' }).click()
    await expect(page.getByRole('heading', { name: '模型配置' })).toBeVisible()
    await page.getByRole('button', { name: '添加模型' }).click()
    await expect(page.getByRole('dialog')).toBeVisible()
    await page.screenshot({ path: '/tmp/notemeld-acceptance/cloud-c01-c06/c06-model-dialog-live-playwright.png', fullPage: true })
    const tempModelName = `acceptance-ui-model-${Date.now()}`
    await page.getByLabel('显示名称').fill(tempModelName)
    await page.getByLabel('自定义模型 ID').fill('acceptance-ui-model')
    await page.getByRole('dialog').getByRole('button', { name: '添加云端模型' }).click()
    await expect(page.getByText('模型已保存，列表已刷新。', { exact: true })).toBeVisible()
    const listedModels = await request.get(`${baseUrl}/v1/models`, { headers: apiHeaders })
    const listedModelsData = (await listedModels.json()).data
    const savedModel = listedModelsData.find(model => model.name === tempModelName)
    expect(savedModel).toBeTruthy()
    // The temporary model only proves the create/list UI path. It has no
    // provider credential, so never leave it in the shared acceptance account
    // or let it become the model used by the real turn below.
    const configuredDefault = listedModelsData.find(model => model.is_default && model.credential_status === 'configured')
    expect(configuredDefault).toBeTruthy()
    expect(await request.delete(`${baseUrl}/v1/models/${encodeURIComponent(savedModel.id)}`, { headers: apiHeaders })).toBeTruthy()

    await page.locator('a[href="/cloud/sessions"]').click()
    await page.screenshot({ path: '/tmp/notemeld-acceptance/cloud-c01-c06/c03-session-empty-live-playwright.png', fullPage: true })
    await page.getByRole('button', { name: '打开底部面板' }).click()
    await expect(page.getByText('运行面板', { exact: true })).toBeVisible()
    await page.getByRole('button', { name: '打开底部面板' }).click()
    await page.getByRole('button', { name: '打开侧边面板' }).click()
    await expect(page.getByText('会话摘要', { exact: true })).toBeVisible()
    await page.getByRole('button', { name: '打开侧边面板' }).click()
    await page.getByRole('button', { name: /新建会话/ }).first().click()
    await expect(page.getByRole('heading', { name: /新建会话|New session/ }).first()).toBeVisible({ timeout: 10_000 })
    const modelButton = page.locator('form.fixed button').filter({ hasText: '模型' }).first()
    await expect(modelButton).toBeVisible()
    await modelButton.click()
    await expect(page.getByRole('menuitem').first()).toBeVisible()
    await modelButton.click()
    await page.getByText('默认权限', { exact: true }).click()
    await expect(page.getByRole('dialog', { name: '权限设置' })).toBeVisible()
    await page.getByText('默认权限', { exact: true }).click()
    const editor = page.locator('textarea:visible').last()
    await expect(editor).toBeVisible()
    const attachmentPreview = page.locator('.cloud-attachment-preview:visible')
    await editor.evaluate(node => {
      const transfer = new DataTransfer()
      const bytes = Uint8Array.from([137, 80, 78, 71, 13, 10, 26, 10])
      transfer.items.add(new File([bytes], 'clipboard.png', { type: 'image/png' }))
      node.dispatchEvent(new ClipboardEvent('paste', { bubbles: true, clipboardData: transfer }))
    })
    await expect(attachmentPreview).toBeVisible()
    const attachmentInputs = page.locator('input[type="file"]')
    await expect(attachmentInputs).toHaveCount(1, { timeout: 10_000 })
    for (let index = 0; index < await attachmentInputs.count(); index += 1) {
      await attachmentInputs.nth(index).setInputFiles(path.join(__dirname, '..', 'src', 'assets', 'notemeld-cloud-logo.png'))
      if (await attachmentPreview.count()) break
    }
    await expect(attachmentPreview).toBeVisible()
    await editor.fill('Reply with exactly: BROWSER_ACCEPTED')
    const sendButton = editor.locator('xpath=ancestor::form').locator('button[type="submit"]')
    await expect(sendButton).toBeEnabled()
    await sendButton.click()
    await expect(page.getByText('命令状态：已完成')).toBeVisible({ timeout: 30_000 })
    await page.getByText('待处理审批', { exact: true }).first().click()
    await expect(page.getByRole('status', { name: '审批' })).toContainText('暂无待处理审批')

    await page.screenshot({ path: '/tmp/notemeld-acceptance/cloud-c01-c06/c03-live-playwright.png', fullPage: true })
    await page.getByRole('button', { name: '切换主题' }).click()
    await page.screenshot({ path: '/tmp/notemeld-acceptance/cloud-c01-c06/c03-live-playwright-dark.png', fullPage: true })
    await page.emulateMedia({ reducedMotion: 'reduce' })
    await page.setViewportSize({ width: 1024, height: 768 })
    await page.screenshot({ path: '/tmp/notemeld-acceptance/cloud-c01-c06/c03-live-playwright-1024-reduced.png', fullPage: true })
    await page.setViewportSize({ width: 390, height: 844 })
    await page.screenshot({ path: '/tmp/notemeld-acceptance/cloud-c01-c06/c03-live-playwright-mobile-reduced.png', fullPage: true })
    const sessionsAfterSmokeResponse = await request.get(`${baseUrl}/v1/cloud/sessions`, { headers: apiHeaders })
    const sessionsAfterSmokeData = (await sessionsAfterSmokeResponse.json()).data
    const sessionsAfterSmoke = Array.isArray(sessionsAfterSmokeData) ? sessionsAfterSmokeData : sessionsAfterSmokeData.items || []
    for (const session of sessionsAfterSmoke) {
      if (!baselineSessionIds.has(session.id)) await request.delete(`${baseUrl}/v1/cloud/sessions/${encodeURIComponent(session.id)}`, { headers: apiHeaders })
    }
    const devicesAfterSmokeResponse = await request.get(`${baseUrl}/v1/devices`, { headers: apiHeaders })
    const devicesAfterSmokeData = (await devicesAfterSmokeResponse.json()).data
    const devicesAfterSmoke = Array.isArray(devicesAfterSmokeData) ? devicesAfterSmokeData : devicesAfterSmokeData.items || []
    for (const device of devicesAfterSmoke) {
      if (!baselineDeviceIds.has(device.id)) await request.delete(`${baseUrl}/v1/devices/${encodeURIComponent(device.id)}`, { headers: apiHeaders })
    }
    await request.delete(`${baseUrl}/v1/models/${encodeURIComponent(savedModel.id)}`, { headers: apiHeaders })
    expect(httpErrors).toEqual([])
    expect(consoleErrors).toEqual([])
  })
})
