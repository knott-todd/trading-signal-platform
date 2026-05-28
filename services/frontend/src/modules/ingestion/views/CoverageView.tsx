import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { clsx } from 'clsx'
import { Plus, Trash2, Loader2, RefreshCw, AlertTriangle } from 'lucide-react'
import { api } from '@/lib/api'
import { format, subDays, eachDayOfInterval, isWeekend } from 'date-fns'

// ── Coverage Heatmap ──────────────────────────────────────────────

const RESOLUTIONS = ['1m', '5m', '15m', '1h', '1d']

function CellTooltip({ symbol, date, resolutions }: { symbol: string; date: string; resolutions: any[] }) {
  return (
    <div className="absolute z-50 bottom-full left-1/2 -translate-x-1/2 mb-1 min-w-max
                    bg-ink border border-border rounded-sm p-2 text-[10px] font-mono pointer-events-none shadow-xl">
      <div className="text-bright font-semibold mb-1">{symbol} · {date}</div>
      {resolutions.map((r) => (
        <div key={r.resolution} className="flex justify-between gap-4">
          <span className="text-dim">{r.resolution}</span>
          <span className="text-text">{r.bar_count?.toLocaleString() ?? 0} bars</span>
        </div>
      ))}
    </div>
  )
}

function HeatmapCell({ symbol, dateStr, coverage }: {
  symbol: string
  dateStr: string
  coverage: Record<string, any>
}) {
  const [hovered, setHovered] = useState(false)
  const date = new Date(dateStr)
  const isWknd = isWeekend(date)

  const key = `${symbol}::${dateStr}`
  const dayData = coverage[key]

  let bg = 'bg-muted/20'       // no data
  let tooltip: any[] = []

  if (isWknd) {
    bg = 'bg-border/30'
  } else if (dayData) {
    const filled = dayData.filter((r: any) => (r.bar_count ?? 0) > 0)
    if (filled.length === RESOLUTIONS.length) {
      bg = 'bg-green/30'
    } else if (filled.length > 0) {
      bg = 'bg-amber/30'
    } else {
      bg = 'bg-red/20'
    }
    tooltip = dayData
  }

  return (
    <div
      className="relative"
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
    >
      <div className={clsx('w-5 h-5 rounded-[2px] cursor-default', bg)} />
      {hovered && !isWknd && tooltip.length > 0 && (
        <CellTooltip symbol={symbol} date={dateStr} resolutions={tooltip} />
      )}
    </div>
  )
}

// ── Watchlist Table ───────────────────────────────────────────────

function TickerRow({ ticker, onDelete, onToggle }: {
  ticker: any
  onDelete: (sym: string) => void
  onToggle: (sym: string, field: string, val: boolean) => void
}) {
  return (
    <tr className="table-row-hover border-t border-border/50">
      <td className="px-3 py-2">
        <span className="text-[12px] font-mono font-semibold text-bright">{ticker.symbol}</span>
      </td>
      <td className="px-3 py-2 text-[11px] font-mono text-dim">{ticker.name ?? '—'}</td>
      <td className="px-3 py-2">
        <button
          onClick={() => onToggle(ticker.symbol, 'active', !ticker.active)}
          className={clsx(
            'w-8 h-4 rounded-full transition-colors duration-200 relative flex-shrink-0',
            ticker.active ? 'bg-green/40' : 'bg-muted'
          )}
        >
          <span className={clsx(
            'absolute top-0.5 w-3 h-3 rounded-full transition-transform duration-200',
            ticker.active ? 'translate-x-4 bg-green' : 'translate-x-0.5 bg-dim'
          )} />
        </button>
      </td>
      <td className="px-3 py-2">
        <button
          onClick={() => onToggle(ticker.symbol, 'stream_live', !ticker.stream_live)}
          className={clsx(
            'w-8 h-4 rounded-full transition-colors duration-200 relative flex-shrink-0',
            ticker.stream_live ? 'bg-blue/40' : 'bg-muted'
          )}
        >
          <span className={clsx(
            'absolute top-0.5 w-3 h-3 rounded-full transition-transform duration-200',
            ticker.stream_live ? 'translate-x-4 bg-blue' : 'translate-x-0.5 bg-dim'
          )} />
        </button>
      </td>
      <td className="px-3 py-2 text-[11px] font-mono text-dim">
        {ticker.added_at ? format(new Date(ticker.added_at), 'yyyy-MM-dd') : '—'}
      </td>
      <td className="px-3 py-2">
        <button
          onClick={() => onDelete(ticker.symbol)}
          className="p-1 hover:text-red text-dim transition-colors rounded-sm"
          title="Remove ticker"
        >
          <Trash2 size={12} />
        </button>
      </td>
    </tr>
  )
}

