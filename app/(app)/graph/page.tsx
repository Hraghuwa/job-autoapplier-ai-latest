'use client'
import React, { useCallback, useEffect } from 'react'
import ReactFlow, { 
  useNodesState, 
  useEdgesState, 
  addEdge, 
  Background, 
  Controls, 
  MiniMap,
  MarkerType
} from 'reactflow'
import 'reactflow/dist/style.css'
import { useQuery, useMutation } from '@tanstack/react-query'
import api from '@/lib/api'
import { Zap, Building2, Target, X, Briefcase, ExternalLink, Sparkles, RefreshCw, Share2, Loader2 } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Handle, Position } from 'reactflow'

const SkillNode = ({ data }: any) => (
  <div className="px-3 py-2 shadow-xl rounded-xl bg-white dark:bg-slate-900 border-2 border-emerald-500/30 min-w-[140px]">
    <Handle type="target" position={Position.Top} className="w-2 h-2 !bg-emerald-500" />
    <div className="flex items-center gap-2">
      <div className="flex-shrink-0 w-8 h-8 rounded-lg bg-emerald-100 dark:bg-emerald-900/30 flex items-center justify-center text-emerald-600">
        <Zap size={14} />
      </div>
      <div className="flex-1 min-w-0">
        <p className="text-[11px] font-bold text-emerald-600 uppercase tracking-wider">Skill</p>
        <p className="text-sm font-bold truncate text-foreground">{data.label}</p>
      </div>
    </div>
    <Handle type="source" position={Position.Bottom} className="w-2 h-2 !bg-emerald-500" />
  </div>
)

const JobNode = ({ data }: any) => (
  <div className="px-3 py-2 shadow-xl rounded-xl bg-white dark:bg-slate-900 border-2 border-amber-500/30 min-w-[140px]">
    <Handle type="target" position={Position.Top} className="w-2 h-2 !bg-amber-500" />
    <div className="flex items-center gap-2">
      <div className="flex-shrink-0 w-8 h-8 rounded-lg bg-amber-100 dark:bg-amber-900/30 flex items-center justify-center text-amber-600">
        <Briefcase size={14} />
      </div>
      <div className="flex-1 min-w-0">
        <p className="text-[11px] font-bold text-amber-600 uppercase tracking-wider">Opportunity</p>
        <p className="text-sm font-bold truncate text-foreground">{data.label}</p>
      </div>
    </div>
    <Handle type="source" position={Position.Bottom} className="w-2 h-2 !bg-amber-500" />
  </div>
)

const CompanyNode = ({ data }: any) => (
  <div className="px-3 py-2 shadow-xl rounded-xl bg-white dark:bg-slate-900 border-2 border-indigo-500/30 min-w-[140px]">
    <Handle type="target" position={Position.Top} className="w-2 h-2 !bg-indigo-500" />
    <div className="flex items-center gap-2">
      <div className="flex-shrink-0 w-8 h-8 rounded-lg bg-indigo-100 dark:bg-indigo-900/30 flex items-center justify-center text-indigo-600">
        <Building2 size={14} />
      </div>
      <div className="flex-1 min-w-0">
        <p className="text-[11px] font-bold text-indigo-600 uppercase tracking-wider">Company</p>
        <p className="text-sm font-bold truncate text-foreground">{data.label}</p>
      </div>
    </div>
    <Handle type="source" position={Position.Bottom} className="w-2 h-2 !bg-indigo-500" />
  </div>
)

const UserNode = ({ data }: any) => (
  <div className="px-4 py-3 shadow-2xl rounded-2xl bg-indigo-600 text-white border-4 border-white dark:border-slate-800 scale-110">
    <div className="flex items-center gap-3">
      <div className="w-10 h-10 rounded-full bg-white/20 flex items-center justify-center">
        <Target size={20} />
      </div>
      <div className="pr-2">
        <p className="text-[10px] font-bold uppercase tracking-widest text-indigo-100">Profile</p>
        <p className="text-lg font-black leading-tight">YOU</p>
      </div>
    </div>
    <Handle type="source" position={Position.Bottom} className="w-3 h-3 !bg-white" />
  </div>
)

const nodeTypes = {
  skill: SkillNode,
  job: JobNode,
  company: CompanyNode,
  user: UserNode
}

