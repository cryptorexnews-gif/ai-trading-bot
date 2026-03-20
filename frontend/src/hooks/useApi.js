import { useState, useEffect, useCallback, useRef } from 'react'

const API_BASE = '/api'

function getApiKey() {
  // 1. Window injected (vite inject)
  if (typeof window !== 'undefined' && window.__DASHBOARD_API_KEY__) {
    console.log('[useApi] Key from window:', window.__DASHBOARD_API_KEY__.substring(0, 8) + '...')
    return window.__DASHBOARD_API_KEY__
  }

  // 2. Vite .env (recommended)
  if (import.meta.env.VITE_DASHBOARD_API_KEY) {
    console.log('[useApi] Key from VITE env:', import.meta.env.VITE_DASHBOARD_API_KEY.substring(0, 8) + '...')
    return import.meta.env.VITE_DASHBOARD_API_KEY
  }

  // 3. Meta tag fallback
  const meta = document.querySelector('meta[name="dashboard-api-key"]')
  if (meta) {
    const content = meta.getAttribute('content') || ''
    if (content && content !== '%VITE_DASHBOARD_API_KEY%') {
      console.log('[useApi] Key from meta:', content.substring(0, 8) + '...')
      return content
    }
  }

  console.warn('[useApi] NO API KEY FOUND - requests will fail with 401')
  return ''
}

export function getHeaders() {
  const headers = {}
  const apiKey = getApiKey()
  if (apiKey) {
    headers['X-API-Key'] = apiKey
    console.log('[useApi] Sending X-API-Key header:', apiKey.substring(0, 8) + '...')
  } else {
    console.warn('[useApi] No API key - header not sent')
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
      const headers = getHeaders()
      const response = await fetch(`${API_BASE}${endpoint}`, { headers })
      
      if (!response.ok) {
        if (response.status === 401) {
          throw new Error('401 Unauthorized — Check DASHBOARD_API_KEY matches backend/frontend')
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
          console.error(`[useApi ${endpoint}] Error:`, err.message)
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

    // Initial fetch
    fetchData()
    
    const interval = setInterval(fetchData, intervalMs)
    return () => {
      mountedRef.current = false
      clearInterval(interval)
    }
  }, [fetchData, intervalMs])

  return { data, loading, error, lastUpdated, refetch: fetchData }
}