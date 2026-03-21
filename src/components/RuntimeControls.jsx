import React, { useMemo, useState } from 'react'
import { Settings2, Cpu, Coins, Plus, AlertTriangle } from 'lucide-react'
import useRuntimeConfig from '../hooks/useRuntimeConfig'
import Toast from './Toast'

export default function RuntimeControls() {
  const {
    loading,
    saving,
    loadError,
    availablePairs,
    strategyMode,
    setStrategyMode,
    selectedPairs,
    toggleCoin,
    save,
  } = useRuntimeConfig()

  const [toast, setToast] = useState({ type: 'info', message: '' })
  const [coinInput, setCoinInput] = useState('')

  const sortedPairs = useMemo(() => {
    const merged = new Set([...(Array.isArray(availablePairs) ? availablePairs : []), ...selectedPairs])
    return [...merged].sort((a, b) => a.localeCompare(b))
  }, [availablePairs, selectedPairs])

  const onAddCoin = () => {
    const coin = coinInput.trim().toUpperCase()
    if (!coin) return

    if (!/^[A-Z0-9]{1,20}$/.test(coin)) {
      setToast({ type: 'error', message: 'Formato coin non valido.' })
      return
    }

    if (selectedPairs.includes(coin)) {
      setToast({ type: 'info', message: `${coin} è già selezionata.` })
      setCoinInput('')
      return
    }

    toggleCoin(coin)
    setCoinInput('')
    setToast({
      type: sortedPairs.includes(coin) ? 'success' : 'info',
      message: sortedPairs.includes(coin)
        ? `${coin} aggiunta alle monete monitorate.`
        : `${coin} aggiunta manualmente. Se Hyperliquid non la supporta, il backend lo segnalerà al salvataggio.`,
    })
  }

  const onSave = async () => {
    try {
      await save()
      setToast({ type: 'success', message: 'Impostazioni salvate: il bot applicherà strategia e monete nel prossimo ciclo.' })
    } catch (err) {
      setToast({ type: 'error', message: `Salvataggio fallito: ${err.message}` })
    }
  }

  if (loading) {
    return (
      <div className="bg-gray-900 rounded-xl p-6 border border-gray-800">
        <div className="animate-pulse space-y-3">
          <div className="h-4 bg-gray-800 rounded w-56" />
          <div className="h-9 bg-gray-800 rounded w-72" />
          <div className="h-24 bg-gray-800 rounded" />
        </div>
      </div>
    )
  }

  return (
    <>
      <div className="bg-gray-900 rounded-xl p-6 border border-gray-800 space-y-5">
        <div className="flex items-center gap-2">
          <Settings2 size={18} className="text-cyan-400" />
          <h3 className="text-lg font-semibold">Runtime Trading Controls</h3>
        </div>

        {loadError && (
          <div className="rounded-lg border border-yellow-700/50 bg-yellow-900/20 p-3 flex items-start gap-2">
            <AlertTriangle size={14} className="text-yellow-400 mt-0.5 shrink-0" />
            <p className="text-xs text-yellow-200">{loadError}</p>
          </div>
        )}

        <div>
          <p className="text-xs text-gray-400 mb-2 flex items-center gap-2">
            <Cpu size={12} />
            Strategia attiva
          </p>
          <div className="flex gap-2">
            <button
              onClick={() => setStrategyMode('trend')}
              className={`px-3 py-2 rounded-lg text-sm border transition-colors ${
                strategyMode === 'trend'
                  ? 'bg-blue-600/20 border-blue-500 text-blue-300'
                  : 'bg-gray-800 border-gray-700 text-gray-400 hover:text-white'
              }`}
            >
              Trend
            </button>
            <button
              onClick={() => setStrategyMode('scalping')}
              className={`px-3 py-2 rounded-lg text-sm border transition-colors ${
                strategyMode === 'scalping'
                  ? 'bg-orange-600/20 border-orange-500 text-orange-300'
                  : 'bg-gray-800 border-gray-700 text-gray-400 hover:text-white'
              }`}
            >
              Scalping
            </button>
          </div>
          <p className="text-[11px] text-gray-500 mt-2">
            {strategyMode === 'scalping'
              ? 'Profilo più rapido e aggressivo, con risk guardrail automatici.'
              : 'Profilo conservativo multi-timeframe 1H/4H/1D.'}
          </p>
        </div>

        <div>
          <p className="text-xs text-gray-400 mb-2 flex items-center gap-2">
            <Coins size={12} />
            Monete monitorate dal LLM ({selectedPairs.length})
          </p>

          <div className="flex flex-col sm:flex-row gap-2 mb-3">
            <input
              list="runtime-available-coins"
              value={coinInput}
              onChange={(e) => setCoinInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') {
                  e.preventDefault()
                  onAddCoin()
                }
              }}
              placeholder="Scrivi coin (es. SOL)"
              className="flex-1 bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-cyan-500"
            />
            <button
              onClick={onAddCoin}
              className="inline-flex items-center justify-center gap-1 px-3 py-2 rounded-lg bg-cyan-600 hover:bg-cyan-700 text-sm font-medium"
            >
              <Plus size={14} />
              Aggiungi
            </button>
            <datalist id="runtime-available-coins">
              {sortedPairs.map((coin) => (
                <option key={coin} value={coin} />
              ))}
            </datalist>
          </div>

          <div className="max-h-52 overflow-y-auto rounded-lg border border-gray-800 p-3 grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-2">
            {sortedPairs.map((coin) => {
              const active = selectedPairs.includes(coin)
              return (
                <button
                  key={coin}
                  onClick={() => toggleCoin(coin)}
                  className={`px-2 py-1.5 text-xs rounded border transition-colors ${
                    active
                      ? 'bg-green-600/20 border-green-500 text-green-300'
                      : 'bg-gray-800 border-gray-700 text-gray-400 hover:text-white'
                  }`}
                >
                  {coin}
                </button>
              )
            })}
          </div>
          <p className="text-[11px] text-gray-500 mt-2">
            Puoi scrivere la coin oppure selezionarla dai pulsanti; il bot userà solo quelle salvate.
          </p>
        </div>

        <div className="flex items-center gap-3">
          <button
            onClick={onSave}
            disabled={saving || selectedPairs.length === 0}
            className="px-4 py-2 rounded-lg bg-cyan-600 hover:bg-cyan-700 disabled:opacity-50 disabled:cursor-not-allowed text-sm font-medium"
          >
            {saving ? 'Saving...' : 'Save runtime settings'}
          </button>
          <span className="text-xs text-gray-500">
            Applicazione effettiva: prossimo ciclo del bot
          </span>
        </div>
      </div>

      <Toast
        type={toast.type}
        message={toast.message}
        onClose={() => setToast({ type: 'info', message: '' })}
      />
    </>
  )
}