const { test } = require('playwright/test')
const { createHash } = require('crypto')
const { mkdir, readFile, writeFile } = require('fs/promises')

const baseUrl = process.env.NOTEMELD_NEW_PRODUCT_BASE_URL || 'http://127.0.0.1:8765'
const outputDir = process.env.CLOUD_REFERENCE_DIR || '/tmp/notemeld-acceptance/cloud-c01-c06/visual-matrix/reference'

test.use({
  launchOptions: {
    executablePath: process.env.CHROME_EXECUTABLE || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
  },
})

test('captures the new-product C02-C06 reference matrix', async ({ page }) => {
  test.setTimeout(180_000)
  const cases = [
    ['C01-login', '/pages/cloud/c01.html'],
    ['C01-access-request', '/pages/cloud/c01.html'],
    ['C02-workbench', '/pages/cloud/c02.html'],
    ['C03-sessions', '/pages/cloud/c03.html'],
    ['C04-people', '/pages/cloud/c04.html'],
    ['C05-devices', '/pages/cloud/c05.html'],
    ['C06-settings', '/pages/cloud/c06.html'],
  ]
  const viewports = [
    ['wide', 1440, 960],
    ['tablet', 1024, 768],
    ['mobile', 390, 844],
  ]
  const evidence = []
  const previewResponse = await page.request.get(`${baseUrl}/__new_product_version`)
  const previewVersion = previewResponse.ok() ? (await previewResponse.json()).version : 'unknown'
  await mkdir(outputDir, { recursive: true })
  await page.addInitScript(() => {
    localStorage.setItem('notemeld-theme', 'light')
    sessionStorage.removeItem('notemeld-cloud-token')
  })

  for (const [viewportName, width, height] of viewports) {
    for (const theme of ['light', 'dark']) {
      for (const reducedMotion of [false, true]) {
        await page.setViewportSize({ width, height })
        await page.emulateMedia({ reducedMotion: reducedMotion ? 'reduce' : 'no-preference' })
        for (const [caseName, route] of cases) {
          await page.goto(`${baseUrl}${route}`, { waitUntil: 'networkidle' })
          if (caseName === 'C01-access-request') {
            await page.locator('[data-open-access]').click()
          }
          await page.evaluate(nextTheme => {
            localStorage.setItem('notemeld-theme', nextTheme)
            document.body.classList.toggle('theme-dark', nextTheme === 'dark')
          }, theme)
          await page.waitForTimeout(50)
          const id = `${caseName}-${viewportName}-${theme}-${reducedMotion ? 'reduced' : 'normal'}`
          const screenshotPath = `${outputDir}/${id}.png`
          await page.screenshot({ path: screenshotPath, fullPage: true })
          const reference = await readFile(screenshotPath)
          evidence.push({
            id,
            feature_ids: [caseName.split('-')[0]],
            route,
            viewport: `${width}x${height}`,
            theme,
            reduced_motion: reducedMotion,
            reference_path: screenshotPath,
            reference_sha256: createHash('sha256').update(reference).digest('hex'),
            source: 'docs/new-product',
            reference_status: 'AVAILABLE_DIFFERENT_DATA_STATE',
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
      schema: 'notemeld.cloud-reference-matrix.v1',
      source: 'docs/new-product',
      base_url: baseUrl,
      preview_version: previewVersion,
      generated_by: 'tests/cloudReferenceMatrix.spec.cjs',
      cases: evidence,
    }, null, 2) + '\n',
  )
})
