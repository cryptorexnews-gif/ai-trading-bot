import { useCallback, useEffect, useState } from 'react'
import { getApiBase, getHeaders } from './useApi'

export default function useBotControl() {
  const apiBase = getApiBase()
  const [controller, setController] = useState({ is_running: false, pid: null, started_at: null })
  const [loading, setLoading] = useState(true)
  const [actionLoading, setActionLoading] = useState(false)

  const loadStatus = useCallback(async () => {
    const res = await fetch(`${apiBase}/bot-control/status`, {
      headers: getHeaders(),
      credentials: 'same-origin',
    })
    if (!res.ok) {
      throw new Error(`HTTP ${res.status}`)
    }
    const json = await res.json()
    setController(json.controller || { is_running: false, pid: null, started_at: null })
    setLoading(false)
  }, [apiBase])

  useEffect(() => {
    loadStatus().catch(() => {
      setLoading(false)
    })

    const timer = setInterval(() => {
      loadStatus().catch(() => {})
    }, 2000)

    return () => clearInterval(timer)
  }, [loadStatus])

  const startBot = useCallback(async () => {
    setActionLoading(true)
    const res = await fetch(`${apiBase}/bot-control/start`, {
      method: 'POST',
      headers: getHeaders(),
      credentials: 'same-origin',
    })
    setActionLoading(false)

    if (!res.ok) {
      const json = await res.json().catch(() => ({}))
      throw new Error(json.error || `HTTP ${res.status}`)
    }

    const json = await res.json()
    setController(json.controller || controller)
    return json
  }, [apiBase, controller])

  const stopBot = useCallback(async () => {
    setActionLoading(true)
    const res = await fetch(`${apiBase}/bot-control/stop`, {
      method: 'POST',
      headers: getHeaders(),
      credentials: 'same-origin',
    })
    setActionLoading(false)

    if (!res.ok) {
      const json = await res.json().catch(() => ({}))
      throw new Error(json.error || `HTTP ${res.status}`)
    }

    const json = await res.json()
    setController(json.controller || controller)
    return json
  }, [apiBase, controller])

  return {
    controller,
    loading,
    actionLoading,
    startBot,
    stopBot,
    refresh: loadStatus,
  }
}