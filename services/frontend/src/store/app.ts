import { create } from 'zustand'

export interface SSEEvent {
  type: string
  module: string
  ts: string
  payload: Record<string, unknown>
}

export interface LiveBar {
  symbol: string
  resolution: string
  ts: string
  open: number
  high: number
  low: number
  close: number
  volume: number
  source: string
}

export interface ModuleHealth {
  id: string
  status: 'healthy' | 'degraded' | 'unhealthy' | 'unreachable' | 'unknown'
}

interface AppStore {
  // Navigation
  activeModule: string
  activeView: string
  setActiveView: (module: string, view: string) => void

  // SSE connection
  sseConnected: boolean
  setSseConnected: (v: boolean) => void

  // Event ticker
  events: SSEEvent[]
  tickerPaused: boolean
  pushEvent: (e: SSEEvent) => void
  setTickerPaused: (v: boolean) => void

  // Live bars (for View 4)
  liveBars: LiveBar[]
  feedPaused: boolean
  pushLiveBar: (bar: LiveBar) => void
  setFeedPaused: (v: boolean) => void

  // Module health map (updated by SSE)
  moduleHealth: Record<string, string>
  setModuleHealth: (id: string, status: string) => void

  // Stream status (for View 4 header)
  streamState: string
  streamSymbolCount: number
  streamBarsSession: number
  lastBarTs: string | null
  setStreamState: (state: string) => void
  incrementBarCount: () => void
  setLastBarTs: (ts: string) => void
}

export const useAppStore = create<AppStore>((set) => ({
  activeModule: 'ingestion',
  activeView: 'health',
  setActiveView: (module, view) => set({ activeModule: module, activeView: view }),

  sseConnected: false,
  setSseConnected: (v) => set({ sseConnected: v }),

  events: [],
  tickerPaused: false,
  pushEvent: (e) =>
    set((s) => ({
      events: s.tickerPaused ? s.events : [e, ...s.events].slice(0, 200),
    })),
  setTickerPaused: (v) => set({ tickerPaused: v }),

  liveBars: [],
  feedPaused: false,
  pushLiveBar: (bar) =>
    set((s) => ({
      liveBars: s.feedPaused ? s.liveBars : [bar, ...s.liveBars].slice(0, 500),
    })),
  setFeedPaused: (v) => set({ feedPaused: v }),

  moduleHealth: {},
  setModuleHealth: (id, status) =>
    set((s) => ({ moduleHealth: { ...s.moduleHealth, [id]: status } })),

  streamState: 'disconnected',
  streamSymbolCount: 0,
  streamBarsSession: 0,
  lastBarTs: null,
  setStreamState: (state) => set({ streamState: state }),
  incrementBarCount: () =>
    set((s) => ({ streamBarsSession: s.streamBarsSession + 1 })),
  setLastBarTs: (ts) => set({ lastBarTs: ts }),
}))
