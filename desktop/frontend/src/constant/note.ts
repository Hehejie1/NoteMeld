/* -------------------- 常量 -------------------- */
import {
  BiliBiliLogo,
  DouyinLogo,
  KuaishouLogo,
  LocalLogo,
  WeChatChannelsLogo,
  YoutubeLogo,
} from '@/components/Icons/platform.tsx'

export const noteFormats = [
  { label: '目录', value: 'toc' },
  { label: '原片跳转', value: 'link' },
  { label: '原片截图', value: 'screenshot' },
  { label: 'AI总结', value: 'summary' },
] as const

export const noteStyles = [
  { label: '知识卡片', value: 'knowledge_card' },
  { label: '深度研究', value: 'deep_research' },
  { label: '快速摘要', value: 'quick_summary' },
  { label: '行动清单', value: 'action_list' },
  { label: '会议纪要', value: 'meeting_minutes' },
  { label: '视频解析', value: 'video_analysis' },
  { label: '网页提炼', value: 'web_digest' },
  { label: '工具网站', value: 'tool_website' },
  { label: 'AI 对话沉淀', value: 'ai_conversation' },
] as const

export const videoPlatforms = [
  { label: '哔哩哔哩', value: 'bilibili', logo: BiliBiliLogo },
  { label: 'YouTube', value: 'youtube', logo: YoutubeLogo },
  { label: '抖音', value: 'douyin', logo: DouyinLogo },
  { label: '快手', value: 'kuaishou', logo: KuaishouLogo },
  { label: '视频号', value: 'wechat_channels', logo: WeChatChannelsLogo },
  { label: '网页链接', value: 'web_link', logo: LocalLogo },
  { label: '本地视频', value: 'local', logo: LocalLogo },
] as const
