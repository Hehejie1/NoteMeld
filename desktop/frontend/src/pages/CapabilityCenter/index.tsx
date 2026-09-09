import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Bot, Cable, PackageOpen, Puzzle, Sparkles } from 'lucide-react'
import ApplicationList from '@/pages/Applications'
import Plugins from '@/pages/SettingPage/Plugins'
import McpServers from '@/pages/SettingPage/McpServers'

type CapabilityTab = 'plugins' | 'skills' | 'connectors' | 'applications' | 'agents'

const tabs: Array<[CapabilityTab, string, typeof Puzzle]> = [
  ['plugins', '插件', Puzzle],
  ['skills', '技能', Sparkles],
  ['connectors', '连接器', Cable],
  ['applications', '应用', PackageOpen],
  ['agents', '智能体', Bot],
]

export default function CapabilityCenter() {
  const [tab, setTab] = useState<CapabilityTab>('plugins')
  const navigate = useNavigate()
  return <div className="nm-capability-page"><header className="nm-capability-header"><div><p className="nm-kicker">D06 · CAPABILITY CENTER</p><h1>插件应用</h1><p>管理 Skills、MCP、插件、Application 和智能体能力。</p></div><div className="nm-capability-header-meta"><span>本地能力目录</span><span className="nm-live-dot" />安全沙箱</div></header><nav className="nm-capability-tabs" aria-label="能力类型" role="tablist">{tabs.map(([id, label, Icon]) => <button key={id} role="tab" aria-selected={tab === id} onClick={() => setTab(id)}><Icon />{label}</button>)}</nav><main className="nm-capability-content">{tab === 'plugins' && <Plugins />}{tab === 'applications' && <ApplicationList />}{tab === 'skills' && <SkillCatalog onSelect={prompt => { navigate('/new'); window.setTimeout(() => window.dispatchEvent(new CustomEvent('notemeld:prefill-research', { detail: { prompt } })), 0) }} />}{tab === 'connectors' && <McpServers />}{tab === 'agents' && <AgentCatalog />}</main></div>
}

function SkillCatalog({ onSelect }: { onSelect: (prompt: string) => void }) { const skills = [['代码审查', '检查当前工作区的实现、风险和测试缺口。'], ['架构设计', '围绕目标拆解模块、依赖和演进方案。'], ['文档驱动', '从需求建立可执行的实现清单和验收标准。'], ['界面工程', '设计并实现可访问、可响应的产品界面。']] as const; return <section className="grid gap-4 p-5 md:p-8"><div><h2 className="text-xl font-semibold text-on-surface">技能</h2><p className="mt-1 text-sm text-on-surface-variant">选择技能会打开新对话，并将任务模板填入 Agent 输入框。</p></div><div className="grid gap-3 md:grid-cols-2">{skills.map(([title, description]) => <button type="button" key={title} onClick={() => onSelect(description)} className="rounded-xl border border-border-subtle bg-surface-container-lowest p-4 text-left transition hover:border-primary/40 hover:shadow-sm"><h3 className="font-medium text-on-surface">{title}</h3><p className="mt-2 text-xs text-on-surface-variant">{description}</p><span className="mt-3 block text-xs font-medium text-primary">在新对话中使用 →</span></button>)}</div></section> }

function AgentCatalog() { const agents = [['架构分析 Agent', '读取 Workspace、梳理依赖并输出风险清单。', '本地 · 可用'], ['研究检索 Agent', '围绕主题收集来源，保留引用和可验证结论。', '本地 · 需配置搜索'], ['发布检查 Agent', '检查产物、权限和发布前的测试状态。', '本地 · 可用']] as const; return <section className="nm-agent-catalog"><div><p className="nm-kicker">AGENT ROSTER</p><h2>智能体</h2><p>管理可协作的专用 Agent，以及它们能读取和写入的数据范围。</p></div><div className="nm-agent-grid">{agents.map(([name, description, status]) => <article key={name}><div className="nm-agent-icon"><Bot /></div><div><h3>{name}</h3><p>{description}</p><small>{status}</small></div><button type="button">查看详情</button></article>)}</div></section> }
