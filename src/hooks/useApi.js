import { useState, useEffect, useCallback, useRef } from 'react'

const API_BASE = '/api'

function getApiKey() {
  // 1. Window injected (vite inject)
  if (typeof window !== 'undefined' && window.__DASHBOARD_API_KEY__) {
    return window.__DASHBOARD_API_KEY__
  }

  // 2. Vite .env (recommended)
  if (import.meta.env.VITE_DASHBOARD_API_KEY) {
    return import.meta.env.VITE_DASHBOARD_API_KEY
  }

  // 3. Meta tag fallback
  const meta = document.querySelector('meta[name="dashboard-api-key"]')
  if (meta) {
    const content = meta.getAttribute('content') || ''
    if (content && content !== '%VITE_DASHBOARD_API_KEY%') {
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

// Specialized hook for OpenRouter API calls
export function useOpenRouter() {
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  const chatCompletion = useCallback(async (messages, model = 'anthropic/claude-opus-4', options = {}) => {
    setLoading(true)
    setError(null)

    try {
      const headers = getHeaders()
      const response = await fetch('/api/openrouter/chat', {
        method: 'POST',
        headers: {
          ...headers,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          model,
          messages,
          max_tokens: options.max_tokens || 8192,
          temperature: options.temperature || 0.15,
          top_p: options.top_p || 1.0,
          ...options
        })
      })

      if (!response.ok) {
        throw new Error(`OpenRouter API error: ${response.status}`)
      }

      const data = await response.json()
      return data
    } catch (err) {
      setError(err.message)
      throw err
    } finally {
      setLoading(false)
    }
  }, [])

  const getModels = useCallback(async () => {
    try {
      const headers = getHeaders()
      const response = await fetch('/api/openrouter/models', { headers })
      
      if (!response.ok) {
        throw new Error(`Failed to fetch models: ${response.status}`)
      }

      return await response.json()
    } catch (err) {
      setError(err.message)
      throw err
    }
  }, [])

  return { chatCompletion, getModels, loading, error }
}

// Specialized hook for Hyperliquid API calls
export function useHyperliquid() {
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  const getInfo = useCallback(async (payload) => {
    setLoading(true)
    setError(null)

    try {
      const headers = getHeaders()
      const response = await fetch('/api/hyperliquid/info', {
        method: 'POST',
        headers: {
          ...headers,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(payload)
      })

      if (!response.ok) {
        throw new Error(`Hyperliquid API error: ${response.status}`)
      }

      const data = await response.json()
      return data
    } catch (err) {
      setError(err.message)
      throw err
    } finally {
      setLoading(false)
    }
  }, [])

  const getMidPrices = useCallback(async () => {
    try {
      const headers = getHeaders()
      const response = await fetch('/api/hyperliquid/mids', { headers })
      
      if (!response.ok) {
        throw new Error(`Failed to fetch mid prices: ${response.status}`)
      }

      return await response.json()
    } catch (err) {
      setError(err.message)
      throw err
    }
  }, [])

  const getCandles = useCallback(async (coin, interval = '15m', limit = 100) => {
    setLoading(true)
    setError(null)

    try {
      const headers = getHeaders()
      const response = await fetch(
        `/api/hyperliquid/candles?coin=${coin}&interval=${interval}&limit=${limit}`,
        { headers }
      )

      if (!response.ok) {
        throw new Error(`Failed to fetch candles: ${response.status}`)
      }

      const data = await response.json()
      return data
    } catch (err) {
      setError(err.message)
      throw err
    } finally {
      setLoading(false)
    }
  }, [])

  return { getInfo, getMidPrices, getCandles, loading, error }
}