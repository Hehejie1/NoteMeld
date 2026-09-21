export type DemoMethod = 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE'

export interface DemoRequest {
  method: DemoMethod
  path: string
  body?: unknown
  query?: Record<string, unknown>
}

export type DemoListener = () => void

export interface DemoSnapshot {
  conversations: Array<Record<string, unknown>>
  taskStatuses: Record<string, Record<string, unknown>>
  styles: Array<Record<string, unknown>>
  settings: Record<string, unknown>
}

export interface DemoFixtureSeed extends DemoSnapshot {
  wikiGraph: Record<string, unknown>
}

export interface DemoRuntime {
  request<T = unknown>(request: DemoRequest): Promise<T>
  reset(): void
  subscribe(listener: DemoListener): () => void
  getSnapshot(): DemoSnapshot
}
