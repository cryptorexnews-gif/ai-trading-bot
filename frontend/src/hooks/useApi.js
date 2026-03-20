import { useState, useEffect, useCallback, useRef } from 'react'

const API_BASE = '/api'

function getHeaders() {
  // Removed API key retrieval to prevent client-side exposure
  // Server will handle authentication based on origin (localhost)
  return {}
}

export function useApi(endpoint, intervalMs = 5000) {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [lastUpdated, setLastUpdated] = useState(null)
  const mountedRef = useRef(true)
  const errorLoggedRef = useRef(false)
  const fetchIdRef = useRef(0)

  const fetchData = useCallback(async () => {
    const currentFetchId = ++fetchIdRef.current

    try {
      const response = await fetch(`${API_BASE}${endpoint}`, { headers: getHeaders() })
      
      if (!response.ok) {
        if (response.status === 401) {
          throw new Error('401 Unauthorized — Server authentication required')
        }
        throw new Error(`HTTP ${response.status}: ${response.statusText}`)
      }
      
      const json = await response.json()

      if (mountedRef.current && currentFetchId === fetchIdRef.current) {
        setData(json)
        setError(null)
        setLastUpdated(new Date())
        errorLoggedRef.current = false
      }
    } catch (err) {
      if (mountedRef.current && currentFetchId === fetchIdRef.current) {
        setError(err.message)
        if (!errorLoggedRef.current) {
          console.warn(`[useApi] ${endpoint}: ${err.message}`)
          errorLoggedRef.current = true
        }
      }
    } finally {
      if (mountedRef.current && currentFetchId === fetchIdRef.current) {
        setLoading(false)
      }
    }
  }, [endpoint])

  useEffect(() => {
    mountedRef.current = true
    fetchIdRef.current = 0
    setLoading(true)
    setError(null)

    fetchData()
    const interval = setInterval(fetchData, intervalMs)
    return () => {
      mountedRef.current = false
      clearInterval(interval)
    }
  }, [fetchData, intervalMs])

  return { data, loading, error, lastUpdated, refetch: fetchData }
}