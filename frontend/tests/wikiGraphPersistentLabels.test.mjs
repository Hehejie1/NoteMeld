import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import path from 'node:path'

const root = path.resolve(import.meta.dirname, '..')
const sigmaGraphSource = await readFile(
  path.join(root, 'src/pages/WikiPage/graph/SigmaWikiGraph.tsx'),
  'utf8',
)
const buildGraphSource = await readFile(
  path.join(root, 'src/pages/WikiPage/graph/buildGraphologyGraph.ts'),
  'utf8',
)

assert.match(
  buildGraphSource,
  /const\s+MIN_PERSISTENT_LABEL_COUNT\s*=\s*3/,
  '知识图谱必须保留至少 3 个常驻标签，避免缩小时只剩无意义原点',
)

assert.match(
  buildGraphSource,
  /forceLabel:\s*persistentLabelNodeIds\.has\(node\.id\)/,
  '关键节点必须通过 forceLabel 常驻显示标签',
)

assert.match(
  buildGraphSource,
  /persistentLabelNodeIds\s*=\s*pickPersistentLabelNodeIds\(payload\)/,
  'buildGraphologyGraph 必须先挑选出一批常驻标签节点',
)

assert.match(
  sigmaGraphSource,
  /labelDensity:\s*0\.16/,
  'Sigma 标签密度应提高，避免缩小时标签过早全部消失',
)

assert.match(
  sigmaGraphSource,
  /labelGridCellSize:\s*96/,
  'Sigma 标签网格应更细，让缩小时仍能留住少量标签',
)

assert.match(
  sigmaGraphSource,
  /labelRenderedSizeThreshold:\s*6/,
  'Sigma 标签尺寸阈值应降低，让关键节点在更小缩放下仍可见',
)
