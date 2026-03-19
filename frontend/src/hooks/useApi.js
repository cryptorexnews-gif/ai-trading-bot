import { useState, useEffect, useCallback, useRef } from 'react'

const API_BASE = '/api'

export function useApi(endpoint, intervalMs = 5000) {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [lastUpdated, setLastUpdated] = useState(null)
  const mountedRef = useRef(true)

  const fetchData = useCallback(async () => {
    try {
      const response = await fetch(`${API_BASE}${endpoint}`)
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`)
      }
      const json = await response.json()
      if (mountedRef.current) {
        setData(json)
        setError(null)
        setLastUpdated(new Date())
      }
    } catch (err) {
      if (mountedRef.current) {
        setError(err.message)
      }
    } finally {
      if (mountedRef.current) {
        setLoading(false)
      }
    }
  }, [endpoint])

  useEffect(() => {
    mountedRef.current = true
    fetchData()
    const interval = setInterval(fetchData, intervalMs)
    return () => {
      mountedRef.current = false
      clearInterval(interval)
    }
  }, [fetchData, intervalMs])

  return { data, loading, error, lastUpdated, refetch: fetchData }
}