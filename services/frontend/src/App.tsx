import { Suspense, lazy } from 'react'
import { clsx } from 'clsx'
import { Loader2 } from 'lucide-react'
import { PipelineStatusBar } from '@/components/shell/PipelineStatusBar'
import { LeftNav } from '@/components/shell/LeftNav'
import { EventTicker } from '@/components/shell/EventTicker'
import { MODULE_REGISTRY } from '@/lib/moduleRegistry'
import { useAppStore } from '@/store/app'
import { useSSE } from '@/hooks/useSSE'

function ViewLoader() {
  return (
    <div className="flex items-center justify-center h-full">
      <Loader2 size={18} className="animate-spin text-dim" />
    </div>
  )
}

function ActiveView() {
  const { activeModule, activeView } = useAppStore()
  const mod = MODULE_REGISTRY.find((m) => m.id === activeModule)
  const view = mod?.views.find((v) => v.id === activeView)
  if (!view) {
    return (
      <div className="flex items-center justify-center h-full text-dim text-xs font-mono">
        View not found: {activeModule}/{activeView}
      </div>
    )
  }
  const Component = view.component
  return (
    <Suspense fallback={<ViewLoader />}>
      <Component />
    </Suspense>
  )
}

export default function App() {
  // Establish SSE connection for the lifetime of the app
  useSSE()

  return (
    <div className="flex flex-col h-full bg-ink">
      {/* Top: pipeline status bar */}
      <PipelineStatusBar />

      {/* Middle: nav + content */}
      <div className="flex flex-1 overflow-hidden">
        <LeftNav />
        <main className="flex-1 overflow-hidden bg-ink">
          <ActiveView />
        </main>
      </div>

      {/* Bottom: event ticker */}
      <EventTicker />
    </div>
  )
}