export default function KnowledgeGraphPage() {
  const [nodes, setNodes, onNodesChange] = useNodesState([])
  const [edges, setEdges, onEdgesChange] = useEdgesState([])
  const [selectedNode, setSelectedNode] = React.useState<any>(null)

  const { data: graphData, isLoading, refetch } = useQuery({
    queryKey: ['knowledge-graph'],
    queryFn: async () => {
      const { data } = await api.get('/graph', { silent: true })
      return data
    },
    retry: false,
  })

  // Mutation for updating positions
  const { mutate: updatePositions } = useMutation({
    mutationFn: (positions: any[]) => api.put('/graph/positions', { positions })
  })

  const onNodeDragStop = useCallback((_: any, node: any) => {
    updatePositions([{
        node_id: node.id,
        x: node.position.x,
        y: node.position.y
    }])
  }, [updatePositions])

  const resetLayout = useCallback(async () => {
    try {
      await api.delete('/graph/positions')
      refetch()
    } catch {
      refetch()
    }
  }, [refetch])

  useEffect(() => {
    if (graphData) {
      // Map the backend nodes to React Flow format
      const mappedNodes = graphData.nodes.map((n: any) => ({
          ...n,
          position: n.position || { x: Math.random() * 400, y: Math.random() * 400 },
          style: {
              background: n.color || '#fff',
              color: '#fff',
              borderRadius: '8px',
              padding: '10px',
              width: 150,
              textAlign: 'center',
              fontWeight: 'bold',
              border: 'none',
              boxShadow: '0 4px 6px -1px rgb(0 0 0 / 0.1)'
          }
      }))
      
      const mappedEdges = graphData.edges.map((e: any) => ({
          ...e,
          type: 'smoothstep',
          animated: e.animated,
          labelStyle: { fill: '#64748b', fontWeight: 700, fontSize: 10 },
          markerEnd: {
              type: MarkerType.ArrowClosed,
              color: e.style?.stroke || '#b1b1b7',
              width: 20,
              height: 20
          },
      }))

      setNodes(mappedNodes)
      setEdges(mappedEdges)
    }
  }, [graphData, setNodes, setEdges])

  const onConnect = useCallback(
    (params: any) => setEdges((eds) => addEdge(params, eds)),
    [setEdges]
  )

  return (
    <div className="flex flex-col h-[calc(100vh-120px)] space-y-4">
      <div className="flex justify-between items-center">
        <div>
          <h1 className="font-display text-2xl font-bold tracking-tight">Knowledge Graph</h1>
          <p className="text-[hsl(var(--muted-foreground))] mt-1">
            Visualize your professional ecosystem and job matching clusters.
          </p>
        </div>
        <div className="flex gap-2">
            <button 
                onClick={() => refetch()}
                className="inline-flex items-center gap-2 px-3 py-1.5 rounded-lg border border-[hsl(var(--border))] bg-[hsl(var(--card))] text-xs font-semibold hover:bg-[hsl(var(--color-surface-2))] transition-colors"
            >
                <Loader2 className={`h-3 w-3 ${isLoading ? 'animate-spin' : ''}`} />
                Refresh Graph
            </button>
            <button 
                onClick={resetLayout}
                className="inline-flex items-center gap-2 px-3 py-1.5 rounded-lg border border-[hsl(var(--border))] bg-[hsl(var(--card))] text-xs font-semibold hover:bg-[hsl(var(--color-surface-2))] transition-colors text-amber-600"
            >
                <RefreshCw className="h-3 w-3" />
                Reset Layout
            </button>
            <button className="inline-flex items-center gap-2 px-3 py-1.5 rounded-lg bg-[hsl(var(--color-accent))] text-white text-xs font-semibold hover:opacity-90 transition-opacity">
                <Share2 className="h-3 w-3" />
                Export
            </button>
        </div>
      </div>

      <div className="flex-1 min-h-0 border border-[hsl(var(--border))] rounded-2xl overflow-hidden bg-[hsl(var(--card))] relative">
        {isLoading ? (
          <div className="absolute inset-0 flex items-center justify-center bg-[hsl(var(--card))]/50 z-10">
            <div className="text-center">
                <Loader2 className="h-8 w-8 animate-spin text-[hsl(var(--color-accent))] mx-auto mb-4" />
                <p className="text-sm font-medium">Maping nodes and entities...</p>
            </div>
          </div>
        ) : null}

        <ReactFlow
          nodes={nodes}
          edges={edges}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onConnect={onConnect}
          onNodeClick={(_, node) => setSelectedNode(node)}
          onNodeDragStop={onNodeDragStop}
          onPaneClick={() => setSelectedNode(null)}
          fitView
          nodeTypes={nodeTypes}
          minZoom={0.2}
          maxZoom={2}
        >
          <Background color="#ccc" variant={"dots" as any} />
          <Controls />
          <MiniMap 
            nodeColor={(n: any) => {
                if (n.type === 'skill') return '#10b981'
                if (n.type === 'job') return '#f59e0b'
                if (n.type === 'company') return '#ef4444'
                return '#4f46e5'
            }}
            maskColor="rgb(241, 245, 249, 0.2)"
          />
        </ReactFlow>

        {/* Side Inspector Panel */}
        {selectedNode && (
          <div className="absolute top-4 right-4 bottom-4 w-80 bg-white/95 dark:bg-slate-900/95 backdrop-blur-md border border-slate-200 dark:border-slate-800 rounded-2xl shadow-2xl p-6 overflow-y-auto animate-in slide-in-from-right duration-300 z-50">
            <div className="flex justify-between items-start mb-6">
              <div>
                <Badge variant={
                    selectedNode.type === 'skill' ? 'secondary' : 
                    selectedNode.type === 'job' ? 'default' : 'outline'
                } className="mb-2">
                  {selectedNode.type?.toUpperCase()}
                </Badge>
                <h2 className="text-xl font-bold leading-tight">{selectedNode.data.label}</h2>
              </div>
              <button 
                onClick={() => setSelectedNode(null)}
                className="p-1 hover:bg-slate-100 dark:hover:bg-slate-800 rounded-full transition-colors"
              >
                <X size={20} />
              </button>
            </div>

            <div className="space-y-6">
                {selectedNode.type === 'job' && (
                    <div className="space-y-4">
                        <div className="p-4 rounded-xl bg-amber-50 dark:bg-amber-900/20 border border-amber-100 dark:border-amber-900/30">
                            <p className="text-xs font-bold text-amber-600 uppercase mb-1">Status</p>
                            <p className="text-sm font-semibold capitalize">{selectedNode.data.status || 'Applied'}</p>
                        </div>
                        <Button className="w-full gap-2">
                            View Application <ExternalLink size={14} />
                        </Button>
                    </div>
                )}

                {selectedNode.type === 'skill' && (
                    <div className="space-y-4">
                        <div className="p-4 rounded-xl bg-emerald-50 dark:bg-emerald-900/20 border border-emerald-100 dark:border-emerald-900/30">
                            <p className="text-xs font-bold text-emerald-600 uppercase mb-1">Impact</p>
                            <p className="text-sm font-medium">This skill is linked to multiple job opportunities in your pipeline.</p>
                        </div>
                    </div>
                )}

                <div className="border-t border-slate-100 dark:border-slate-800 pt-6">
                    <p className="text-xs font-bold text-muted-foreground uppercase mb-4 tracking-wider">Related Connections</p>
                    <div className="space-y-3">
                        {edges
                          .filter(e => e.source === selectedNode.id || e.target === selectedNode.id)
                          .map(e => {
                              const otherId = e.source === selectedNode.id ? e.target : e.source
                              const otherNode = nodes.find(n => n.id === otherId)
                              return (
                                <div key={e.id} className="flex items-center gap-3 p-2 rounded-lg hover:bg-slate-50 dark:hover:bg-slate-800 transition-colors cursor-pointer group">
                                    <div className={`w-2 h-2 rounded-full ${e.style?.stroke === '#10b981' ? 'bg-emerald-500' : 'bg-slate-400'}`} />
                                    <div className="flex-1 min-w-0">
                                        <p className="text-sm font-medium truncate group-hover:text-indigo-600 transition-colors">
                                            {otherNode?.data?.label || otherId}
                                        </p>
                                        <p className="text-[10px] text-muted-foreground uppercase">{e.label}</p>
                                    </div>
                                </div>
                              )
                          })}
                    </div>
                </div>
            </div>
          </div>
        )}
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <Card className="bg-emerald-50/50 border-emerald-200">
              <CardHeader className="py-3 px-4">
                  <CardTitle className="text-sm font-bold flex items-center gap-2 text-emerald-700">
                      <div className="h-2 w-2 rounded-full bg-emerald-500" />
                      Skills
                  </CardTitle>
              </CardHeader>
              <CardContent className="py-2 px-4">
                  <p className="text-xs text-emerald-600">Represented by green nodes. These are extracted from your resume and matched against jobs.</p>
              </CardContent>
          </Card>
          <Card className="bg-amber-50/50 border-amber-200">
              <CardHeader className="py-3 px-4">
                  <CardTitle className="text-sm font-bold flex items-center gap-2 text-amber-700">
                      <div className="h-2 w-2 rounded-full bg-amber-500" />
                      Opportunities
                  </CardTitle>
              </CardHeader>
              <CardContent className="py-2 px-4">
                  <p className="text-xs text-amber-600">Represented by amber nodes. These show specific job applications and their skill connections.</p>
              </CardContent>
          </Card>
          <Card className="bg-indigo-50/50 border-indigo-200">
              <CardHeader className="py-3 px-4">
                  <CardTitle className="text-sm font-bold flex items-center gap-2 text-indigo-700">
                      <div className="h-2 w-2 rounded-full bg-indigo-500" />
                      Connections
                  </CardTitle>
              </CardHeader>
              <CardContent className="py-2 px-4">
                  <p className="text-xs text-indigo-600">Lines show 'Applied', 'Matched', or 'Missing' relationships between entities.</p>
              </CardContent>
          </Card>
      </div>
    </div>
  )
}
