import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import path from 'node:path'

const root = path.resolve(import.meta.dirname, '..')
const pageSource = await readFile(path.join(root, 'src/pages/LandingPage/index.tsx'), 'utf8')

assert.match(
  pageSource,
  /http:\/\/43\.167\.164\.213\/files\/f_20260602_53c22160366f\.dmg/,
  '官网落地页必须指向最新的 macOS arm64 安装包',
)

assert.match(
  pageSource,
  /http:\/\/43\.167\.164\.213\/files\/f_20260602_4d812951bf4c\.dmg/,
  '官网落地页必须指向最新的 macOS x64 安装包',
)

assert.match(
  pageSource,
  /Apple Silicon|M1\/M2\/M3|arm64/,
  '官网必须明确标注 Apple Silicon 下载入口',
)

assert.match(
  pageSource,
  /Intel|x64/,
  '官网必须明确标注 Intel x64 下载入口',
)
