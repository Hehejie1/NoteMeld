import { useEffect, useState } from 'react'
import CloudClient from '../../services/cloud'

type WorkspaceFile = { path: string; size?: number; modified_at?: number }

export function CloudWorkspaceBrowser({ client, workspaceId }: { client: CloudClient; workspaceId: string }) {
  const [files, setFiles] = useState<WorkspaceFile[]>([])
  const [selected, setSelected] = useState<string | null>(null)
  const [content, setContent] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  useEffect(() => { let active = true; setError(null); void client.listWorkspaceFiles(workspaceId).then(value => { if (active) setFiles(value as WorkspaceFile[]) }).catch(reason => { if (active) setError(reason instanceof Error ? reason.message : 'Unable to list workspace files') }); return () => { active = false } }, [client, workspaceId])
  async function read(path: string) { setSelected(path); setContent(null); setError(null); try { const result = await client.readWorkspaceFile(workspaceId, path) as { content?: string }; setContent(result.content ?? '') } catch (reason) { setError(reason instanceof Error ? reason.message : 'Unable to read workspace file') } }
  if (error && !files.length) return <section role="alert" className="p-3 text-sm text-red-700">{error}</section>
  return <section aria-labelledby="workspace-title" className="grid min-h-40 grid-cols-1 gap-3 p-3 md:grid-cols-[minmax(12rem,18rem)_1fr]"><div><h2 id="workspace-title" className="mb-2 text-base font-semibold text-slate-900">Workspace files</h2>{files.length ? <ul role="list" className="space-y-1">{files.map(file => <li key={file.path}><button type="button" className="w-full truncate rounded px-2 py-1 text-left text-sm hover:bg-slate-100" onClick={() => void read(file.path)}>{file.path}</button></li>)}</ul> : <p role="status" className="text-sm text-slate-500">No readable files.</p>}</div><div className="rounded border border-slate-200 bg-slate-50 p-3"><p className="text-xs text-slate-500">Read-only preview</p>{selected ? <h3 className="mt-1 truncate text-sm font-medium">{selected}</h3> : <p className="mt-3 text-sm text-slate-500">Select a file to view it.</p>}{content !== null ? <pre className="mt-3 max-h-80 overflow-auto whitespace-pre-wrap text-xs text-slate-700">{content}</pre> : null}{error ? <p role="alert" className="mt-2 text-sm text-red-700">{error}</p> : null}</div></section>
}
