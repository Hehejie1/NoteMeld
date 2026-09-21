const { test } = require('playwright/test')
const { mkdir, readFile, readdir, writeFile } = require('fs/promises')
const path = require('path')

const actualDir = process.env.CLOUD_VISUAL_DIR || '/tmp/notemeld-acceptance/cloud-c01-c06/visual-matrix'
const referenceDir = path.join(actualDir, 'reference')
const diffDir = path.join(actualDir, 'diff')
const comparisonDir = path.join(actualDir, 'comparison')

test.use({
  launchOptions: {
    executablePath: process.env.CHROME_EXECUTABLE || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
  },
})

test('compares Cloud actuals with new-product references without claiming visual pass', async ({ page }) => {
  test.setTimeout(180_000)
  await mkdir(diffDir, { recursive: true })
  await mkdir(comparisonDir, { recursive: true })
  const files = (await readdir(referenceDir)).filter(name => name.endsWith('.png'))
  const actualManifest = JSON.parse(await readFile(path.join(actualDir, 'manifest.json'), 'utf8'))
  const referenceManifest = JSON.parse(await readFile(path.join(referenceDir, 'manifest.json'), 'utf8'))
  const cases = []
  for (const name of files) {
    const actualPath = path.join(actualDir, name)
    const referencePath = path.join(referenceDir, name)
    const actual = `data:image/png;base64,${(await readFile(actualPath)).toString('base64')}`
    const reference = `data:image/png;base64,${(await readFile(referencePath)).toString('base64')}`
    const result = await page.evaluate(async ({ actual, reference }) => {
      const load = src => new Promise((resolve, reject) => {
        const image = new Image()
        image.onload = () => resolve(image)
        image.onerror = reject
        image.src = src
      })
      const [actualImage, referenceImage] = await Promise.all([load(actual), load(reference)])
      const width = Math.max(actualImage.naturalWidth, referenceImage.naturalWidth)
      const height = Math.max(actualImage.naturalHeight, referenceImage.naturalHeight)
      const actualCanvas = document.createElement('canvas')
      const referenceCanvas = document.createElement('canvas')
      const diffCanvas = document.createElement('canvas')
      for (const canvas of [actualCanvas, referenceCanvas, diffCanvas]) {
        canvas.width = width
        canvas.height = height
      }
      const actualContext = actualCanvas.getContext('2d')
      const referenceContext = referenceCanvas.getContext('2d')
      const diffContext = diffCanvas.getContext('2d')
      actualContext.fillStyle = '#000'
      actualContext.fillRect(0, 0, width, height)
      actualContext.drawImage(actualImage, 0, 0)
      referenceContext.fillStyle = '#000'
      referenceContext.fillRect(0, 0, width, height)
      referenceContext.drawImage(referenceImage, 0, 0)
      const actualPixels = actualContext.getImageData(0, 0, width, height).data
      const referencePixels = referenceContext.getImageData(0, 0, width, height).data
      const diffPixels = diffContext.createImageData(width, height)
      let changedPixels = 0
      for (let index = 0; index < actualPixels.length; index += 4) {
        const delta = Math.abs(actualPixels[index] - referencePixels[index])
          + Math.abs(actualPixels[index + 1] - referencePixels[index + 1])
          + Math.abs(actualPixels[index + 2] - referencePixels[index + 2])
        if (delta > 24) changedPixels += 1
        diffPixels.data[index] = Math.min(255, delta * 3)
        diffPixels.data[index + 1] = Math.max(0, 255 - Math.min(255, delta * 3))
        diffPixels.data[index + 2] = 32
        diffPixels.data[index + 3] = delta > 24 ? 230 : 48
      }
      diffContext.putImageData(diffPixels, 0, 0)
      return {
        width,
        height,
        actual_width: actualImage.naturalWidth,
        actual_height: actualImage.naturalHeight,
        reference_width: referenceImage.naturalWidth,
        reference_height: referenceImage.naturalHeight,
        changed_pixels: changedPixels,
        total_pixels: width * height,
        diff_data_url: diffCanvas.toDataURL('image/png'),
      }
    }, { actual, reference })
    const diffPath = path.join(diffDir, name)
    await writeFile(diffPath, Buffer.from(result.diff_data_url.split(',')[1], 'base64'))
    const { diff_data_url: _diffDataUrl, ...comparison } = result
    cases.push({
      id: name.replace(/\.png$/, ''),
      actual_path: actualPath,
      reference_path: referencePath,
      diff_path: diffPath,
      ...comparison,
      changed_ratio: comparison.changed_pixels / comparison.total_pixels,
      result: 'PENDING_REVIEW',
      reason: 'Reference is new-product demo state; actual is live Cloud state.',
    })
  }
  await writeFile(`${comparisonDir}/manifest.json`, `${JSON.stringify({
    schema: 'notemeld.cloud-visual-comparison.v1',
    reference_source: 'docs/new-product',
    actual_source: 'cloud-runtime',
    actual_commit: actualManifest.commit || 'unknown',
    actual_image_digest: actualManifest.image_digest || 'unknown',
    actual_runtime: actualManifest.runtime || 'unknown',
    reference_preview_version: referenceManifest.preview_version || 'unknown',
    comparison_status: 'PENDING_REVIEW',
    reason: 'Reference and actual pages do not share the same data state.',
    cases,
  }, null, 2)}\n`)
})
