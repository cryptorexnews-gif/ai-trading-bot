import { useCallback, useEffect, useState } from 'react'
import { getApiBase, getHeaders } from './useApi'

const DEFAULT_PAIRS = [
  'BTC', 'ETH', 'SOL', 'BNB', 'XRP', 'ADA', 'DOGE', 'AVAX', 'LINK', 'SUI',
  'ARB', 'OP', 'NEAR', 'WIF', 'PEPE', 'INJ', 'TIA', 'SEI', 'RENDER', 'FET',
]

function normalizeCoinList(list) {
  if (!Array.isArray(list)) return []
  const normalized = []
  const seen = new Set()

  for (const item of list) {
    const coin = String(item || '').trim().toUpperCase()
    if (!coin) continue
    if (seen.has(coin)) continue
    seen.add(coin)
    normalized.push(coin)
  }

  return normalized
}

export default function useRuntimeConfig() {
  const apiBase = getApiBase()
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [loadError, setLoadError] = useState('')
  const [availablePairs, setAvailablePairs] = useState(DEFAULT_PAIRS)
  const [strategyMode, setStrategyMode] = useState('trend')
  const [selectedPairs, setSelectedPairs] = useState(['BTC', 'ETH'])

  const load = useCallback(async () => {
    setLoading(true)
    setLoadError('')

    try {
      const res = await fetch(`${apiBase}/runtime-config`, {
        headers: getHeaders(),
        credentials: 'same-origin',
      })

      if (!res.ok) {
        throw new Error(`HTTP ${res.status}`)
      }

      const json = await res.json()
      const runtime = json.runtime_config || {}

      const available = normalizeCoinList(json.available_pairs)
      const selected = normalizeCoinList(runtime.trading_pairs)
      const mode = String(runtime.strategy_mode || 'trend').toLowerCase()

      setAvailablePairs(available.length ? available : DEFAULT_PAIRS)
      setSelectedPairs(selected.length ? selected : ['BTC', 'ETH'])
      setStrategyMode(mode === 'scalping' ? 'scalping' : 'trend')
      setLoading(false)
      return
    } catch (runtimeErr) {
      try {
        const configRes = await fetch(`${apiBase}/config`, {
          headers: getHeaders(),
          credentials: 'same-origin',
        })

        if (!configRes.ok) {
          throw new Error(`HTTP ${configRes.status}`)
        }

        const configJson = await configRes.json()
        const configPairs = normalizeCoinList(configJson.trading_pairs)

        setAvailablePairs(configPairs.length ? configPairs : DEFAULT_PAIRS)
        setSelectedPairs(configPairs.slice(0, 5).length ? configPairs.slice(0, 5) : ['BTC', 'ETH'])
        setStrategyMode('trend')
        setLoadError('Runtime config non disponibile: fallback attivo su config base.')
        setLoading(false)
        return
      } catch {
        setAvailablePairs(DEFAULT_PAIRS)
        setSelectedPairs(['BTC', 'ETH'])
        setStrategyMode('trend')
        setLoadError(`Caricamento runtime fallito: ${runtimeErr.message}`)
        setLoading(false)
      }
    }
  }, [apiBase])

  useEffect(() => {
    load().catch(() => {
      setLoading(false)
      setLoadError('Errore imprevisto durante il caricamento.')
    })
  }, [load])

  const toggleCoin = useCallback((coin) => {
    const normalized = String(coin || '').trim().toUpperCase()
    if (!normalized) return

    setSelectedPairs((prev) => {
      if (prev.includes(normalized)) return prev.filter((c) => c !== normalized)
      return [...prev, normalized]
    })
  }, [])

  const save = useCallback(async () => {
    const normalizedSelected = normalizeCoinList(selectedPairs)
    if (!normalizedSelected.length) {
      throw new Error('Seleziona almeno una moneta')
    }

    setSaving(true)
    const res = await fetch(`${apiBase}/runtime-config`, {
      method: 'POST',
      headers: { ...getHeaders(), 'Content-Type': 'application/json' },
      credentials: 'same-origin',
      body: JSON.stringify({
        strategy_mode: strategyMode,
        trading_pairs: normalizedSelected,
      }),
    })

    setSaving(false)

    if (!res.ok) {
      const json = await res.json().catch(() => ({}))
      throw new Error(json.error || `HTTP ${res.status}`)
    }

    const json = await res.json()
    const runtime = json.runtime_config || {}
    const runtimeSelected = normalizeCoinList(runtime.trading_pairs)
    const runtimeMode = String(runtime.strategy_mode || strategyMode).toLowerCase()

    setStrategyMode(runtimeMode === 'scalping' ? 'scalping' : 'trend')
    setSelectedPairs(runtimeSelected.length ? runtimeSelected : normalizedSelected)
    setLoadError('')
    return json
  }, [apiBase, selectedPairs, strategyMode])

  return {
    loading,
    saving,
    loadError,
    availablePairs,
    strategyMode,
    setStrategyMode,
    selectedPairs,
    toggleCoin,
    save,
    reload: load,
  }
}