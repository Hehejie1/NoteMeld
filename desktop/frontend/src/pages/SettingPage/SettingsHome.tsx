import { ChevronRight, Database, Gauge, KeyRound, Monitor, ShieldCheck, SlidersHorizontal, Captions, HardDriveDownload, Plug } from 'lucide-react'
import { Link } from 'react-router-dom'
import { useBackendInitContext } from '@/contexts/BackendInitContext'

const groups = [
  { title: '模型与输入', description: '决定 Agent 如何理解和处理内容。', items: [
    ['AI 模型与提供商', '模型、默认值和连接探测', '/settings/model', SlidersHorizontal],
    ['音频转写', 'Whisper 配置与转写参数', '/settings/transcriber', Captions],
    ['下载器', '平台下载与 Cookie 配置', '/settings/download', HardDriveDownload],
  ] },
  { title: '连接与运行', description: '管理外部能力、本机状态和诊断信息。', items: [
    ['MCP 服务器', '工具连接、授权和可用性', '/settings/mcp-servers', Plug],
    ['设备与部署', '本机、远程设备和运行时状态', '/settings/monitor', Monitor],
    ['Agent 诊断', '任务、事件流和运行状态', '/settings/agent-diagnostics', Gauge],
  ] },
  { title: '数据与安全', description: '控制数据边界、审批和迁移操作。', items: [
    ['数据与迁移', '导入导出、索引和存储', '/settings/data-migration', Database],
    ['应用与权限', '应用、插件和外部文件权限', '/settings/applications', KeyRound],
    ['安全中心', '候选审批和高风险操作确认', '/settings/candidates', ShieldCheck],
  ] },
]

export default function SettingsHome() {
  const { backendReady } = useBackendInitContext()
  return <div className="nm-settings-home"><header><p className="nm-kicker">D09 · SETTINGS</p><h1>设置</h1><p>配置 NoteMeld 的运行环境、权限和 Agent 行为。</p></header><main><section className="nm-settings-intro"><div><span className={backendReady ? 'nm-live-dot' : 'nm-live-dot is-pending'} /><strong>{backendReady ? '本地 Agent 已连接' : '正在连接本地 Agent'}</strong><p>设置优先保存在当前设备，状态会随运行时实时更新。</p></div><div className="nm-settings-intro-meta"><span>当前设备</span><strong>Desktop</strong></div></section><div className="nm-settings-groups">{groups.map(group => <section key={group.title} className="nm-settings-group"><div className="nm-settings-group-heading"><h2>{group.title}</h2><p>{group.description}</p></div><div className="nm-settings-card-grid">{group.items.map(([title, description, path, Icon]) => <Link key={title} to={path} className="nm-settings-card"><span><Icon /></span><div><h3>{title}</h3><p>{description}</p></div><ChevronRight /></Link>)}</div></section>)}</div></main></div>
}
