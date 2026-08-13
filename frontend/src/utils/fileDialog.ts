import { isDesktopEmbedded } from './runtime'
import type * as DialogPlugin from '@tauri-apps/plugin-dialog'
import { isDemoMode } from '@/demo/mode'
import { demoDesktopAction } from '@/demo/transport'

type DialogSelection = string | string[] | null
type DialogModule = typeof DialogPlugin

let dialogModulePromise: Promise<DialogModule> | null = null

function normalizeDialogSelection(selection: DialogSelection): string | null {
  if (Array.isArray(selection)) {
    return selection.find(item => typeof item === 'string' && item.trim()) || null
  }
  return typeof selection === 'string' && selection.trim() ? selection : null
}

async function openDesktopDialog(options: Record<string, unknown>): Promise<string | null> {
  if (!isDesktopEmbedded()) {
    return null
  }

  const { open } = await loadDesktopDialogModule()
  const selection = (await open(options)) as DialogSelection
  return normalizeDialogSelection(selection)
}

function loadDesktopDialogModule(): Promise<DialogModule> {
  dialogModulePromise ||= import('@tauri-apps/plugin-dialog')
  return dialogModulePromise
}

export function preloadDesktopFileDialog(): void {
  if (isDesktopEmbedded()) {
    void loadDesktopDialogModule()
  }
}

export function canUseNativeFileDialog(): boolean {
  return isDesktopEmbedded()
}

export async function selectMigrationPackagePath(): Promise<string | null> {
  if (isDemoMode()) return await demoDesktopAction('select_migration_package') as string
  return await openDesktopDialog({
    directory: false,
    multiple: false,
    title: '选择迁移包文件',
    filters: [{ name: 'Migration Package', extensions: ['zip'] }],
  })
}

export async function selectExportPackagePath(defaultName?: string): Promise<string | null> {
  if (isDemoMode()) return await demoDesktopAction('select_export_package', defaultName) as string
  if (!isDesktopEmbedded()) {
    return null
  }
  const { save } = await loadDesktopDialogModule()
  const defaultPath = defaultName
    ? (/\.zip$/i.test(defaultName) ? defaultName : `${defaultName}.zip`)
    : 'migration.zip'
  const selection = await save({
    title: '保存迁移包',
    defaultPath,
    filters: [{ name: 'Migration Package', extensions: ['zip'] }],
  })
  return typeof selection === 'string' ? selection : null
}
