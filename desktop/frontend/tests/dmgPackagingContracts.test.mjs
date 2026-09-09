import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import path from 'node:path'

const root = path.resolve(import.meta.dirname, '..', '..', '..')
const buildScript = await readFile(path.join(root, 'scripts/desktop/packaging/scripts/build-desktop-macos.sh'), 'utf8')
const buildBackendScript = await readFile(path.join(root, 'scripts/desktop/packaging/scripts/build-backend-macos.sh'), 'utf8')
const skillScript = await readFile(
  path.join(root, '..', '.agents/skills/notemeld-dmg-packaging/scripts/package-notemeld-dmg.sh'),
  'utf8',
)

assert.match(
  buildScript,
  /ln\s+-s\s+\/Applications\s+"\$\{DMG_STAGE_DIR\}\/Applications"/,
  'DMG stage 必须包含 /Applications 快捷方式，避免用户手动打开应用程序目录拖拽',
)

assert.match(
  skillScript,
  /Applications/,
  'NoteMeld DMG packaging skill 必须覆盖 Applications 快捷方式校验，防止后续打包回退',
)

assert.match(
  buildScript,
  /NOTEMELD_CODESIGN_IDENTITY/,
  '桌面打包脚本必须支持 Developer ID 签名身份注入',
)

assert.match(
  buildScript,
  /--options runtime/,
  'Developer ID 签名必须启用 hardened runtime，才能进入 Apple notarization',
)

assert.match(
  skillScript,
  /--release/,
  'DMG packaging skill 必须提供正式发布模式，区分 ad-hoc 本地包和可上架包',
)

assert.match(
  skillScript,
  /notarytool submit/,
  '正式发布模式必须提交 Apple notarization',
)

assert.match(
  skillScript,
  /stapler staple/,
  '正式发布模式必须 staple 公证票据',
)

assert.match(
  skillScript,
  /spctl -a -vv --type execute/,
  '正式发布模式必须用 spctl accepted 作为 Gatekeeper 门禁',
)

assert.match(
  buildBackendScript,
  /otool -L/,
  'macOS 后端打包必须检查 ffmpeg/ffprobe 动态库依赖，避免打入不可分发的 Homebrew 小二进制',
)

assert.match(
  buildBackendScript,
  /\/usr\/local\/Cellar|\/usr\/local\/opt|\/opt\/homebrew/,
  'macOS 后端打包必须拒绝 Homebrew Cellar/opt 动态依赖，避免用户机器缺 dylib 后 ffmpeg 不可用',
)
