import { useState, useEffect, useCallback, useRef } from 'react'

function normalizeBaseUrl(value) {
  const raw = (value || '/api').trim()
  if (!raw) return '/api'
  return raw.endsWith('/') ? raw.slice(0, -1) : raw
}

const API_BASE = normalizeBaseUrl(import.meta.env.VITE_API_BASE_URL)

export function getApiBase() {
  return API_BASE
}

export function getHeaders() {
  // Security: never send secrets from browser code.
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
      const response = await fetch(`${API_BASE}${endpoint}`, {
        credentials: 'same-origin',
        headers: getHeaders(),
      })

      if (!response.ok) {
        if (response.status === 401) {
          throw new Error('Unauthorized')
        }
        throw new Error(`HTTP ${response.status}`)
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