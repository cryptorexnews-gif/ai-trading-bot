import { useState, useEffect, useCallback, useRef } from 'react'

const API_BASE = '/api'

function getApiKey() {
  if (typeof window !== 'undefined' && window.__DASHBOARD_API_KEY__) {
    return window.__DASHBOARD_API_KEY__
  }
  const meta = document.querySelector('meta[name="dashboard-api-key"]')
  if (meta) {
    return meta.getAttribute('content')
  }
  return ''
}

export function getHeaders() {
  const headers = {}
  const apiKey = getApiKey()
  if (apiKey) {
    headers['X-API-Key'] = apiKey
  }
  return headers
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
          throw new Error('Unauthorized — check DASHBOARD_API_KEY')
        }
        throw new Error(`HTTP ${response.status}`)
      }
      const json = await response.json()

      // Guard against race conditions: only apply if this is still the latest fetch
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