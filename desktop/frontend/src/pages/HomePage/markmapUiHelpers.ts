export interface MarkmapToolbarButtonDef {
  id: 'xmind' | 'png' | 'fullscreen'
  label: string
  title: string
}

export const getMarkmapToolbarButtons = (isFullscreen: boolean): MarkmapToolbarButtonDef[] => [
  {
    id: 'xmind',
    label: '导出 XMind',
    title: '导出 XMind 脑图',
  },
  {
    id: 'png',
    label: '导出 PNG',
    title: '导出 PNG 图片',
  },
  {
    id: 'fullscreen',
    label: isFullscreen ? '退出全屏' : '全屏',
    title: isFullscreen ? '退出全屏' : '进入全屏',
  },
]

export const shouldShowTaskStatusToast = (status?: string): boolean => status === 'SUCCESS'
