import { useCallback, useEffect, useMemo, useState } from 'react'
import { getApiBase, getHeaders } from './useApi'

const DEFAULT_PAIRS = [
  'BTC', 'ETH', 'SOL', 'BNB', 'XRP', 'ADA', 'DOGE', 'AVAX', 'LINK', 'SUI',
  'ARB', 'OP', 'NEAR', 'WIF', 'PEPE', 'INJ', 'TIA', 'SEI', 'RENDER', 'FET',
]

const PARAM_KEYS = [
  'cycle_sec',
  'min_cycle_sec',
  'max_cycle_sec',
  'max_trades_per_cycle',
  'hard_max_leverage',
  'min_confidence_open',
  'min_confidence_manage',
  'max_order_margin_pct',
  'trade_cooldown_sec',
  'daily_notional_limit_usd',
  'max_drawdown_pct',
  'max_single_asset_pct',
  'emergency_margin_threshold',
  'position_size_pct',
  'volume_confirmation_threshold',
  'sl_pct',
  'tp_pct',
  'break_even_activation_pct',
  'trailing_activation_pct',
  'trailing_callback',
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

function normalizeStrategyParams(raw) {
  if (!raw || typeof raw !== 'object') return {}
  const result = {}
  for (const key of PARAM_KEYS) {
    const value = raw[key]
    if (value == null || value === '') continue
    result[key] = String(value)
  }
  return result
}

export default function useRuntimeConfig() {
  const apiBase = getApiBase()
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [loadError, setLoadError] = useState('')
  const [availablePairs, setAvailablePairs] = useState(DEFAULT_PAIRS)
  const [strategyMode, setStrategyMode] = useState('trend')
  const [selectedPairs, setSelectedPairs] = useState(['BTC', 'ETH'])
  const [strategyParams, setStrategyParams] = useState({})
  const [defaultParams, setDefaultParams] = useState({})

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

      const defaults = normalizeStrategyParams(json.default_strategy_params || {})
      const runtimeParams = normalizeStrategyParams(runtime.strategy_params || {})
      const mergedParams = { ...defaults, ...runtimeParams }

      setAvailablePairs(available.length ? available : DEFAULT_PAIRS)
      setSelectedPairs(selected.length ? selected : ['BTC', 'ETH'])
      setStrategyMode(mode === 'scalping' ? 'scalping' : 'trend')
      setDefaultParams(defaults)
      setStrategyParams(mergedParams)
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
        setDefaultParams({})
        setStrategyParams({})
        setLoadError('Runtime config non disponibile: fallback attivo su config base.')
        setLoading(false)
        return
      } catch {
        setAvailablePairs(DEFAULT_PAIRS)
        setSelectedPairs(['BTC', 'ETH'])
        setStrategyMode('trend')
        setDefaultParams({})
        setStrategyParams({})
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

  const setStrategyParam = useCallback((key, value) => {
    if (!PARAM_KEYS.includes(key)) return
    setStrategyParams((prev) => ({ ...prev, [key]: value }))
  }, [])

  const resetStrategyParams = useCallback(() => {
    setStrategyParams((prev) => ({ ...defaultParams, ...prev }))
  }, [defaultParams])

  const save = useCallback(async () => {
    const normalizedSelected = normalizeCoinList(selectedPairs)
    if (!normalizedSelected.length) {
      throw new Error('Seleziona almeno una moneta')
    }

    const normalizedParams = {}
    for (const key of PARAM_KEYS) {
      const raw = strategyParams[key]
      if (raw == null || String(raw).trim() === '') continue
      const numeric = Number(String(raw).trim())
      if (!Number.isFinite(numeric)) {
        throw new Error(`Parametro non numerico: ${key}`)
      }
      normalizedParams[key] = numeric
    }

    setSaving(true)
    const res = await fetch(`${apiBase}/runtime-config`, {
      method: 'POST',
      headers: { ...getHeaders(), 'Content-Type': 'application/json' },
      credentials: 'same-origin',
      body: JSON.stringify({
        strategy_mode: strategyMode,
        trading_pairs: normalizedSelected,
        strategy_params: normalizedParams,
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
    const runtimeParams = normalizeStrategyParams(runtime.strategy_params || {})

    setStrategyMode(runtimeMode === 'scalping' ? 'scalping' : 'trend')
    setSelectedPairs(runtimeSelected.length ? runtimeSelected : normalizedSelected)
    setStrategyParams((prev) => ({ ...prev, ...runtimeParams }))
    setLoadError('')
    return json
  }, [apiBase, selectedPairs, strategyMode, strategyParams])

  const mergedPreviewParams = useMemo(() => ({ ...defaultParams, ...strategyParams }), [defaultParams, strategyParams])

  return {
    loading,
    saving,
    loadError,
    availablePairs,
    strategyMode,
    setStrategyMode,
    selectedPairs,
    toggleCoin,
    strategyParams: mergedPreviewParams,
    setStrategyParam,
    resetStrategyParams,
    save,
    reload: load,
  }
}