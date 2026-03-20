import React from 'react'

export default function DrawdownBar({ peakValue, currentBalance, maxDrawdownPct = 0.15 }) {
  const peak = parseFloat(peakValue || 0)
  const current = parseFloat(currentBalance || 0)

  if (peak <= 0 || isNaN(peak) || isNaN(current)) {
    return null
  }

  const drawdownPct = Math.max(0, ((peak - current) / peak) * 100)
  const maxPct = maxDrawdownPct * 100
  const fillPct = Math.min((drawdownPct / maxPct) * 100, 100)

  let barColor = 'bg-green-500'
  if (drawdownPct > maxPct * 0.7) barColor = 'bg-red-500'
  else if (drawdownPct > maxPct * 0.4) barColor = 'bg-yellow-500'

  return (
    <div className="bg-gray-900 rounded-xl p-4 border border-gray-800">
      <div className="flex items-center justify-between mb-2">
        <span className="text-xs font-medium text-gray-400 uppercase tracking-wide">Drawdown</span>
        <span className={`text-sm font-bold ${drawdownPct > maxPct * 0.7 ? 'text-red-400' : 'text-gray-300'}`}>
          {drawdownPct.toFixed(2)}% / {maxPct.toFixed(0)}%
        </span>
      </div>
      <div className="w-full bg-gray-800 rounded-full h-2.5 overflow-hidden">
        <div
          className={`h-full rounded-full transition-all duration-500 ${barColor}`}
          style={{ width: `${fillPct}%` }}
        />
      </div>
      <div className="flex justify-between mt-1">
        <span className="text-[10px] text-gray-600">Peak: ${peak.toFixed(2)}</span>
        <span className="text-[10px] text-gray-600">Current: ${current.toFixed(2)}</span>
      </div>
    </div>
  )
}