'use client'
import React, { useEffect } from 'react'
import ReactFlow, { 
  useNodesState, 
  useEdgesState, 
  Background,
  MarkerType
} from 'reactflow'
import 'reactflow/dist/style.css'
import { useQuery } from '@tanstack/react-query'
import api from '@/lib/api'
import { Loader2 } from 'lucide-react'

// Simple node types to avoid heavy icons in the preview
const SimpleNode = ({ data }: any) => (
  <div className={`w-4 h-4 rounded-full shadow-sm border border-white dark:border-slate-800 ${data.color || 'bg-slate-400'}`} />
)

const nodeTypes = {
  skill: SimpleNode,
  job: SimpleNode,
  company: SimpleNode,
  user: SimpleNode
}

export function GraphMiniMap() {
  const [nodes, setNodes] = useNodesState([])
  const [edges, setEdges] = useEdgesState([])

  const { data: graphData, isLoading, isError } = useQuery({
    queryKey: ['knowledge-graph-preview'],
    queryFn: async () => {
      // silent:true — the graph endpoint can legitimately fail for new users
      // with no applications yet; don't spam them with toasts.
      const { data } = await api.get('/graph', { silent: true })
      return data
    },
    retry: false,
  })

  useEffect(() => {
    if (graphData) {
      const mappedNodes = graphData.nodes.map((n: any) => ({
          ...n,
          type: n.type || 'skill',
          data: { ...n.data, color: n.type === 'skill' ? '#10b981' : n.type === 'job' ? '#f59e0b' : '#6366f1' },
          draggable: false,
          selectable: false,
          connectable: false
      }))
      
      const mappedEdges = graphData.edges.map((e: any) => ({
          ...e,
          type: 'straight',
          animated: false,
          style: { stroke: '#cbd5e1', strokeWidth: 1 },
          markerEnd: {
              type: MarkerType.ArrowClosed,
              color: '#cbd5e1',
              width: 10,
              height: 10
          },
      }))

      setNodes(mappedNodes)
      setEdges(mappedEdges)
    }
  }, [graphData, setNodes, setEdges])

  if (isLoading) {
    return (
      <div className="h-full w-full flex items-center justify-center bg-slate-50/50 dark:bg-slate-900/50 rounded-xl">
        <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
      </div>
    )
  }

  if (isError || !graphData || (graphData.nodes || []).length === 0) {
    return (
      <div className="h-full w-full flex items-center justify-center bg-slate-50/50 dark:bg-slate-900/50 rounded-xl text-xs text-muted-foreground italic px-4 text-center">
        Graph will appear once you have applications.
      </div>
    )
  }

  return (
    <div className="h-full w-full grayscale opacity-60 hover:grayscale-0 hover:opacity-100 transition-all duration-500 cursor-pointer">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        fitView
        nodesDraggable={false}
        nodesConnectable={false}
        elementsSelectable={false}
        panOnDrag={false}
        zoomOnScroll={false}
        zoomOnPinch={false}
        zoomOnDoubleClick={false}
      >
        <Background gap={20} size={1} color="#e5e7eb" />
      </ReactFlow>
    </div>
  )
}
