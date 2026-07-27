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

  forceAtlas2.assign(graph, {
    iterations: 180,
    settings: LAYOUT_SETTINGS,
  })

  return graph
}
