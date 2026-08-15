import { memo } from 'react'
import {
  BaseEdge,
  EdgeLabelRenderer,
  getBezierPath,
  getSmoothStepPath,
  getStraightPath,
  type EdgeProps,
} from '@xyflow/react'
import type { WhiteboardFlowEdge } from './whiteboardProjection'

function WhiteboardRelationEdge(props: EdgeProps<WhiteboardFlowEdge>) {
  const relation = props.data?.relation
  const pathInput = {
    sourceX: props.sourceX,
    sourceY: props.sourceY,
    sourcePosition: props.sourcePosition,
    targetX: props.targetX,
    targetY: props.targetY,
    targetPosition: props.targetPosition,
  }
  const [path, labelX, labelY] = relation?.line_type === 'straight'
    ? getStraightPath(pathInput)
    : relation?.line_type === 'smoothstep'
      ? getSmoothStepPath(pathInput)
      : getBezierPath(pathInput)

  return (
    <>
      <BaseEdge
        path={path}
        markerStart={props.markerStart}
        markerEnd={props.markerEnd}
        style={props.style}
        interactionWidth={28}
      />
      {relation?.label ? (
        <EdgeLabelRenderer>
          <div
            className={`pointer-events-none absolute max-w-40 -translate-x-1/2 -translate-y-1/2 truncate rounded-full border bg-white/95 px-2 py-1 text-[10px] shadow-sm ${
              props.selected ? 'border-primary text-primary' : 'border-border-subtle text-on-surface-variant'
            }`}
            style={{ transform: `translate(-50%, -50%) translate(${labelX}px, ${labelY}px)` }}
            title={relation.description || relation.label}
          >
            {relation.label}
          </div>
        </EdgeLabelRenderer>
      ) : null}
    </>
  )
}

export default memo(WhiteboardRelationEdge)
