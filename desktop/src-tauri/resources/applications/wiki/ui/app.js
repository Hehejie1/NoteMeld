const params = new URLSearchParams(location.search)
const appId = params.get('app_id') || 'wiki'
const runId = params.get('run_id') || ''
const graphElement = document.querySelector('#graph')
const sideElement = document.querySelector('#side')
let graph = { nodes: [], edges: [], clusters: [] }
let mode = 'type'
let resolveHostReady
const hostReady = new Promise(resolve => { resolveHostReady = resolve })
const readyMessage = { type: 'notemeld.application.ready', app_id: appId, run_id: runId }
const readyTimer = setInterval(() => window.parent.postMessage(readyMessage, '*'), 250)

window.addEventListener('message', event => {
  if (event.data?.type === 'notemeld.application.host-ready' && event.data.run_id === runId) {
    clearInterval(readyTimer)
    resolveHostReady()
  }
})
window.parent.postMessage(readyMessage, '*')

const invoke = (capability, method, input = {}) => new Promise((resolve, reject) => {
  const requestId = crypto.randomUUID()
  const timer = setTimeout(() => reject(new Error('Host Bridge 请求超时')), 10000)
  const listener = event => {
    const message = event.data
    if (!message || message.type !== 'notemeld.application.result' || message.request_id !== requestId) return
    clearTimeout(timer)
    window.removeEventListener('message', listener)
    if (message.ok) resolve(message.result)
    else reject(new Error(message.error?.message || 'Host Bridge 调用失败'))
  }
  window.addEventListener('message', listener)
  // The Host sandbox gives this document an opaque origin. The parent validates
  // the exact iframe window before accepting or answering any request.
  window.parent.postMessage({ type: 'notemeld.application.invoke', request_id: requestId, app_id: appId, run_id: runId, capability, method, input }, '*')
})

const nodeColor = node => mode === 'community' ? (node.community_color || '#8b5cf6') : ({ source: '#2563eb', concept: '#7c3aed', entity: '#059669', video: '#ea580c' }[node.type] || '#64748b')

function render() {
  const nodes = graph.nodes || []
  const width = 900; const height = 600
  const positions = new Map(nodes.map((node, index) => [node.id, { x: 100 + (index % 5) * 170, y: 130 + Math.floor(index / 5) * 150 }]))
  const edges = (graph.edges || []).map(edge => { const from = positions.get(edge.source); const to = positions.get(edge.target); return from && to ? `<line class="edge" x1="${from.x}" y1="${from.y}" x2="${to.x}" y2="${to.y}"/>` : '' }).join('')
  const circles = nodes.map(node => { const position = positions.get(node.id); return `<g data-node="${escapeHtml(node.id)}"><circle class="node" cx="${position.x}" cy="${position.y}" r="${Math.max(8, Math.min(22, node.size || 12))}" fill="${nodeColor(node)}"/><text class="node-label" x="${position.x + 14}" y="${position.y + 4}">${escapeHtml(node.label || node.id)}</text></g>` }).join('')
  graphElement.innerHTML = `${edges}${circles}`
  graphElement.querySelectorAll('[data-node]').forEach(element => element.addEventListener('click', () => selectNode(element.dataset.node)))
}

function escapeHtml(value) { return String(value).replace(/[&<>"']/g, character => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[character])) }

function selectNode(id) {
  const node = graph.nodes.find(item => item.id === id)
  if (!node) return
  sideElement.innerHTML = `<h2>${escapeHtml(node.label || node.id)}</h2><p class="muted">类型：${escapeHtml(node.type || '未知')}<br/>节点 ID：${escapeHtml(node.id)}</p><div class="card"><button id="article">查看文章详情</button></div><div id="article-content"></div>`
  document.querySelector('#article').addEventListener('click', async () => {
    const content = document.querySelector('#article-content')
    content.innerHTML = '<p class="muted">正在读取文章…</p>'
    try { const article = await invoke('wiki.read', 'article', { source_id: node.id }); content.innerHTML = `<div class="card"><strong>${escapeHtml(article.title || node.label)}</strong><p class="muted">${escapeHtml(article.summary || '暂无摘要')}</p></div>` } catch (error) { content.innerHTML = `<p class="error">${escapeHtml(error.message)}</p>` }
  })
}

async function load() {
  // Do not deadlock if an older Host misses the optional handshake. The Bridge
  // request itself is still validated by app/run identity at the Host.
  await Promise.race([hostReady, new Promise(resolve => setTimeout(resolve, 500))])
  sideElement.innerHTML = '<h2>Wiki</h2><p class="muted">正在读取知识图谱…</p>'
  try { graph = await invoke('wiki.read', 'graph'); render(); sideElement.innerHTML = `<h2>Wiki</h2><p class="muted">${graph.nodes?.length || 0} 个节点，${graph.edges?.length || 0} 条关系。</p><p class="muted">点击节点查看详情。</p>` } catch (error) { sideElement.innerHTML = `<h2>Wiki</h2><p class="error">${escapeHtml(error.message)}</p>` }
}

document.querySelector('#refresh').addEventListener('click', load)
document.querySelectorAll('[data-mode]').forEach(button => button.addEventListener('click', () => { mode = button.dataset.mode; document.querySelectorAll('[data-mode]').forEach(item => item.classList.toggle('active', item === button)); render() }))
load()