// ── Main View ─────────────────────────────────────────────────────

export default function CoverageView() {
  const qc = useQueryClient()
  const [newSymbol, setNewSymbol] = useState('')
  const [adding, setAdding] = useState(false)

  const today = new Date()
  const days30 = eachDayOfInterval({ start: subDays(today, 29), end: today })
  const dateStrs = days30.map((d) => format(d, 'yyyy-MM-dd'))

  const { data: tickersData, isLoading: tickersLoading } = useQuery({
    queryKey: ['tickers'],
    queryFn: api.tickers,
    refetchInterval: 30_000,
  })

  const { data: coverageData, isLoading: coverageLoading } = useQuery({
    queryKey: ['coverage'],
    queryFn: () => api.coverage({ start: dateStrs[0], end: dateStrs[dateStrs.length - 1] }),
    refetchInterval: 60_000,
  })

  const addMut = useMutation({
    mutationFn: (symbol: string) => api.addTicker({ symbol }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['tickers'] })
      qc.invalidateQueries({ queryKey: ['coverage'] })
      setNewSymbol('')
      setAdding(false)
    },
  })

  const deleteMut = useMutation({
    mutationFn: (symbol: string) => api.deleteTicker(symbol),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['tickers'] }),
  })

  const toggleMut = useMutation({
    mutationFn: ({ symbol, body }: { symbol: string; body: any }) => api.updateTicker(symbol, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['tickers'] }),
  })

  const tickers: any[] = tickersData?.tickers ?? []

  // Build coverage lookup: "SYMBOL::YYYY-MM-DD" → [{resolution, bar_count}]
  const coverageLookup: Record<string, any[]> = {}
  if (coverageData?.coverage) {
    for (const entry of coverageData.coverage) {
      for (const r of (entry.resolutions ?? [])) {
        const oldest = r.oldest ? format(new Date(r.oldest), 'yyyy-MM-dd') : null
        const newest = r.newest ? format(new Date(r.newest), 'yyyy-MM-dd') : null
        if (!oldest || !newest) continue
        for (const d of dateStrs) {
          if (d >= oldest && d <= newest) {
            const k = `${entry.symbol}::${d}`
            if (!coverageLookup[k]) coverageLookup[k] = []
            coverageLookup[k].push({ resolution: r.resolution, bar_count: r.bar_count })
          }
        }
      }
    }
  }

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* Watchlist table — top half */}
      <div className="flex flex-col flex-[0_0_45%] overflow-hidden border-b border-border">
        <div className="flex items-center justify-between px-5 py-3 border-b border-border flex-shrink-0">
          <div>
            <h2 className="text-sm font-mono font-semibold text-bright uppercase tracking-widest">Watchlist</h2>
            <p className="text-dim text-[11px] font-mono">{tickers.length} tickers</p>
          </div>
          <div className="flex items-center gap-2">
            {adding ? (
              <>
                <input
                  className="input w-24"
                  placeholder="SYMBOL"
                  value={newSymbol}
                  onChange={(e) => setNewSymbol(e.target.value.toUpperCase())}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' && newSymbol) addMut.mutate(newSymbol)
                    if (e.key === 'Escape') setAdding(false)
                  }}
                  autoFocus
                />
                <button className="btn-primary" onClick={() => newSymbol && addMut.mutate(newSymbol)}>
                  {addMut.isPending ? <Loader2 size={11} className="animate-spin" /> : 'Add'}
                </button>
                <button className="btn" onClick={() => setAdding(false)}>Cancel</button>
              </>
            ) : (
              <button className="btn-primary" onClick={() => setAdding(true)}>
                <Plus size={11} /> Add ticker
              </button>
            )}
          </div>
        </div>

        <div className="overflow-y-auto flex-1">
          {tickersLoading ? (
            <div className="flex items-center justify-center h-20">
              <Loader2 size={16} className="animate-spin text-dim" />
            </div>
          ) : tickers.length === 0 ? (
            <div className="flex items-center justify-center h-20 text-dim text-[11px] font-mono">
              No tickers in watchlist. Add one above.
            </div>
          ) : (
            <table className="w-full">
              <thead>
                <tr>
                  {['Symbol', 'Name', 'Active', 'Live Stream', 'Added', ''].map((h) => (
                    <th key={h} className="px-3 py-2 text-left label-xs font-normal">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {tickers.map((t: any) => (
                  <TickerRow
                    key={t.symbol}
                    ticker={t}
                    onDelete={(sym) => deleteMut.mutate(sym)}
                    onToggle={(sym, field, val) => toggleMut.mutate({ symbol: sym, body: { [field]: val } })}
                  />
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>

      {/* Coverage heatmap — bottom half */}
      <div className="flex flex-col flex-1 overflow-hidden">
        <div className="flex items-center justify-between px-5 py-3 border-b border-border flex-shrink-0">
          <div>
            <h2 className="text-sm font-mono font-semibold text-bright uppercase tracking-widest">Coverage Heatmap</h2>
            <p className="text-dim text-[11px] font-mono">Last 30 days · all resolutions</p>
          </div>
          <div className="flex items-center gap-3 text-[10px] font-mono text-dim">
            <span className="flex items-center gap-1.5"><span className="w-3 h-3 rounded-[2px] bg-green/30 inline-block" /> Full</span>
            <span className="flex items-center gap-1.5"><span className="w-3 h-3 rounded-[2px] bg-amber/30 inline-block" /> Partial</span>
            <span className="flex items-center gap-1.5"><span className="w-3 h-3 rounded-[2px] bg-red/20 inline-block" /> None</span>
            <span className="flex items-center gap-1.5"><span className="w-3 h-3 rounded-[2px] bg-border/30 inline-block" /> Weekend</span>
          </div>
        </div>

        <div className="overflow-auto flex-1 p-4">
          {coverageLoading ? (
            <div className="flex items-center justify-center h-20">
              <Loader2 size={16} className="animate-spin text-dim" />
            </div>
          ) : tickers.length === 0 ? (
            <div className="flex items-center justify-center h-20 text-dim text-[11px] font-mono">
              Add tickers to see coverage
            </div>
          ) : (
            <div className="inline-flex flex-col gap-1 min-w-max">
              {/* Date header */}
              <div className="flex items-center gap-1 pl-20">
                {dateStrs.map((d, i) => (
                  <div key={d} className="w-5 flex justify-center">
                    {i === 0 || d.slice(8) === '01' || i % 7 === 0 ? (
                      <span className="text-[9px] font-mono text-dim -rotate-45 origin-left">
                        {format(new Date(d), 'M/d')}
                      </span>
                    ) : null}
                  </div>
                ))}
              </div>

              {/* Ticker rows */}
              {tickers.map((t: any) => (
                <div key={t.symbol} className="flex items-center gap-1">
                  <div className="w-20 flex-shrink-0 text-right pr-2">
                    <span className="text-[11px] font-mono text-text">{t.symbol}</span>
                  </div>
                  {dateStrs.map((d) => (
                    <HeatmapCell
                      key={d}
                      symbol={t.symbol}
                      dateStr={d}
                      coverage={coverageLookup}
                    />
                  ))}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
