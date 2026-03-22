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

const PERCENT_PARAM_KEYS = new Set([
  'min_confidence_open',
  'min_confidence_manage',
  'max_order_margin_pct',
  'max_drawdown_pct',
  'max_single_asset_pct',
  'emergency_margin_threshold',
  'position_size_pct',
  'sl_pct',
  'tp_pct',
  'break_even_activation_pct',
  'trailing_activation_pct',
  'trailing_callback',
])

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

function decimalToDisplayPercent(value) {
  const n = Number(value)
  if (!Number.isFinite(n)) return ''
  const pct = n * 100
  return String(Number(pct.toFixed(4)))
}

function displayPercentToDecimal(value) {
  const n = Number(value)
  if (!Number.isFinite(n)) return NaN
  return Number((n / 100).toFixed(8))
}

function normalizeStrategyParams(raw) {
  if (!raw || typeof raw !== 'object') return {}
  const result = {}
  for (const key of PARAM_KEYS) {
    const value = raw[key]
    if (value == null || value === '') continue

    if (PERCENT_PARAM_KEYS.has(key)) {
      result[key] = decimalToDisplayPercent(value)
    } else {
      result[key] = String(value)
    }
  }
  return result
}

export default function useRuntimeConfig() {
  const apiBase = getApiBase()
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [loadError, setLoadError] = useState('')
  const [availablePairs, setAvailablePairs] = useState(DEFAULT_PAIRS)
  const [strategyMode, setStrategyModeState] = useState('trend')
  const [selectedPairs, setSelectedPairs] = useState(['BTC', 'ETH'])
  const [strategyParams, setStrategyParams] = useState({})
  const [defaultParams, setDefaultParams] = useState({})
  const [strategyPresets, setStrategyPresets] = useState({ trend: {}, scalping: {} })

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

      const rawPresets = json.strategy_presets || {}
      const normalizedPresets = {
        trend: normalizeStrategyParams(rawPresets.trend || {}),
        scalping: normalizeStrategyParams(rawPresets.scalping || {}),
      }

      setStrategyPresets(normalizedPresets)
      setAvailablePairs(available.length ? available : DEFAULT_PAIRS)
      setSelectedPairs(selected.length ? selected : ['BTC', 'ETH'])
      setStrategyModeState(mode === 'scalping' ? 'scalping' : 'trend')
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
        setStrategyModeState('trend')
        setDefaultParams({})
        setStrategyParams({})
        setStrategyPresets({ trend: {}, scalping: {} })
        setLoadError('Runtime config non disponibile: fallback attivo su config base.')
        setLoading(false)
        return
      } catch {
        setAvailablePairs(DEFAULT_PAIRS)
        setSelectedPairs(['BTC', 'ETH'])
        setStrategyModeState('trend')
        setDefaultParams({})
        setStrategyParams({})
        setStrategyPresets({ trend: {}, scalping: {} })
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

  const setStrategyMode = useCallback((mode) => {
    const normalized = String(mode || '').toLowerCase() === 'scalping' ? 'scalping' : 'trend'
    setStrategyModeState(normalized)

    const presetForMode = strategyPresets[normalized] || {}
    if (Object.keys(presetForMode).length > 0) {
      setStrategyParams({ ...presetForMode })
      setDefaultParams({ ...presetForMode })
    }
  }, [strategyPresets])

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

      if (PERCENT_PARAM_KEYS.has(key)) {
        const dec = displayPercentToDecimal(numeric)
        if (!Number.isFinite(dec)) {
          throw new Error(`Parametro percentuale non valido: ${key}`)
        }
        normalizedParams[key] = dec
      } else {
        normalizedParams[key] = numeric
      }
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

    setStrategyModeState(runtimeMode === 'scalping' ? 'scalping' : 'trend')
    setSelectedPairs(runtimeSelected.length ? runtimeSelected : normalizedSelected)
    setStrategyParams((prev) => ({ ...prev, ...runtimeParams }))
    setLoadError('')
    return json
  }, [apiBase, selectedPairs, strategyMode, strategyParams])

  const mergedPreviewParams = useMemo(() => ({ ...defaultParams, ...strategyParams }), [defaultParams, strategyParams])
  const activePreset = useMemo(() => strategyPresets[strategyMode] || {}, [strategyPresets, strategyMode])

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
    defaultParams,
    strategyPresets,
    activePreset,
    setStrategyParam,
    resetStrategyParams,
    save,
    reload: load,
  }
}