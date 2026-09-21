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

test('Cloud Web renders the primary routes in English', async ({ page }) => {
  const httpErrors = []
  const consoleErrors = []
  page.on('response', response => {
    if (response.status() >= 400 && response.url().includes('/v1/')) httpErrors.push(`${response.status()} ${response.url()}`)
  })
  page.on('console', message => {
    if (message.type() === 'error') consoleErrors.push(message.text())
  })

  await page.goto(`${baseUrl}/cloud/login?returnTo=%2Fcloud%2Fworkbench`)
  await page.getByLabel(/邮箱或用户名|Email or username/).fill(username)
  await page.locator('#cloud-password').fill(password)
  await page.getByRole('button', { name: /登录|Sign in/ }).click()
  await expect(page).toHaveURL(/\/cloud\/workbench/)

  await page.getByRole('link', { name: /设置|Settings/ }).click()
  await page.getByRole('button', { name: /通用|General/ }).click()
  await page.getByLabel(/Cloud 语言|Cloud language|Language/).selectOption('en-US')
  await expect(page.locator('html')).toHaveAttribute('lang', 'en-US')
  await page.getByRole('button', { name: 'Save and sync' }).click()
  await expect(page.getByText(/Saved to Cloud revision/)).toBeVisible()

  const routes = [
    ['AI workspace', 'AI workspace', 'Cloud status synced'],
    ['Cloud sessions', 'Cloud sessions', 'Cloud models'],
    ['People', 'People', 'Members'],
    ['Devices', 'Devices', 'Trusted devices'],
    ['Settings', 'Settings', 'General'],
  ]
  for (const [navLabel, heading, marker] of routes) {
    await page.getByRole('link', { name: navLabel, exact: true }).click()
    await expect(page).toHaveURL(/\/cloud\//)
    await expect(page.getByRole('link', { name: heading, exact: true }).first()).toBeVisible()
    await expect(page.getByText(marker, { exact: true }).first()).toBeVisible()
  }

  expect(httpErrors).toEqual([])
  expect(consoleErrors).toEqual([])
})
