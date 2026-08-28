import type { ComponentType } from 'react'
import wikiManifest from '@/apps/wiki/manifest.json'

export interface BuiltInApplicationDefinition {
  id: string
  name: string
  description: string
  capabilities: string[]
  component: ComponentType<{ applicationId: string; runId: string }>
}

export const WIKI_APPLICATION_ID = 'wiki'

export interface BuiltInApplicationCatalogEntry {
  id: string
  name: string
  description: string
  capabilities: string[]
}

export const builtInApplicationCatalog: BuiltInApplicationCatalogEntry[] = [
  { id: wikiManifest.id, name: wikiManifest.name, description: wikiManifest.description, capabilities: wikiManifest.capabilities },
]

export const getBuiltInApplicationCatalogEntry = (appId: string) =>
  builtInApplicationCatalog.find(application => application.id === appId)

export const loadBuiltInApplication = async (appId: string): Promise<BuiltInApplicationDefinition | undefined> => {
  const catalogEntry = getBuiltInApplicationCatalogEntry(appId)
  if (!catalogEntry) return undefined

  if (appId === WIKI_APPLICATION_ID) {
    const { default: WikiApplication } = await import('@/apps/wiki/WikiApplication')
    return { ...catalogEntry, component: WikiApplication }
  }

  return undefined
}
