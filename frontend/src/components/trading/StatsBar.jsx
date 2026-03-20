import React from 'react'
import { fmtPrice, fmtVol } from './formatters'

export default function StatsBar({ stats24h }) {
  if (!stats24h) return null

  const high = stats24h.high || 0
  const low = stats24h.low || 0
  const volume = stats24h.volume || 0
  const open = stats24h.open || 0
  const close = stats24h.close || 0

  return (
    <div className="flex items-center gap-4 px-4 py-1.5 border-b border-gray-800/50 text-[11px] text-gray-400 font-mono overflow-x-auto">
      <span>24h High <span className="text-green-400">${fmtPrice(high)}</span></span>
      <span className="text-gray-700">|</span>
      <span>24h Low <span className="text-red-400">${fmtPrice(low)}</span></span>
      <span className="text-gray-700">|</span>
      <span>24h Vol <span className="text-blue-400">{fmtVol(volume)}</span></span>
      <span className="text-gray-700">|</span>
      <span>O <span className="text-gray-300">${fmtPrice(open)}</span></span>
      <span>C <span className="text-white">${fmtPrice(close)}</span></span>
    </div>
  )
}