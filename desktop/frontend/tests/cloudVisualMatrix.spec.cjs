const { test, expect } = require('playwright/test')
const { createHash } = require('crypto')
const { mkdir, readFile, writeFile } = require('fs/promises')

const baseUrl = process.env.CLOUD_TEST_BASE_URL || 'http://127.0.0.1:18583'
const username = process.env.CLOUD_TEST_USERNAME || 'hehejie'
const password = process.env.CLOUD_TEST_PASSWORD
const outputDir = process.env.CLOUD_VISUAL_DIR || '/tmp/notemeld-acceptance/cloud-c01-c06/visual-matrix'

async function waitForCloudRouteSettled(page, route) {
  // The Cloud pages load their authoritative data after the route transition.
  // `networkidle` alone is not enough: a screenshot taken in that gap records
  // a transient loading surface instead of the page users actually review.
  await expect(page.locator('[aria-busy="true"]')).toHaveCount(0, { timeout: 15_000 })
  if (route === '/cloud/workbench') {
    await expect(page.getByText(/云端状态已同步|Cloud status synced/)).toBeVisible({ timeout: 15_000 })
  } else if (route === '/cloud/sessions') {
    await expect(page.getByText(/云端会话|Cloud sessions/).first()).toBeVisible({ timeout: 15_000 })
    await expect(page.getByText(/正在读取会话|Loading sessions/)).toHaveCount(0, { timeout: 15_000 })
  } else if (route === '/cloud/people') {
    await expect(page.getByText(/人员管理|People/).first()).toBeVisible({ timeout: 15_000 })
    await expect(page.getByText(/正在读取成员|Loading members/)).toHaveCount(0, { timeout: 15_000 })
  } else if (route === '/cloud/devices') {
    await expect(page.getByText(/设备安全|Device security/).first()).toBeVisible({ timeout: 15_000 })
    await expect(page.getByText(/正在读取设备|Loading devices/)).toHaveCount(0, { timeout: 15_000 })
  } else if (route === '/cloud/settings') {
    await expect(page.getByText(/通用设置|General settings/).first()).toBeVisible({ timeout: 15_000 })
    await expect(page.getByText(/正在读取配置|Reading configuration/)).toHaveCount(0, { timeout: 15_000 })
  }
}

async function captureDeviceBaseline(page) {
  const loginResponse = await page.request.post(`${baseUrl}/v1/auth/login`, {
    data: { username, password },
  })
  const loginPayload = await loginResponse.json()
  const token = loginPayload.data?.access_token || loginPayload.data?.token
  if (!token) throw new Error('Cloud visual test could not obtain an API token for cleanup')
  const headers = { Authorization: `Bearer ${token}` }
  const response = await page.request.get(`${baseUrl}/v1/devices`, { headers })
  const payload = await response.json()
  const devices = Array.isArray(payload.data) ? payload.data : (payload.data?.items || [])
  return { headers, ids: new Set(devices.map(device => device.id)) }
}

async function removeNewDevices(page, baseline) {
  const response = await page.request.get(`${baseUrl}/v1/devices`, { headers: baseline.headers })
  const payload = await response.json()
  const devices = Array.isArray(payload.data) ? payload.data : (payload.data?.items || [])
  for (const device of devices) {
    if (!baseline.ids.has(device.id)) {
      await page.request.delete(`${baseUrl}/v1/devices/${encodeURIComponent(device.id)}`, { headers: baseline.headers })
    }
  }
}

test.use({
  launchOptions: {
    executablePath: process.env.CHROME_EXECUTABLE || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
  },
})

test.skip(!password, 'CLOUD_TEST_PASSWORD is required for live Cloud acceptance')

