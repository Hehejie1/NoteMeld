import { Outlet } from 'react-router-dom'
import React from 'react'

interface ISettingLayoutProps {
  Menu: React.ReactNode
}
const SettingLayout = ({ Menu }: ISettingLayoutProps) => {
  return (
    <div className="desktop-settings-layout flex h-full w-full bg-surface">
      <aside className="desktop-settings-sidebar shrink-0 border-r border-border-subtle/60 bg-surface-container-lowest p-3 md:p-5">
        <div className="mb-4 px-2"><p className="text-[10px] font-semibold tracking-[0.16em] text-primary">D09 · SETTINGS</p><h1 className="mt-1 text-lg font-semibold text-on-surface">设置</h1></div>
        <div className="desktop-settings-menu">{Menu}</div>
      </aside>
      <main className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden bg-surface-container-lowest">
        <Outlet />
      </main>
    </div>
  )
}
export default SettingLayout
