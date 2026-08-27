import type { ComponentType } from 'react'
import WikiApplication from '@/apps/wiki/WikiApplication'

export interface BuiltInApplicationDefinition {
  id: string
  name: string
  description: string
  capabilities: string[]
  component: ComponentType<{ applicationId: string }>
}

export const WIKI_APPLICATION_ID = 'wiki'

export const getBuiltInApplication = (appId: string): BuiltInApplicationDefinition | undefined => {
  if (appId !== WIKI_APPLICATION_ID) return undefined

  return {
    id: WIKI_APPLICATION_ID,
    name: 'Wiki',
    description: '浏览由 NoteMeld 编译的来源、实体、概念和关系图谱。',
    capabilities: ['wiki.read'],
    component: WikiApplication,
  }
}
