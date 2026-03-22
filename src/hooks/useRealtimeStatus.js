import { useEffect, useRef, useState } from 'react'

function buildWsUrl(path) {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${protocol}//${window.location.host}${path}`
}

export default function useRealtimeStatus() {
  const [data, setData] = useState(null)
  const [connected, setConnected] = useState(false)
  const [lastUpdated, setLastUpdated] = useState(null)
  const reconnectTimerRef = useRef(null)
  const wsRef = useRef(null)

  useEffect(() => {
    let active = true

    const connect = () => {
      const ws = new WebSocket(buildWsUrl('/ws/status'))
      wsRef.current = ws

      ws.onopen = () => {
        if (!active) return
        setConnected(true)
      }

      ws.onmessage = (event) => {
        if (!active) return
        try {
          const json = JSON.parse(event.data)
          setData(json)
          setLastUpdated(new Date())
        } catch {
          // Ignore malformed frames and keep stream alive
        }
      }

      ws.onclose = () => {
        if (!active) return
        setConnected(false)
        reconnectTimerRef.current = window.setTimeout(connect, 1500)
      }

      ws.onerror = () => {
        if (!active) return
        setConnected(false)
      }
    }

    connect()

    return () => {
      active = false
      if (reconnectTimerRef.current) {
        window.clearTimeout(reconnectTimerRef.current)
      }
      if (wsRef.current) {
        wsRef.current.close()
      }
    }
  }, [])

  return { data, connected, lastUpdated }
}