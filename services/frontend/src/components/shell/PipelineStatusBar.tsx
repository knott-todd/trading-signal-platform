import { useQuery } from '@tanstack/react-query'
import { useAppStore } from '@/store/app'
import { MODULE_REGISTRY } from '@/lib/moduleRegistry'
import { api } from '@/lib/api'
import { clsx } from 'clsx'

const STATUS_COLOR: Record<string, string> = {
  healthy:    'status-dot-green',
  degraded:   'status-dot-amber',
  unhealthy:  'status-dot-red',
  unreachable:'status-dot-red',
  unknown:    'status-dot-grey',
}

const STATUS_LABEL: Record<string, string> = {
  healthy:    'OK',
  degraded:   'DEG',
  unhealthy:  'ERR',
  unreachable:'ERR',
  unknown:    '—',
}

export function PipelineStatusBar() {
  const { activeModule, setActiveView, sseConnected, moduleHealth } = useAppStore()

  const { data: modulesData } = useQuery({
    queryKey: ['modules'],
    queryFn: api.modules,
    refetchInterval: 15_000,
  })

  const serverModuleHealth: Record<string, string> = {}
  if (modulesData?.modules) {
    for (const m of modulesData.modules) {
      serverModuleHealth[m.id] = m.health
    }
  }

  return (
    <header className="flex items-stretch h-10 bg-panel border-b border-border flex-shrink-0 select-none">
      {/* Wordmark */}
      <div className="flex items-center px-4 border-r border-border">
        <span className="text-[11px] font-mono font-semibold tracking-[0.2em] text-bright uppercase">
          PERCEPTION
        </span>
      </div>

      {/* Pipeline nodes */}
      <div className="flex items-center flex-1 px-4 gap-0">
        {MODULE_REGISTRY.map((mod, i) => {
          const status = moduleHealth[mod.id] ?? serverModuleHealth[mod.id] ?? 'unknown'
          const isActive = activeModule === mod.id
          const dotClass = STATUS_COLOR[status] ?? 'status-dot-grey'

          return (
            <div key={mod.id} className="flex items-center">
              {/* Connector line */}
              {i > 0 && (
                <div className="relative w-8 mx-1 flex items-center">
                  <svg width="32" height="10" className="overflow-visible">
                    <line
                      x1="0" y1="5" x2="32" y2="5"
                      stroke="#1e2530" strokeWidth="1"
                    />
                    {status === 'healthy' && (
                      <line
                        x1="0" y1="5" x2="32" y2="5"
                        stroke="#00d084" strokeWidth="1"
                        strokeOpacity="0.5"
                        className="flow-line"
                        strokeDasharray="4 4"
                      />
                    )}
                  </svg>
                </div>
              )}

              {/* Node */}
              <button
                onClick={() => setActiveView(mod.id, mod.views[0]?.id ?? '')}
                className={clsx(
                  'flex items-center gap-2 px-3 h-10 text-[11px] font-mono tracking-wider uppercase',
                  'border-b-2 transition-colors duration-100',
                  isActive
                    ? 'border-blue text-bright'
                    : 'border-transparent text-dim hover:text-text hover:border-border',
                )}
              >
                <span className={clsx('status-dot', dotClass)} />
                <span>{mod.label}</span>
                <span className={clsx(
                  'text-[9px] tracking-widest',
                  status === 'healthy' ? 'text-green' :
                  status === 'degraded' ? 'text-amber' :
                  status === 'unknown' ? 'text-dim' : 'text-red'
                )}>
                  {STATUS_LABEL[status] ?? '—'}
                </span>
              </button>
            </div>
          )
        })}

        {/* Future modules render automatically here */}
      </div>

      {/* SSE indicator */}
      <div className="flex items-center px-4 border-l border-border gap-2">
        <span className={clsx(
          'status-dot',
          sseConnected ? 'status-dot-green status-dot-pulse' : 'status-dot-red'
        )} />
        <span className="text-[10px] font-mono text-dim uppercase tracking-wider">
          {sseConnected ? 'LIVE' : 'OFFLINE'}
        </span>
      </div>
    </header>
  )
}
