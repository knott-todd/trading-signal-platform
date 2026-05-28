import { useEffect, useRef } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { useAppStore, SSEEvent, LiveBar } from '@/store/app'

const BASE = import.meta.env.VITE_GATEWAY_URL ?? ''
const SSE_URL = `${BASE}/api/events`
const RECONNECT_MS = 3000

export function useSSE() {
  const qc = useQueryClient()
  const esRef = useRef<EventSource | null>(null)
  const retryRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const {
    setSseConnected,
    pushEvent,
    pushLiveBar,
    setModuleHealth,
    setStreamState,
    incrementBarCount,
    setLastBarTs,
  } = useAppStore.getState()

  useEffect(() => {
    function connect() {
      const es = new EventSource(SSE_URL)
      esRef.current = es

      es.onopen = () => {
        setSseConnected(true)
        if (retryRef.current) clearTimeout(retryRef.current)
      }

      es.onmessage = (e) => {
        let event: SSEEvent
        try {
          event = JSON.parse(e.data)
        } catch {
          return // malformed — ignore per spec
        }

        // Always push to event ticker
        pushEvent(event)

        // Route by type
        switch (event.type) {
          case 'bar.live': {
            const p = event.payload as any
            const bar: LiveBar = {
              symbol:     p.symbol,
              resolution: p.resolution,
              ts:         p.ts ?? event.ts,
              open:       p.open,
              high:       p.high,
              low:        p.low,
              close:      p.close,
              volume:     p.volume,
              source:     p.source,
            }
            pushLiveBar(bar)
            incrementBarCount()
            setLastBarTs(bar.ts)
            // Invalidate bar query if this ticker is currently viewed
            qc.invalidateQueries({ queryKey: ['bars', bar.symbol] })
            break
          }

          case 'ingestion.health_change': {
            const p = event.payload as any
            setModuleHealth('ingestion', p.new_state)
            qc.invalidateQueries({ queryKey: ['ingestion-health'] })
            break
          }

          case 'stream.connected': {
            setStreamState('connected')
            qc.invalidateQueries({ queryKey: ['stream-status'] })
            break
          }
          case 'stream.disconnected': {
            setStreamState('disconnected')
            qc.invalidateQueries({ queryKey: ['stream-status'] })
            break
          }
          case 'stream.reconnected': {
            setStreamState('connected')
            qc.invalidateQueries({ queryKey: ['stream-status'] })
            break
          }

          case 'backfill.complete': {
            qc.invalidateQueries({ queryKey: ['coverage'] })
            qc.invalidateQueries({ queryKey: ['bars'] })
            break
          }

          case 'gap.detected': {
            qc.invalidateQueries({ queryKey: ['coverage'] })
            break
          }

          default:
            // Unknown event type — log only, no error (spec requirement)
            console.debug('[SSE] Unknown event type:', event.type, event)
        }
      }

      es.onerror = () => {
        setSseConnected(false)
        es.close()
        esRef.current = null
        retryRef.current = setTimeout(connect, RECONNECT_MS)
      }
    }

    connect()

    return () => {
      esRef.current?.close()
      if (retryRef.current) clearTimeout(retryRef.current)
    }
  }, [])
}
