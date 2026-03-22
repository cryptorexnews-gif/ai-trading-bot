import React from 'react'
import { SlidersHorizontal } from 'lucide-react'

const FIELDS = [
  { key: 'cycle_sec', label: 'Cycle sec', step: '1' },
  { key: 'min_cycle_sec', label: 'Min cycle sec', step: '1' },
  { key: 'max_cycle_sec', label: 'Max cycle sec', step: '1' },
  { key: 'max_trades_per_cycle', label: 'Max trades/cycle', step: '1' },
  { key: 'hard_max_leverage', label: 'Max leverage', step: '0.1' },
  { key: 'min_confidence_open', label: 'Min confidence (%)', step: '0.1', percent: true },
  { key: 'min_confidence_manage', label: 'Min manage confidence (%)', step: '0.1', percent: true },
  { key: 'max_order_margin_pct', label: 'Max order margin (%)', step: '0.1', percent: true },
  { key: 'trade_cooldown_sec', label: 'Trade cooldown sec', step: '1' },
  { key: 'daily_notional_limit_usd', label: 'Daily notional USD', step: '0.1' },
  { key: 'max_drawdown_pct', label: 'Max drawdown (%)', step: '0.1', percent: true },
  { key: 'max_single_asset_pct', label: 'Max single asset (%)', step: '0.1', percent: true },
  { key: 'emergency_margin_threshold', label: 'Emergency margin threshold (%)', step: '0.1', percent: true },
  { key: 'position_size_pct', label: 'Position size (%)', step: '0.1', percent: true },
  { key: 'volume_confirmation_threshold', label: 'Volume confirmation', step: '0.1' },
  { key: 'sl_pct', label: 'Stop loss (%)', step: '0.1', percent: true },
  { key: 'tp_pct', label: 'Take profit (%)', step: '0.1', percent: true },
  { key: 'break_even_activation_pct', label: 'Break-even activation (%)', step: '0.1', percent: true },
  { key: 'trailing_activation_pct', label: 'Trailing activation (%)', step: '0.1', percent: true },
  { key: 'trailing_callback', label: 'Trailing callback (%)', step: '0.1', percent: true },
]

export default function RuntimeStrategyParams({ strategyMode, strategyParams, defaultPreset, onChange }) {
  return (
    <div>
      <p className="text-xs text-gray-400 mb-2 flex items-center gap-2">
        <SlidersHorizontal size={12} />
        Parametri runtime ({strategyMode === 'scalping' ? 'Scalping' : 'Trend'})
      </p>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2.5">
        {FIELDS.map((field) => {
          const defaultValue = defaultPreset?.[field.key] ?? '—'
          return (
            <label key={field.key} className="bg-gray-800/40 border border-gray-700 rounded-lg p-2 flex flex-col gap-1">
              <span className="text-[11px] text-gray-400">{field.label}</span>
              <input
                value={strategyParams[field.key] ?? ''}
                onChange={(e) => onChange(field.key, e.target.value)}
                inputMode="decimal"
                type="number"
                step={field.step}
                placeholder={field.percent ? 'es. 2 = 2%' : 'valore diretto'}
                className="bg-gray-900 border border-gray-700 rounded px-2 py-1.5 text-sm text-white focus:outline-none focus:border-cyan-500"
              />
              <span className="text-[10px] text-gray-500">Default preset: {defaultValue}</span>
            </label>
          )
        })}
      </div>
      <p className="text-[11px] text-gray-500 mt-2">
        Regola unica: inserisci sempre numeri diretti. Esempi: <strong>1</strong> = 1 secondo, 1 USD, 1x; per percentuali <strong>2</strong> = 2%.
      </p>
    </div>
  )
}