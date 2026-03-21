import { useCallback, useEffect, useState } from 'react'
import { getApiBase, getHeaders } from './useApi'

export default function useRuntimeConfig() {
  const apiBase = getApiBase()
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [availablePairs, setAvailablePairs] = useState([])
  const [strategyMode, setStrategyMode] = useState('trend')
  const [selectedPairs, setSelectedPairs] = useState([])

  const load = useCallback(async () => {
    setLoading(true)
    const res = await fetch(`${apiBase}/runtime-config`, {
      headers: getHeaders(),
      credentials: 'same-origin',
    })
    if (!res.ok) {
      setLoading(false)
      throw new Error(`HTTP ${res.status}`)
    }

    const json = await res.json()
    const runtime = json.runtime_config || {}
    setAvailablePairs(json.available_pairs || [])
    setStrategyMode(runtime.strategy_mode || 'trend')
    setSelectedPairs(runtime.trading_pairs || [])
    setLoading(false)
  }, [apiBase])

  useEffect(() => {
    load().catch(() => {
      setLoading(false)
    })
  }, [load])

  const toggleCoin = useCallback((coin) => {
    setSelectedPairs((prev) => {
      if (prev.includes(coin)) return prev.filter((c) => c !== coin)
      return [...prev, coin]
    })
  }, [])

  const save = useCallback(async () => {
    if (!selectedPairs.length) {
      throw new Error('Seleziona almeno una moneta')
    }

    setSaving(true)
    const res = await fetch(`${apiBase}/runtime-config`, {
      method: 'POST',
      headers: { ...getHeaders(), 'Content-Type': 'application/json' },
      credentials: 'same-origin',
      body: JSON.stringify({
        strategy_mode: strategyMode,
        trading_pairs: selectedPairs,
      }),
    })

    setSaving(false)

    if (!res.ok) {
      const json = await res.json().catch(() => ({}))
      throw new Error(json.error || `HTTP ${res.status}`)
    }

    const json = await res.json()
    const runtime = json.runtime_config || {}
    setStrategyMode(runtime.strategy_mode || strategyMode)
    setSelectedPairs(runtime.trading_pairs || selectedPairs)
    return json
  }, [apiBase, selectedPairs, strategyMode])

  return {
    loading,
    saving,
    availablePairs,
    strategyMode,
    setStrategyMode,
    selectedPairs,
    toggleCoin,
    save,
  }
}