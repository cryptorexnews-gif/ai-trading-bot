import { useState, useEffect, useCallback, useRef } from 'react'

const API_BASE = '/api'

// Read API key from meta tag or window config (set by deployment)
function getApiKey() {
  // Check for global config (can be set in index.html or by deployment)
  if (typeof window !== 'undefined' && window.__DASHBOARD_API_KEY__) {
    return window.__DASHBOARD_API_KEY__
  }
  // Check meta tag
  const meta = document.querySelector('meta[name="dashboard-api-key"]')
  if (meta) {
    return meta.getAttribute('content')
  }
  return ''
}

export function useApi(endpoint, intervalMs = 5000) {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [lastUpdated, setLastUpdated] = useState(null)
  const mountedRef = useRef(true)

  const fetchData = useCallback(async () => {
    try {
      const headers = {}
      const apiKey = getApiKey()
      if (apiKey) {
        headers['X-API-Key'] = apiKey
      }

      const response = await fetch(`${API_BASE}${endpoint}`, { headers })
      if (!response.ok) {
        if (response.status === 401) {
          throw new Error('Unauthorized — check DASHBOARD_API_KEY')
        }
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