import React from 'react'
import { SlidersHorizontal } from 'lucide-react'

const FIELDS = [
  { key: 'cycle_sec', label: 'Cycle sec', step: '1' },
  { key: 'min_cycle_sec', label: 'Min cycle sec', step: '1' },
  { key: 'max_cycle_sec', label: 'Max cycle sec', step: '1' },
  { key: 'max_trades_per_cycle', label: 'Max trades/cycle', step: '1' },
  { key: 'hard_max_leverage', label: 'Max leverage', step: '0.1' },
  { key: 'min_confidence_open', label: 'Min conf open', step: '0.01' },
  { key: 'min_confidence_manage', label: 'Min conf manage', step: '0.01' },
  { key: 'max_order_margin_pct', label: 'Max order margin pct', step: '0.01' },
  { key: 'trade_cooldown_sec', label: 'Trade cooldown sec', step: '1' },
  { key: 'daily_notional_limit_usd', label: 'Daily notional USD', step: '0.1' },
  { key: 'max_drawdown_pct', label: 'Max drawdown pct', step: '0.01' },
  { key: 'max_single_asset_pct', label: 'Max single asset pct', step: '0.01' },
  { key: 'emergency_margin_threshold', label: 'Emergency margin threshold', step: '0.01' },
  { key: 'position_size_pct', label: 'Position size pct', step: '0.001' },
  { key: 'volume_confirmation_threshold', label: 'Volume confirmation', step: '0.1' },
  { key: 'sl_pct', label: 'Stop loss pct', step: '0.001' },
  { key: 'tp_pct', label: 'Take profit pct', step: '0.001' },
  { key: 'break_even_activation_pct', label: 'Break-even activation pct', step: '0.001' },
  { key: 'trailing_activation_pct', label: 'Trailing activation pct', step: '0.001' },
  { key: 'trailing_callback', label: 'Trailing callback pct', step: '0.001' },
]

export default function RuntimeStrategyParams({ strategyMode, strategyParams, onChange }) {
  return (
    <div>
      <p className="text-xs text-gray-400 mb-2 flex items-center gap-2">
        <SlidersHorizontal size={12} />
        Parametri runtime ({strategyMode === 'scalping' ? 'Scalping' : 'Trend'})
      </p>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2.5">
        {FIELDS.map((field) => (
          <label key={field.key} className="bg-gray-800/40 border border-gray-700 rounded-lg p-2 flex flex-col gap-1">
            <span className="text-[11px] text-gray-400">{field.label}</span>
            <input
              value={strategyParams[field.key] ?? ''}
              onChange={(e) => onChange(field.key, e.target.value)}
              inputMode="decimal"
              type="number"
              step={field.step}
              className="bg-gray-900 border border-gray-700 rounded px-2 py-1.5 text-sm text-white focus:outline-none focus:border-cyan-500"
            />
          </label>
        ))}
      </div>
      <p className="text-[11px] text-gray-500 mt-2">
        Questi valori vengono salvati in runtime config e applicati automaticamente dal bot nel ciclo successivo.
      </p>
    </div>
  )
}