import React from 'react'
import { fmtPrice } from './formatters'

const INTERVALS = [
  { value: '5m', label: '5m' },
  { value: '15m', label: '15m' },
  { value: '1h', label: '1H' },
  { value: '4h', label: '4H' },
  { value: '1d', label: '1D' },
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
    <div className="flex flex-col xs:flex-row items-start xs:items-center justify-between p-3 xs:p-4 border-b border-gray-800/50 gap-3 bg-gray-900/50 backdrop-blur-sm sticky top-0 z-10">
      <div className="flex flex-wrap items-center gap-2 flex-1 min-w-0">
        <select
          value={selectedCoin}
          onChange={(e) => setSelectedCoin(e.target.value)}
          className="bg-gray-800/50 border border-gray-600/50 hover:border-gray-500 focus:border-blue-500 rounded-lg px-3 py-1.5 text-sm font-bold text-white backdrop-blur-sm transition-all min-w-[80px]"
        >
          {coins.slice(0, 20).map(c => (  // Limit to 20 for mobile
            <option key={c} value={c}>{c}/USDC</option>
          ))}
        </select>

        {lastPrice != null && (
          <div className="flex items-baseline gap-1">
            <span className={`text-lg font-bold font-mono ${isPositive ? 'text-green-400' : 'text-red-400'}`}>
              ${fmtPrice(lastPrice)}
            </span>
            {changePct != null && (
              <span className={`text-xs font-bold ${isPositive ? 'text-green-400' : 'text-red-400'}`}>
                {isPositive ? '+' : ''}{changePct}
              </span>
            )}
          </div>
        )}
      </div>

      <div className="flex bg-gray-800/50 border border-gray-700/50 rounded-full overflow-hidden min-w-max">
        {INTERVALS.map(i => (
          <button
            key={i.value}
            onClick={() => setInterval(i.value)}
            className={`px-3 py-1.5 text-xs font-semibold transition-all whitespace-nowrap touch-manipulation ${
              interval === i.value
                ? 'bg-gradient-to-r from-blue-600 to-blue-700 text-white shadow-lg'
                : 'text-gray-400 hover:text-white hover:bg-gray-700/50'
            }`}
          >
            {i.label}
          </button>
        ))}
      </div>
    </div>
  )
}