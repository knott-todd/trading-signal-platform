import { clsx } from 'clsx'
import {
  Activity, LayoutGrid, CandlestickChart, Radio,
  ChevronDown, ChevronRight, type LucideIcon,
} from 'lucide-react'
import { useAppStore } from '@/store/app'
import { MODULE_REGISTRY } from '@/lib/moduleRegistry'

const ICONS: Record<string, LucideIcon> = {
  Activity,
  LayoutGrid,
  CandlestickChart,
  Radio,
}

const STATUS_DOT: Record<string, string> = {
  healthy:    'status-dot-green',
  degraded:   'status-dot-amber',
  unhealthy:  'status-dot-red',
  unreachable:'status-dot-red',
  unknown:    'status-dot-grey',
}

export function LeftNav() {
  const { activeModule, activeView, setActiveView, moduleHealth } = useAppStore()

  return (
    <nav className="w-48 bg-panel border-r border-border flex-shrink-0 flex flex-col overflow-y-auto">
      <div className="pt-3 pb-2">
        {MODULE_REGISTRY.map((mod) => {
          const isExpanded = activeModule === mod.id
          const status = moduleHealth[mod.id] ?? 'unknown'

          return (
            <div key={mod.id}>
              {/* Module header */}
              <button
                onClick={() => setActiveView(mod.id, mod.views[0]?.id ?? '')}
                className={clsx(
                  'w-full flex items-center gap-2 px-3 py-2 text-[11px] font-mono uppercase tracking-wider',
                  'transition-colors duration-100',
                  isExpanded ? 'text-bright' : 'text-dim hover:text-text',
                )}
              >
                <span className={clsx('status-dot flex-shrink-0', STATUS_DOT[status])} />
                <span className="flex-1 text-left">{mod.label}</span>
                {isExpanded
                  ? <ChevronDown size={10} className="text-dim flex-shrink-0" />
                  : <ChevronRight size={10} className="text-dim flex-shrink-0" />
                }
              </button>

              {/* Views */}
              {isExpanded && (
                <div className="ml-3 border-l border-border pb-1">
                  {mod.views.map((view) => {
                    const Icon = ICONS[view.icon]
                    const isActive = activeView === view.id

                    return (
                      <button
                        key={view.id}
                        onClick={() => setActiveView(mod.id, view.id)}
                        className={clsx(
                          'w-full flex items-center gap-2 pl-3 pr-2 py-1.5',
                          'text-[11px] font-mono transition-colors duration-100',
                          'border-l-2 -ml-px',
                          isActive
                            ? 'border-blue text-bright bg-blue/5'
                            : 'border-transparent text-dim hover:text-text hover:border-border',
                        )}
                      >
                        {Icon && <Icon size={11} className="flex-shrink-0" />}
                        <span>{view.label}</span>
                        {view.verificationView && (
                          <span className="ml-auto text-[8px] text-green/60 tracking-wider">✓</span>
                        )}
                      </button>
                    )
                  })}
                </div>
              )}
            </div>
          )
        })}
      </div>
    </nav>
  )
}
