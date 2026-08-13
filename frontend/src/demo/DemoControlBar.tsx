import { useEffect, useRef, useState } from 'react'
import { FlaskConical, RotateCcw, X } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import { useTaskStore, type TaskStatus } from '@/store/taskStore'
import { demoRuntime } from './runtime'
import { startDemoNoteScenario, type DemoScenarioHandle, type DemoScenarioOutcome } from './scenarios'

const scenarioRoutes = [
  ['新建', '/new'],
  ['成功笔记', '/notes/demo-note-success'],
  ['生成中', '/notes/demo-note-running'],
  ['失败', '/notes/demo-note-failed'],
  ['已取消', '/notes/demo-note-canceled'],
  ['Wiki 部分成功', '/notes/demo-note-partial'],
] as const

const DemoControlBar = () => {
  const navigate = useNavigate()
  const [open, setOpen] = useState(false)
  const handleRef = useRef<DemoScenarioHandle | null>(null)
  const updateTaskContent = useTaskStore(state => state.updateTaskContent)
  const loadConversations = useTaskStore(state => state.loadConversations)

  useEffect(() => () => handleRef.current?.dispose(), [])

  const run = (outcome: DemoScenarioOutcome) => {
    handleRef.current?.dispose()
    navigate('/notes/demo-note-running')
    handleRef.current = startDemoNoteScenario(outcome, {
      onStatus: status => updateTaskContent('demo-note-running', {
        status: status as TaskStatus,
        message: status === 'SUCCESS' ? '模拟笔记生成完成' : `模拟任务阶段：${status}`,
        ...(status === 'SUCCESS' ? { markdown: '# 模拟生成完成\n\n这是完全在浏览器内生成的演示结果，没有调用后端或模型。' } : {}),
      }),
    })
  }

  const reset = async () => {
    handleRef.current?.dispose()
    demoRuntime.reset()
    await loadConversations()
    navigate('/new')
  }

  if (!open) {
    return (
      <button
        type="button"
        className="fixed right-4 bottom-4 z-[80] flex h-11 items-center gap-2 rounded-full bg-[#18181b] px-4 text-sm font-medium text-white shadow-xl hover:bg-black"
        onClick={() => setOpen(true)}
      >
        <FlaskConical className="h-4 w-4" /> 演示控制
      </button>
    )
  }

  return (
    <aside className="fixed right-4 bottom-4 z-[80] w-[min(92vw,420px)] rounded-2xl border border-border-subtle bg-white p-4 shadow-2xl">
      <div className="mb-3 flex items-center justify-between">
        <div>
          <div className="text-sm font-semibold text-on-surface">静态演示控制</div>
          <div className="text-xs text-on-surface-variant">所有数据和操作都只存在浏览器内存中</div>
        </div>
        <button type="button" className="rounded-lg p-2 hover:bg-surface-container" onClick={() => setOpen(false)} aria-label="关闭演示控制">
          <X className="h-4 w-4" />
        </button>
      </div>
      <div className="mb-3 flex flex-wrap gap-2">
        {scenarioRoutes.map(([label, route]) => (
          <Button key={route} size="sm" variant="outline" onClick={() => navigate(route)}>{label}</Button>
        ))}
      </div>
      <div className="flex flex-wrap gap-2 border-t border-border-subtle pt-3">
        <Button size="sm" onClick={() => run('success')}>模拟成功</Button>
        <Button size="sm" variant="outline" onClick={() => run('failed')}>模拟失败</Button>
        <Button size="sm" variant="outline" onClick={() => run('canceled')}>模拟取消</Button>
        <Button size="sm" variant="ghost" onClick={() => void reset()}><RotateCcw className="mr-1 h-3.5 w-3.5" />重置</Button>
      </div>
    </aside>
  )
}

export default DemoControlBar
