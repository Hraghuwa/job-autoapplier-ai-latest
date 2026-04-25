import { useDraggable } from '@dnd-kit/core'
import { Card, CardContent } from '@/components/ui/card'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { GripVertical } from 'lucide-react'
import Link from 'next/link'
import { Badge } from '@/components/ui/badge'

export function DraggableCard({ job, updateStatus, statusVariants, kanbanCols }: any) {
  const { attributes, listeners, setNodeRef, transform, isDragging } = useDraggable({
    id: job.id,
    data: job
  })

  const style = transform ? {
    transform: `translate3d(${transform.x}px, ${transform.y}px, 0)`,
    zIndex: isDragging ? 50 : 1,
    opacity: isDragging ? 0.8 : 1,
  } : undefined

  return (
    <div ref={setNodeRef} style={style} className="relative outline-none">
      <Card 
        className={`group border bg-[hsl(var(--card))] overflow-hidden transition-all duration-200 ${
          isDragging ? 'shadow-xl shadow-[hsl(var(--color-accent))]/10 border-[hsl(var(--color-accent))]/50 rotate-2' : 'border-[hsl(var(--border))] hover:border-[hsl(var(--border-strong))] hover:shadow-md'
        }`}
      >
        <div 
          className="absolute top-0 left-0 w-[3px] h-full transition-colors" 
          style={{
            backgroundColor: statusVariants[job.status] === 'destructive' ? 'hsl(var(--color-destructive))' : 
                            statusVariants[job.status] === 'default' ? 'hsl(var(--color-accent))' : 'hsl(var(--muted-foreground))'
          }} 
        />
        <CardContent className="p-4 pl-5 relative flex flex-col gap-3">
          <div className="flex justify-between items-start gap-2">
            <Link href={`/jobs/${job.id}`} className="flex-1">
              <p className="font-display font-semibold text-sm leading-tight text-[hsl(var(--foreground))] line-clamp-2 group-hover:text-[hsl(var(--color-accent))] transition-colors">
                {job.job_title}
              </p>
              <p className="text-xs text-[hsl(var(--muted-foreground))] mt-1 truncate">{job.company}</p>
            </Link>
            <div 
              {...attributes} 
              {...listeners}
              className="p-1 -mr-1.5 -mt-1 text-[hsl(var(--muted-foreground))]/50 hover:text-[hsl(var(--color-accent))] cursor-grab active:cursor-grabbing hover:bg-[hsl(var(--color-surface-2))] rounded transition-all"
            >
              <GripVertical className="h-4 w-4" />
            </div>
          </div>
          
          <div className="flex items-center justify-between mt-1">
             {job.match_score != null ? (
               <div className="flex items-center gap-1.5 bg-[hsl(var(--color-surface-2))] px-2 py-0.5 rounded border border-[hsl(var(--border))]">
                 <span className={`h-1.5 w-1.5 rounded-full ${job.match_score > 70 ? 'bg-[hsl(var(--color-success))]' : 'bg-[hsl(var(--muted-foreground))]'}`} />
                 <span className="text-[10px] font-bold tracking-wide">
                   {job.match_score}% MATCH
                 </span>
               </div>
             ) : <div />}
             
             <Select
              value={job.status}
              onValueChange={(s) => s && updateStatus.mutate({ id: job.id, status: s })}
            >
              <SelectTrigger className="h-6 w-auto px-2 text-[10px] font-semibold tracking-wide border-transparent bg-transparent shadow-none hover:bg-[hsl(var(--color-surface-2))] focus:ring-0 transition-colors uppercase">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {kanbanCols.map((s: string) => (
                  <SelectItem key={s} value={s} className="capitalize text-xs font-medium">
                    {s}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
