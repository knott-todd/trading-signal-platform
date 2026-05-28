const BASE = import.meta.env.VITE_GATEWAY_URL ?? ''

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...init?.headers },
    ...init,
  })
  if (!r.ok) {
    const text = await r.text().catch(() => r.statusText)
    throw new Error(`${r.status} ${text}`)
  }
  if (r.status === 204) return undefined as T
  return r.json()
}

// System
export const api = {
  health:   () => req<any>('/api/health'),
  modules:  () => req<any>('/api/modules'),

  // Ingestion — health
  ingestionHealth: () => req<any>('/api/ingestion/health'),

  // Watchlist
  tickers:       () => req<any>('/api/ingestion/tickers'),
  addTicker:     (body: any) => req<any>('/api/ingestion/tickers', { method: 'POST', body: JSON.stringify(body) }),
  updateTicker:  (symbol: string, body: any) => req<any>(`/api/ingestion/tickers/${symbol}`, { method: 'PATCH', body: JSON.stringify(body) }),
  deleteTicker:  (symbol: string) => req<void>(`/api/ingestion/tickers/${symbol}`, { method: 'DELETE' }),

  // Coverage
  coverage: (params?: { start?: string; end?: string }) => {
    const q = new URLSearchParams(params as any).toString()
    return req<any>(`/api/ingestion/coverage${q ? `?${q}` : ''}`)
  },

  // Bars
  bars: (symbol: string, params: { resolution: string; start?: string; end?: string }) => {
    const q = new URLSearchParams(params as any).toString()
    return req<any>(`/api/ingestion/bars/${symbol}?${q}`)
  },

  // Backfill
  backfill: (body: any) => req<any>('/api/ingestion/backfill', { method: 'POST', body: JSON.stringify(body) }),

  // Stream
  streamStatus: () => req<any>('/api/ingestion/stream/status'),
}
