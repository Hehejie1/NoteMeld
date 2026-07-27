import { readFile } from 'node:fs/promises'
import assert from 'node:assert/strict'
import path from 'node:path'

const root = path.resolve(import.meta.dirname, '..')
const cargo = await readFile(path.join(root, '../desktop/src-tauri/Cargo.toml'), 'utf8')
const lib = await readFile(path.join(root, '../desktop/src-tauri/src/lib.rs'), 'utf8')

assert.match(cargo, /tauri-plugin-autostart/, '桌面端必须依赖 tauri-plugin-autostart')
assert.match(lib, /tauri_plugin_autostart/, '桌面端必须初始化 autostart 插件')
assert.match(lib, /get_autostart_enabled/, '桌面端必须暴露读取开机启动状态命令')
assert.match(lib, /set_autostart_enabled/, '桌面端必须暴露设置开机启动状态命令')
