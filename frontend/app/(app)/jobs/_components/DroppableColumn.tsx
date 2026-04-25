import { useDroppable } from '@dnd-kit/core'
import { Badge } from '@/components/ui/badge'

export function DroppableColumn({ id, title, count, children }: { id: string, title: string, count: number, children: React.ReactNode }) {
  const { setNodeRef, isOver } = useDroppable({ id })

  return (
    <div className="min-w-[280px] w-[280px] flex flex-col pt-2 pb-4">
      <div className="flex items-center justify-between mb-4 px-1">
        <h3 className="font-display font-semibold capitalize text-[hsl(var(--foreground))]">{title}</h3>
        <Badge variant={isOver ? 'default' : 'secondary'} className="transition-colors font-mono">{count}</Badge>
      </div>
      <div
        ref={setNodeRef}
        className={`flex-1 rounded-2xl p-3 min-h-[200px] transition-all duration-300 border-2 ${
          isOver 
            ? 'bg-[hsl(var(--color-surface-2))]/80 border-[hsl(var(--color-accent))]/50 shadow-inner' 
            : 'bg-[hsl(var(--color-surface))] border-transparent hover:border-[hsl(var(--border))]'
        }`}
      >
        <div className="flex flex-col gap-3">
          {children}
        </div>
      </div>
    </div>
  )
}
