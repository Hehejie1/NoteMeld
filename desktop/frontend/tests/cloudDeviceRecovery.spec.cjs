const { test, expect } = require('playwright/test')

const baseUrl = process.env.CLOUD_TEST_BASE_URL || 'http://127.0.0.1:18583'
const username = process.env.CLOUD_TEST_USERNAME || 'hehejie'
const password = process.env.CLOUD_TEST_PASSWORD

test.use({
  launchOptions: {
    executablePath: process.env.CHROME_EXECUTABLE || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
  },
})

test.skip(!password, 'CLOUD_TEST_PASSWORD is required for live Cloud acceptance')

test('recovers the session list after an inactive-device response', async ({ page }) => {
  let injectedFailure = false
  await page.route('**/v1/cloud/sessions?archived=false', async route => {
    if (!injectedFailure) {
      injectedFailure = true
      await route.fulfill({
        status: 403,
        contentType: 'application/json',
        body: JSON.stringify({ detail: 'device is not active for this account' }),
      })
      return
    }
    await route.continue()
  })

  await page.goto(`${baseUrl}/cloud/login?returnTo=%2Fcloud%2Fsessions`)
  await page.getByLabel(/邮箱或用户名|Email or username/).fill(username)
  await page.locator('#cloud-password').fill(password)
  await page.getByRole('button', { name: /登录|Sign in/ }).click()
  await expect(page).toHaveURL(/\/cloud\/sessions/)
  await expect(page.getByRole('heading', { name: /会话|sessions/i }).first()).toBeVisible()
  await expect(page.getByText(/会话读取失败|Unable to load sessions/)).toHaveCount(0)
  await expect(page.getByRole('button', { name: /新建会话|\+ New session/ }).first()).toBeEnabled()
  expect(injectedFailure).toBe(true)
})
