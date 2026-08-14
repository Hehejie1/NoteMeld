import forceAtlas2 from 'graphology-layout-forceatlas2'

import type { WikiGraphologyGraph } from './buildGraphologyGraph'

const LAYOUT_SETTINGS = {
  gravity: 0.03,
  scalingRatio: 14,
  strongGravityMode: false,
  slowDown: 1.2,
  barnesHutOptimize: true,
  barnesHutTheta: 0.6,
}

export const runInitialLayout = (graph: WikiGraphologyGraph): WikiGraphologyGraph => {
  if (graph.order <= 1) return graph

  if (graph.size === 0) {
    const radius = Math.max(6, Math.min(16, graph.order * 1.4))
    const nodeIds = graph.nodes()
    nodeIds.forEach((nodeId, index) => {
      const angle = (index / nodeIds.length) * Math.PI * 2 - Math.PI / 2
      graph.setNodeAttribute(nodeId, 'x', Math.cos(angle) * radius)
      graph.setNodeAttribute(nodeId, 'y', Math.sin(angle) * radius)
    })
    return graph
  }

  forceAtlas2.assign(graph, {
    iterations: 180,
    settings: LAYOUT_SETTINGS,
  })

  return graph
}
