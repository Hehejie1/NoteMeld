import { Outlet } from 'react-router-dom'
import React from 'react'

interface ISettingLayoutProps {
  Menu: React.ReactNode
}
const SettingLayout = ({ Menu }: ISettingLayoutProps) => {
  return (
    <div className="flex h-full w-full flex-col bg-surface">
      {/* 顶部横向 Tab */}
      <header className="shrink-0 border-b border-border-subtle/60 bg-white">
        <div className="overflow-x-auto px-3 pt-1 md:px-8 md:pt-2">
          <div className="-mb-px min-w-max">{Menu}</div>
        </div>
      </header>

      {/* 主区 */}
      <main className="flex min-h-0 flex-1 flex-col overflow-hidden bg-white">
        <Outlet />
      </main>
    </div>
  )
}
export default SettingLayout
