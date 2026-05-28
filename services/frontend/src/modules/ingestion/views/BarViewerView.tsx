import { useState, useEffect, useRef } from 'react'
import { useQuery } from '@tanstack/react-query'
import { clsx } from 'clsx'
import { Loader2, AlertTriangle } from 'lucide-react'
import { api } from '@/lib/api'
import { format, subDays } from 'date-fns'

// TradingView Lightweight Charts — dynamically imported to avoid SSR issues
let createChart: any = null
let CandlestickSeriesType: any = null
let HistogramSeriesType: any = null

const RESOLUTIONS = ['1m', '5m', '15m', '1h', '1d']

// ── Candlestick Chart ─────────────────────────────────────────────

function CandlestickChart({ bars }: { bars: any[] }) {
  const containerRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<any>(null)
  const candleSeriesRef = useRef<any>(null)
  const volumeSeriesRef = useRef<any>(null)

  useEffect(() => {
    async function initChart() {
      if (!containerRef.current) return

      const lc = await import('lightweight-charts')
      createChart = lc.createChart

      if (chartRef.current) {
        chartRef.current.remove()
      }

      const chart = lc.createChart(containerRef.current, {
        width:  containerRef.current.clientWidth,
        height: containerRef.current.clientHeight,
        layout: {
          background: { color: '#0f1114' },
          textColor:  '#4a5568',
        },
        grid: {
          vertLines: { color: '#1e2530' },
          horzLines: { color: '#1e2530' },
        },
        crosshair: {
          vertLine: { color: '#2a3340', labelBackgroundColor: '#161a1f' },
          horzLine: { color: '#2a3340', labelBackgroundColor: '#161a1f' },
        },
        rightPriceScale: {
          borderColor: '#1e2530',
        },
        timeScale: {
          borderColor: '#1e2530',
          timeVisible: true,
          secondsVisible: false,
        },
      })

      chartRef.current = chart

      const candleSeries = chart.addCandlestickSeries({
        upColor:          '#00d084',
        downColor:        '#e63946',
        borderUpColor:    '#00d084',
        borderDownColor:  '#e63946',
        wickUpColor:      '#00d084',
        wickDownColor:    '#e63946',
      })
      candleSeriesRef.current = candleSeries

      const volumeSeries = chart.addHistogramSeries({
        priceFormat: { type: 'volume' },
        priceScaleId: 'volume',
      })
      chart.priceScale('volume').applyOptions({
        scaleMargins: { top: 0.85, bottom: 0 },
      })
      volumeSeriesRef.current = volumeSeries

      const ro = new ResizeObserver(() => {
        if (containerRef.current && chartRef.current) {
          chartRef.current.applyOptions({
            width: containerRef.current.clientWidth,
            height: containerRef.current.clientHeight,
          })
        }
      })
      ro.observe(containerRef.current)

      return () => { ro.disconnect() }
    }
    initChart()
    return () => { chartRef.current?.remove() }
  }, [])

  useEffect(() => {
    if (!candleSeriesRef.current || !volumeSeriesRef.current) return
    if (!bars || bars.length === 0) return

    const candles = bars.map((b) => ({
      time: Math.floor(new Date(b.ts).getTime() / 1000) as any,
      open:  Number(b.open),
      high:  Number(b.high),
      low:   Number(b.low),
      close: Number(b.close),
    }))

    const volumes = bars.map((b) => ({
      time:  Math.floor(new Date(b.ts).getTime() / 1000) as any,
      value: Number(b.volume),
      color: Number(b.close) >= Number(b.open) ? '#00d08440' : '#e6394640',
    }))

    candleSeriesRef.current.setData(candles)
    volumeSeriesRef.current.setData(volumes)
    chartRef.current?.timeScale().fitContent()
  }, [bars])

  return <div ref={containerRef} className="w-full h-full" />
}

// ── Data Table ────────────────────────────────────────────────────

