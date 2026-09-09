import { useState } from 'react'
import { ChevronRight, Database, Gauge, KeyRound, Monitor, Palette, Settings2, ShieldCheck, SlidersHorizontal } from 'lucide-react'
import { Link } from 'react-router-dom'

const cards = [
  ['通用', '语言、默认工作区和桌面通知', '/settings/model', Settings2],
  ['主题与显示', '浅色、深色和阅读密度', '/settings/model', Palette],
  ['模型与提供商', '配置 Agent 使用的模型和供应商', '/settings/model', SlidersHorizontal],
  ['权限与连接', 'MCP 服务、插件权限和授权状态', '/settings/mcp-servers', KeyRound],
  ['设备', '本机运行时和远程设备连接', '/settings/monitor', Monitor],
  ['数据与安全', '迁移、存储、敏感数据和清理', '/settings/data-migration', Database],
  ['Agent 诊断', '任务、事件流和运行状态', '/settings/agent-diagnostics', Gauge],
  ['安全中心', '候选审批和高风险操作确认', '/settings/candidates', ShieldCheck],
]

export default function SettingsHome() {
  const [density, setDensity] = useState('标准')
  return <div className="nm-settings-home"><header><p className="nm-kicker">D09 · SETTINGS</p><h1>设置</h1><p>配置 NoteMeld 的运行环境、权限和 Agent 行为。</p></header><main><section className="nm-settings-intro"><div><span className="nm-live-dot" /><strong>本地 Agent 已连接</strong><p>所有设置优先保存在当前设备。</p></div><label>阅读密度<select value={density} onChange={event => setDensity(event.target.value)}><option>紧凑</option><option>标准</option><option>宽松</option></select></label></section><div className="nm-settings-card-grid">{cards.map(([title, description, path, Icon]) => <Link key={title} to={path} className="nm-settings-card"><span><Icon /></span><div><h2>{title}</h2><p>{description}</p></div><ChevronRight /></Link>)}</div></main></div>
}
