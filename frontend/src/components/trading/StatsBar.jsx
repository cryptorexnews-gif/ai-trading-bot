import React from 'react'
import { fmtPrice, fmtVol } from './formatters'

export default function StatsBar({ stats24h }) {
  if (!stats24h) return null

  return (
    <div className="flex items-center gap-4 px-4 py-1.5 border-b border-gray-800/50 text-[11px] text-gray-400 font-mono overflow-x-auto">
      <span>24h High <span className="text-green-400">${fmtPrice(stats24h.high)}</span></span>
      <span className="text-gray-700">|</span>
      <span>24h Low <span className="text-red-400">${fmtPrice(stats24h.low)}</span></span>
      <span className="text-gray-700">|</span>
      <span>24h Vol <span className="text-blue-400">{fmtVol(stats24h.volume)}</span></span>
      <span className="text-gray-700">|</span>
      <span>O <span className="text-gray-300">${fmtPrice(stats24h.open)}</span></span>
      <span>C <span className="text-white">${fmtPrice(stats24h.close)}</span></span>
    </div>
  )
}