function BarTable({ bars }: { bars: any[] }) {
  return (
    <div className="overflow-auto h-full">
      <table className="w-full text-[11px] font-mono">
        <thead className="sticky top-0 bg-panel">
          <tr>
            {['Timestamp', 'Open', 'High', 'Low', 'Close', 'Volume', 'Source', 'Flag'].map((h) => (
              <th key={h} className="px-3 py-2 text-left label-xs font-normal border-b border-border">{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {bars.slice().reverse().map((b, i) => (
            <tr
              key={i}
              className={clsx(
                'table-row-hover border-t border-border/30',
                b.flagged && 'bg-amber/5'
              )}
            >
              <td className="px-3 py-1.5 text-dim">{format(new Date(b.ts), 'yyyy-MM-dd HH:mm:ss')}</td>
              <td className="px-3 py-1.5 text-text">{Number(b.open).toFixed(4)}</td>
              <td className="px-3 py-1.5 text-text">{Number(b.high).toFixed(4)}</td>
              <td className="px-3 py-1.5 text-text">{Number(b.low).toFixed(4)}</td>
              <td className={clsx('px-3 py-1.5', Number(b.close) >= Number(b.open) ? 'text-green' : 'text-red')}>
                {Number(b.close).toFixed(4)}
              </td>
              <td className="px-3 py-1.5 text-dim">{Number(b.volume).toLocaleString()}</td>
              <td className="px-3 py-1.5 text-dim">{b.source}</td>
              <td className="px-3 py-1.5">
                {b.flagged && <span className="tag tag-amber">FLAGGED</span>}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

// ── Main View ─────────────────────────────────────────────────────

export default function BarViewerView() {
  const [symbol, setSymbol] = useState('')
  const [symbolInput, setSymbolInput] = useState('')
  const [resolution, setResolution] = useState('1d')
  const [start, setStart] = useState(format(subDays(new Date(), 90), 'yyyy-MM-dd'))
  const [end, setEnd] = useState(format(new Date(), 'yyyy-MM-dd'))

  const { data: tickersData } = useQuery({
    queryKey: ['tickers'],
    queryFn: api.tickers,
  })
  const tickers: any[] = tickersData?.tickers ?? []

  const { data: barsData, isLoading, error } = useQuery({
    queryKey: ['bars', symbol, resolution, start, end],
    queryFn: () => api.bars(symbol, { resolution, start, end }),
    enabled: !!symbol,
  })

  const bars: any[] = Array.isArray(barsData) ? barsData : []
  const flaggedCount = bars.filter((b) => b.flagged).length

  function handleSymbolCommit() {
    setSymbol(symbolInput.toUpperCase().trim())
  }

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* Controls */}
      <div className="flex items-center gap-3 px-5 py-3 border-b border-border flex-shrink-0 flex-wrap">
        <div className="flex items-center gap-2">
          <label className="label-xs">Ticker</label>
          <div className="flex">
            <input
              className="input w-24 rounded-r-none"
              placeholder="AAPL"
              value={symbolInput}
              onChange={(e) => setSymbolInput(e.target.value.toUpperCase())}
              onKeyDown={(e) => e.key === 'Enter' && handleSymbolCommit()}
            />
            <button className="btn rounded-l-none border-l-0" onClick={handleSymbolCommit}>Go</button>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <label className="label-xs">Resolution</label>
          <div className="flex">
            {RESOLUTIONS.map((r) => (
              <button
                key={r}
                onClick={() => setResolution(r)}
                className={clsx(
                  'px-2.5 py-1.5 text-[11px] font-mono border border-border -ml-px first:ml-0',
                  'first:rounded-l-sm last:rounded-r-sm transition-colors duration-100',
                  resolution === r
                    ? 'bg-blue/10 border-blue/50 text-blue z-10'
                    : 'bg-surface text-dim hover:text-text hover:bg-muted'
                )}
              >
                {r}
              </button>
            ))}
          </div>
        </div>

        <div className="flex items-center gap-2">
          <label className="label-xs">From</label>
          <input type="date" className="input" value={start} onChange={(e) => setStart(e.target.value)} />
          <label className="label-xs">To</label>
          <input type="date" className="input" value={end} onChange={(e) => setEnd(e.target.value)} />
        </div>

        <div className="ml-auto flex items-center gap-3 text-[11px] font-mono text-dim">
          {bars.length > 0 && (
            <>
              <span>{bars.length.toLocaleString()} bars</span>
              {flaggedCount > 0 && (
                <span className="flex items-center gap-1 text-amber">
                  <AlertTriangle size={11} /> {flaggedCount} flagged
                </span>
              )}
            </>
          )}
        </div>
      </div>

      {/* Chart */}
      <div className="flex-[0_0_55%] border-b border-border relative">
        {!symbol ? (
          <div className="flex items-center justify-center h-full text-dim text-[11px] font-mono">
            Enter a ticker symbol to load chart
          </div>
        ) : isLoading ? (
          <div className="flex items-center justify-center h-full">
            <Loader2 size={16} className="animate-spin text-dim" />
            <span className="ml-2 text-dim text-xs font-mono">Loading bars...</span>
          </div>
        ) : error ? (
          <div className="flex items-center justify-center h-full text-red text-xs font-mono">
            Error: {String(error)}
          </div>
        ) : bars.length === 0 ? (
          <div className="flex items-center justify-center h-full text-dim text-[11px] font-mono">
            No bars found for {symbol} {resolution} in selected range
          </div>
        ) : (
          <CandlestickChart bars={bars} />
        )}
      </div>

      {/* Data table */}
      <div className="flex-1 overflow-hidden">
        {bars.length > 0 ? (
          <BarTable bars={bars} />
        ) : (
          <div className="flex items-center justify-center h-full text-dim text-[11px] font-mono">
            {symbol ? 'No data to display' : 'Select a ticker and resolution above'}
          </div>
        )}
      </div>
    </div>
  )
}
