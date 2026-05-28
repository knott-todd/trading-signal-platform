import { clsx } from 'clsx'
import { Pause, Play, X } from 'lucide-react'
import { useAppStore, SSEEvent } from '@/store/app'
import { formatDistanceToNow } from 'date-fns'

const EVENT_COLOR: Record<string, string> = {
  'bar.live':                'text-green',
  'ingestion.health_change': 'text-blue',
  'stream.connected':        'text-green',
  'stream.disconnected':     'text-red',
  'stream.reconnected':      'text-green',
  'backfill.complete':       'text-amber',
  'gap.detected':            'text-red',
}

function eventSummary(e: SSEEvent): string {
  const p = e.payload as any
  switch (e.type) {
    case 'bar.live':
      return `${p.symbol} ${p.resolution} — O:${p.open?.toFixed(2)} H:${p.high?.toFixed(2)} L:${p.low?.toFixed(2)} C:${p.close?.toFixed(2)} V:${p.volume?.toLocaleString()}`
    case 'ingestion.health_change':
      return `${p.subsystem} ${p.previous_state ?? '?'} → ${p.new_state}`
    case 'stream.connected':
      return `stream connected · ${p.ticker_count} tickers`
    case 'stream.disconnected':
      return `stream disconnected · ${p.reason ?? 'unknown reason'}`
    case 'stream.reconnected':
      return `stream reconnected · downtime ${p.downtime_seconds}s`
    case 'backfill.complete':
      return `${p.symbol} ${p.resolution} · ${p.rows_written} rows written`
    case 'gap.detected':
      return `gap: ${p.symbol} ${p.resolution} ${p.gap_start} → ${p.gap_end}`
    default:
      return JSON.stringify(e.payload).slice(0, 80)
  }
}

export function EventTicker() {
  const { events, tickerPaused, setTickerPaused, sseConnected } = useAppStore()

  return (
    <footer className="h-7 bg-panel border-t border-border flex items-center flex-shrink-0 select-none">
      {/* Label */}
      <div className="flex items-center gap-2 px-3 border-r border-border h-full flex-shrink-0">
        <span className={clsx(
          'status-dot flex-shrink-0',
          sseConnected ? 'status-dot-green status-dot-pulse' : 'status-dot-grey'
        )} />
        <span className="label-xs">EVENTS</span>
      </div>

      {/* Scrolling events */}
      <div className="flex-1 overflow-hidden flex items-center px-3 gap-4 h-full">
        {events.length === 0 ? (
          <span className="text-dim text-[11px] font-mono">
            awaiting events...
          </span>
        ) : (
          <div className="flex items-center gap-4 overflow-x-auto" style={{ scrollbarWidth: 'none' }}>
            {events.slice(0, 20).map((e, i) => (
              <div key={i} className="flex items-center gap-2 flex-shrink-0">
                <span className="text-dim text-[10px] font-mono">
                  {new Date(e.ts).toLocaleTimeString('en-US', { hour12: false })}
                </span>
                <span className={clsx('text-[10px] font-mono uppercase tracking-wider', EVENT_COLOR[e.type] ?? 'text-dim')}>
                  {e.type}
                </span>
                <span className={clsx(
                  'text-[11px] font-mono text-text',
                  e.type === 'ingestion.health_change' && (e.payload as any).new_state === 'unhealthy' ? 'text-red' :
                  e.type === 'gap.detected' ? 'text-amber' : ''
                )}>
                  {eventSummary(e)}
                </span>
                {i < events.slice(0, 20).length - 1 && (
                  <span className="text-border">·</span>
                )}
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Controls */}
      <div className="flex items-center gap-1 px-2 border-l border-border h-full flex-shrink-0">
        <button
          onClick={() => setTickerPaused(!tickerPaused)}
          className="flex items-center justify-center w-5 h-5 hover:bg-muted rounded-sm transition-colors"
          title={tickerPaused ? 'Resume ticker' : 'Pause ticker'}
        >
          {tickerPaused
            ? <Play size={10} className="text-dim" />
            : <Pause size={10} className="text-dim" />
          }
        </button>
      </div>
    </footer>
  )
}
