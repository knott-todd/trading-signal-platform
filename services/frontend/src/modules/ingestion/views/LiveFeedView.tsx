import { useState, useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { clsx } from 'clsx'
import { Pause, Play, Radio, Loader2, WifiOff } from 'lucide-react'
import { LineChart, Line, ResponsiveContainer } from 'recharts'
import { useAppStore, LiveBar } from '@/store/app'
import { api } from '@/lib/api'
import { format, formatDistanceToNow } from 'date-fns'

// ── Sparkline ─────────────────────────────────────────────────────

function Sparkline({ closes }: { closes: number[] }) {
  const data = closes.map((c) => ({ v: c }))
  const first = closes[0] ?? 0
  const last = closes[closes.length - 1] ?? 0
  const color = last >= first ? '#00d084' : '#e63946'

  return (
    <ResponsiveContainer width="100%" height={32}>
      <LineChart data={data} margin={{ top: 2, right: 2, left: 2, bottom: 2 }}>
        <Line
          type="monotone"
          dataKey="v"
          stroke={color}
          strokeWidth={1.5}
          dot={false}
          isAnimationActive={false}
        />
      </LineChart>
    </ResponsiveContainer>
  )
}

// ── Ticker Sparkline Card ─────────────────────────────────────────

function SparklineCard({ symbol, bars }: { symbol: string; bars: LiveBar[] }) {
  const closes = bars.slice(0, 20).reverse().map((b) => b.close)
  const latest = bars[0]
  const prev = bars[1]
  const change = latest && prev
    ? ((latest.close - prev.close) / prev.close) * 100
    : null

  return (
    <div className="card flex flex-col gap-1 min-w-[140px]">
      <div className="flex items-center justify-between">
        <span className="text-[12px] font-mono font-semibold text-bright">{symbol}</span>
        {change !== null && (
          <span className={clsx('text-[10px] font-mono', change >= 0 ? 'text-green' : 'text-red')}>
            {change >= 0 ? '+' : ''}{change.toFixed(2)}%
          </span>
        )}
      </div>
      {latest && (
        <span className="text-[11px] font-mono text-text">{latest.close.toFixed(4)}</span>
      )}
      {closes.length > 1 && <Sparkline closes={closes} />}
      {latest && (
        <span className="text-[9px] font-mono text-dim">
          {format(new Date(latest.ts), 'HH:mm:ss')} · {latest.resolution}
        </span>
      )}
    </div>
  )
}

// ── Live Bar Row ──────────────────────────────────────────────────

function BarRow({ bar }: { bar: LiveBar }) {
  const isUp = bar.close >= bar.open
  return (
    <tr className="bar-slide-in border-t border-border/30 table-row-hover">
      <td className="px-3 py-1.5 text-dim text-[11px] font-mono">
        {format(new Date(bar.ts), 'HH:mm:ss')}
      </td>
      <td className="px-3 py-1.5">
        <span className="text-[12px] font-mono font-semibold text-bright">{bar.symbol}</span>
      </td>
      <td className="px-3 py-1.5">
        <span className="tag tag-grey">{bar.resolution}</span>
      </td>
      <td className="px-3 py-1.5 text-text text-[11px] font-mono">{bar.open.toFixed(4)}</td>
      <td className="px-3 py-1.5 text-text text-[11px] font-mono">{bar.high.toFixed(4)}</td>
      <td className="px-3 py-1.5 text-text text-[11px] font-mono">{bar.low.toFixed(4)}</td>
      <td className={clsx('px-3 py-1.5 text-[11px] font-mono font-semibold', isUp ? 'text-green' : 'text-red')}>
        {bar.close.toFixed(4)}
      </td>
      <td className="px-3 py-1.5 text-dim text-[11px] font-mono">{bar.volume.toLocaleString()}</td>
      <td className="px-3 py-1.5 text-dim text-[11px] font-mono">{bar.source}</td>
    </tr>
  )
}

// ── Main View ─────────────────────────────────────────────────────

export default function LiveFeedView() {
  const {
    liveBars, feedPaused, setFeedPaused,
    streamState, streamBarsSession, lastBarTs,
  } = useAppStore()

  const [symbolFilter, setSymbolFilter] = useState('')
  const [resolutionFilter, setResolutionFilter] = useState('')

  const { data: streamStatus } = useQuery({
    queryKey: ['stream-status'],
    queryFn: api.streamStatus,
    refetchInterval: 10_000,
  })

  // Per-symbol bars for sparklines
  const bySymbol = useMemo(() => {
    const map: Record<string, LiveBar[]> = {}
    for (const bar of liveBars) {
      if (!map[bar.symbol]) map[bar.symbol] = []
      map[bar.symbol].push(bar)
    }
    return map
  }, [liveBars])

  // Filtered feed
  const filtered = useMemo(() => {
    return liveBars.filter((b) => {
      if (symbolFilter && !b.symbol.includes(symbolFilter.toUpperCase())) return false
      if (resolutionFilter && b.resolution !== resolutionFilter) return false
      return true
    })
  }, [liveBars, symbolFilter, resolutionFilter])

  const isLive = streamState === 'connected'
  const isDegraded = streamState === 'fallback' || streamState === 'reconnecting'

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* Stream status header */}
      <div className={clsx(
        'flex items-center gap-4 px-5 py-3 border-b flex-shrink-0',
        isLive ? 'border-green/20 bg-green/5' :
        isDegraded ? 'border-amber/20 bg-amber/5' :
        'border-border bg-surface'
      )}>
        <div className="flex items-center gap-2">
          {isLive ? (
            <Radio size={14} className="text-green status-dot-pulse" style={{ animation: 'statusPulse 1.5s ease-in-out infinite' }} />
          ) : isDegraded ? (
            <Radio size={14} className="text-amber" />
          ) : (
            <WifiOff size={14} className="text-dim" />
          )}
          <span className={clsx(
            'text-[12px] font-mono font-semibold uppercase tracking-widest',
            isLive ? 'text-green' : isDegraded ? 'text-amber' : 'text-dim'
          )}>
            {isLive ? 'Live' : isDegraded ? streamState.toUpperCase() : 'Disconnected'}
          </span>
        </div>

        <div className="flex items-center gap-5 text-[11px] font-mono text-dim">
          <span>
            <span className="label-xs mr-1.5">Tickers</span>
            <span className="text-text">{streamStatus?.symbol_count ?? Object.keys(bySymbol).length}</span>
          </span>
          <span>
            <span className="label-xs mr-1.5">Bars / session</span>
            <span className="text-text">{streamBarsSession.toLocaleString()}</span>
          </span>
          {lastBarTs && (
            <span>
              <span className="label-xs mr-1.5">Last bar</span>
              <span className="text-text">
                {formatDistanceToNow(new Date(lastBarTs), { addSuffix: true })}
              </span>
            </span>
          )}
        </div>

        <div className="ml-auto flex items-center gap-2">
          <input
            className="input w-24"
            placeholder="Symbol…"
            value={symbolFilter}
            onChange={(e) => setSymbolFilter(e.target.value)}
          />
          <select
            className="input"
            value={resolutionFilter}
            onChange={(e) => setResolutionFilter(e.target.value)}
          >
            <option value="">All</option>
            {['1m', '5m', '15m', '1h', '1d'].map((r) => (
              <option key={r} value={r}>{r}</option>
            ))}
          </select>
          <button
            className={clsx('btn', feedPaused && 'border-amber/40 text-amber')}
            onClick={() => setFeedPaused(!feedPaused)}
            title={feedPaused ? 'Resume feed' : 'Pause feed'}
          >
            {feedPaused ? <Play size={11} /> : <Pause size={11} />}
            {feedPaused ? 'Resume' : 'Pause'}
          </button>
        </div>
      </div>

      {/* Sparklines row */}
      {Object.keys(bySymbol).length > 0 && (
        <div className="flex gap-2 px-4 py-3 border-b border-border overflow-x-auto flex-shrink-0">
          {Object.entries(bySymbol).map(([sym, bars]) => (
            <SparklineCard key={sym} symbol={sym} bars={bars} />
          ))}
        </div>
      )}

      {/* Live bar table */}
      <div className="flex-1 overflow-y-auto">
        {!isLive && liveBars.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full gap-3 text-dim">
            <WifiOff size={24} className="text-dim/50" />
            <span className="text-[11px] font-mono">Stream disconnected — no live bars</span>
            <span className="text-[10px] font-mono text-dim/60">
              Enable stream_live on tickers in the Watchlist view
            </span>
          </div>
        ) : (
          <table className="w-full">
            <thead className="sticky top-0 bg-panel z-10">
              <tr>
                {['Time', 'Symbol', 'Res', 'Open', 'High', 'Low', 'Close', 'Volume', 'Source'].map((h) => (
                  <th key={h} className="px-3 py-2 text-left label-xs font-normal border-b border-border">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {filtered.length === 0 ? (
                <tr>
                  <td colSpan={9} className="px-3 py-8 text-center text-dim text-[11px] font-mono">
                    {liveBars.length > 0 ? 'No bars match current filter' : 'Waiting for live bars...'}
                  </td>
                </tr>
              ) : (
                filtered.map((bar, i) => <BarRow key={`${bar.symbol}-${bar.ts}-${i}`} bar={bar} />)
              )}
            </tbody>
          </table>
        )}
      </div>

      {feedPaused && (
        <div className="flex items-center justify-center gap-2 py-2 bg-amber/5 border-t border-amber/20 flex-shrink-0">
          <Pause size={11} className="text-amber" />
          <span className="text-[11px] font-mono text-amber">Feed paused — SSE connection maintained</span>
        </div>
      )}
    </div>
  )
}
