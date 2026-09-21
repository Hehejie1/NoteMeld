import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'

interface Props {
  open: boolean
  phase?: string
  failureKind?: 'runtime' | 'backend'
  onRetry: () => void
  onClose: () => void
}

const phaseMessages: Record<string, string> = {
  runtime: '正在准备桌面运行时配置…',
  sys_check: '正在连接后端服务…',
  retry_wait: '后端暂未就绪，正在等待重试…',
  sys_health: '正在确认后端健康状态…',
  ready: '后端已就绪，正在进入工作区…',
}

function BackendInitDialog({ open, phase, failureKind, onRetry, onClose }: Props) {
  const title = failureKind === 'runtime' ? '桌面运行时初始化失败' : '后端服务初始化失败'
  const message =
    failureKind === 'runtime'
      ? '桌面环境尚未完成初始化，暂时无法连接后端服务。你可以立即重试，或先关闭提示继续浏览页面。'
      : phase
        ? phaseMessages[phase] || '请稍候，系统正在启动后端服务…'
        : '请稍候，系统正在启动后端服务…'

  return (
    <Dialog open={open}>
      <DialogContent className="text-center" showCloseButton={false}>
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
        </DialogHeader>
        <DialogDescription className="mt-2">
          {message} 你可以先继续浏览页面，也可以稍后重试连接。
        </DialogDescription>
        <DialogFooter className="sm:justify-center">
          <Button variant="outline" onClick={onClose}>
            关闭
          </Button>
          <Button onClick={onRetry}>重试</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
export default BackendInitDialog
