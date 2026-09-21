import { copyFile, mkdir } from 'node:fs/promises'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const packageRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
await mkdir(path.join(packageRoot, 'dist'), { recursive: true })
await copyFile(
  path.join(packageRoot, 'src', 'tokens.css'),
  path.join(packageRoot, 'dist', 'tokens.css'),
)