test('captures the Cloud C02-C06 viewport and theme matrix', async ({ page }) => {
  test.setTimeout(180_000)
  const cases = [
    ['C02-workbench', '/cloud/workbench'],
    ['C03-sessions', '/cloud/sessions'],
    ['C04-people', '/cloud/people'],
    ['C05-devices', '/cloud/devices'],
    ['C06-settings', '/cloud/settings'],
  ]
  const viewports = [
    ['wide', 1440, 960],
    ['tablet', 1024, 768],
    ['mobile', 390, 844],
  ]
  const evidence = []
  const readyResponse = await page.request.get(`${baseUrl}/ready`)
  const ready = await readyResponse.json()
  await mkdir(outputDir, { recursive: true })

  const deviceBaseline = await captureDeviceBaseline(page)
  await page.goto(`${baseUrl}/cloud/login?returnTo=%2Fcloud%2Fworkbench`)
  await page.getByLabel('邮箱或用户名').fill(username)
  await page.locator('#cloud-password').fill(password)
  await page.getByRole('button', { name: '登录' }).click()
  await expect(page).toHaveURL(/\/cloud\/workbench/)

  for (const [viewportName, width, height] of viewports) {
    for (const theme of ['light', 'dark']) {
      for (const reducedMotion of [false, true]) {
        await page.setViewportSize({ width, height })
        await page.emulateMedia({ reducedMotion: reducedMotion ? 'reduce' : 'no-preference' })
        await page.evaluate(nextTheme => {
          document.documentElement.classList.toggle('dark', nextTheme === 'dark')
          localStorage.setItem('notemeld-theme', nextTheme)
        }, theme)
        for (const [caseName, route] of cases) {
          const navigationLink = page.locator(`a[href="${route}"]`).first()
          await expect(navigationLink).toBeVisible()
          await navigationLink.click()
          await expect(page).toHaveURL(new RegExp(`${route.replace('/', '\\/')}$`))
          await expect(page).not.toHaveURL(/\/cloud\/login/)
          await page.waitForLoadState('networkidle')
          await waitForCloudRouteSettled(page, route)
          const screenshotPath = `${outputDir}/${caseName}-${viewportName}-${theme}-${reducedMotion ? 'reduced' : 'normal'}.png`
          await page.screenshot({
            path: screenshotPath,
            fullPage: true,
          })
          const actual = await readFile(screenshotPath)
          evidence.push({
            id: `${caseName}-${viewportName}-${theme}-${reducedMotion ? 'reduced' : 'normal'}`,
            feature_ids: [caseName.split('-')[0]],
            route,
            viewport: `${width}x${height}`,
            theme,
            reduced_motion: reducedMotion,
            actual_path: screenshotPath,
            actual_sha256: createHash('sha256').update(actual).digest('hex'),
            reference_status: 'NOT_AVAILABLE_SAME_STATE',
            diff_status: 'NOT_RUN',
            result: 'PENDING_REVIEW',
          })
        }
      }
    }
  }
  await writeFile(
    `${outputDir}/manifest.json`,
    JSON.stringify({
      schema: 'notemeld.cloud-visual-matrix.v1',
      commit: ready.build_commit || 'unknown',
      image_digest: ready.image_digest || 'unknown',
      runtime: ready.environment || 'unknown',
      generated_by: 'tests/cloudVisualMatrix.spec.cjs',
      cases: evidence,
    }, null, 2) + '\n',
  )
  await removeNewDevices(page, deviceBaseline)
})

test('captures the Cloud C01 login and access-request matrix', async ({ page }) => {
  test.setTimeout(120_000)
  const viewports = [['wide', 1440, 960], ['tablet', 1024, 768], ['mobile', 390, 844]]
  const evidence = []
  const readyResponse = await page.request.get(`${baseUrl}/ready`)
  const ready = await readyResponse.json()
  await mkdir(outputDir, { recursive: true })
  for (const [viewportName, width, height] of viewports) {
    for (const theme of ['light', 'dark']) {
      for (const reducedMotion of [false, true]) {
        await page.setViewportSize({ width, height })
        await page.emulateMedia({ reducedMotion: reducedMotion ? 'reduce' : 'no-preference' })
        for (const [caseName, route, accessRequest] of [['C01-login', '/cloud/login', false], ['C01-access-request', '/cloud/access-request', true]]) {
          await page.goto(`${baseUrl}${route}`, { waitUntil: 'networkidle' })
          await page.evaluate(nextTheme => {
            document.documentElement.classList.toggle('dark', nextTheme === 'dark')
            localStorage.setItem('notemeld-theme', nextTheme)
          }, theme)
          await page.waitForTimeout(50)
          const screenshotPath = `${outputDir}/${caseName}-${viewportName}-${theme}-${reducedMotion ? 'reduced' : 'normal'}.png`
          await page.screenshot({ path: screenshotPath, fullPage: true })
          const actual = await readFile(screenshotPath)
          evidence.push({
            id: `${caseName}-${viewportName}-${theme}-${reducedMotion ? 'reduced' : 'normal'}`,
            feature_ids: [accessRequest ? 'C01.access-request' : 'C01.auth'],
            route,
            viewport: `${width}x${height}`,
            theme,
            reduced_motion: reducedMotion,
            actual_path: screenshotPath,
            actual_sha256: createHash('sha256').update(actual).digest('hex'),
            reference_status: 'NOT_AVAILABLE_SAME_STATE',
            diff_status: 'NOT_RUN',
            result: 'PENDING_REVIEW',
          })
        }
      }
    }
  }
  const deviceBaseline = await captureDeviceBaseline(page)
  await removeNewDevices(page, deviceBaseline)
  const existingManifest = JSON.parse(await readFile(`${outputDir}/manifest.json`, 'utf8'))
  await writeFile(`${outputDir}/manifest.json`, JSON.stringify({
    ...existingManifest,
    commit: ready.build_commit || existingManifest.commit,
    image_digest: ready.image_digest || existingManifest.image_digest,
    cases: [...evidence, ...existingManifest.cases],
  }, null, 2) + '\n')
})
