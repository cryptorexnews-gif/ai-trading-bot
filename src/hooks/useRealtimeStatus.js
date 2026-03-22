import { useEffect, useRef, useState } from 'react'
import { getApiBase, getHeaders } from './useApi'

function buildWsUrl(path) {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${protocol}//${window.location.host}${path}`
}

export default function useRealtimeStatus() {
  const apiBase = getApiBase()
  const [data, setData] = useState(null)
  const [connected, setConnected] = useState(false)
  const [lastUpdated, setLastUpdated] = useState(null)

  const reconnectTimerRef = useRef(null)
  const fallbackTimerRef = useRef(null)
  const wsRef = useRef(null)
  const retryDelayRef = useRef(1500)

  useEffect(() => {
    let active = true

    const fallbackFetch = async () => {
      const response = await fetch(`${apiBase}/status`, {
        credentials: 'same-origin',
        headers: getHeaders(),
      })
      if (!response.ok) {
        return
      }
      const json = await response.json()
      if (!active) {
        return
      }
      setData(json)
      setLastUpdated(new Date())
    }

    const startFallbackPolling = () => {
      if (fallbackTimerRef.current) {
        return
      }
      fallbackFetch()
      fallbackTimerRef.current = window.setInterval(fallbackFetch, 3000)
    }

    const stopFallbackPolling = () => {
      if (fallbackTimerRef.current) {
        window.clearInterval(fallbackTimerRef.current)
        fallbackTimerRef.current = null
      }
    }

    const connect = () => {
      const ws = new WebSocket(buildWsUrl('/ws/status'))
      wsRef.current = ws

      ws.onopen = () => {
        if (!active) return
        setConnected(true)
        retryDelayRef.current = 1500
        stopFallbackPolling()
      }

      ws.onmessage = (event) => {
        if (!active) return
        try {
          const json = JSON.parse(event.data)
          setData(json)
          setLastUpdated(new Date())
        } catch {
          // ignore malformed frames
        }
      }

      ws.onclose = () => {
        if (!active) return
        setConnected(false)
        startFallbackPolling()

        reconnectTimerRef.current = window.setTimeout(connect, retryDelayRef.current)
        retryDelayRef.current = Math.min(retryDelayRef.current * 2, 20000)
      }

      ws.onerror = () => {
        if (!active) return
        setConnected(false)
      }
    }

    connect()
    startFallbackPolling()

    return () => {
      active = false

      if (reconnectTimerRef.current) {
        window.clearTimeout(reconnectTimerRef.current)
      }
      if (fallbackTimerRef.current) {
        window.clearInterval(fallbackTimerRef.current)
      }
      if (wsRef.current) {
        wsRef.current.close()
      }
    }
  }, [apiBase])

  return { data, connected, lastUpdated }
}