import React from 'react'
import { fmtPrice } from './formatters'

const INTERVALS = [
  { value: '5m', label: '5m' },
  { value: '15m', label: '15m' },
  { value: '1h', label: '1H' },
  { value: '4h', label: '4H' },
  { value: '1d', label: 'D' },
]

export default function ChartToolbar({
  coins,
  selectedCoin,
  setSelectedCoin,
  interval,
  setInterval,
  lastPrice,
  isPositive,
  changePct,
}) {
  return (
    <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between px-4 py-3 border-b border-gray-800 gap-2">
      <div className="flex items-center gap-3 flex-wrap">
        <select
          value={selectedCoin}
          onChange={(e) => setSelectedCoin(e.target.value)}
          className="bg-gray-800 border border-gray-700 rounded-lg px-3 py-1.5 text-sm font-bold text-white focus:outline-none focus:border-blue-500"
        >
          {coins.map(c => <option key={c} value={c}>{c}/USDC</option>)}
        </select>

        {lastPrice != null && (
          <span className={`text-xl font-bold font-mono ${isPositive ? 'text-green-400' : 'text-red-400'}`}>
            ${fmtPrice(lastPrice)}
          </span>
        )}
        {changePct != null && (
          <span className={`text-sm font-bold ${isPositive ? 'text-green-400' : 'text-red-400'}`}>
            {isPositive ? '+' : ''}{changePct}%
          </span>
        )}
      </div>

      <div className="flex bg-gray-800 rounded-lg border border-gray-700 overflow-hidden">
        {INTERVALS.map(i => (
          <button
            key={i.value}
            onClick={() => setInterval(i.value)}
            className={`px-3 py-1.5 text-xs font-medium transition-colors ${
              interval === i.value
                ? 'bg-blue-600 text-white'
                : 'text-gray-400 hover:text-white hover:bg-gray-700'
            }`}
          >
            {i.label}
          </button>
        ))}
      </div>
    </div>
  )
}