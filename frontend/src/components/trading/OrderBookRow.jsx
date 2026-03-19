import React, { useState, useEffect, useRef } from 'react'
import { fmtPrice, fmtSize } from './formatters'

export default function OrderBookRow({ price, size, cumulative, maxSize, side, prevSize }) {
  const [flash, setFlash] = useState(null)
  const prevSizeRef = useRef(size)

  useEffect(() => {
    if (prevSizeRef.current !== size && prevSizeRef.current !== undefined) {
      const diff = size - prevSizeRef.current
      if (Math.abs(diff) > 0.001) {
        if (side === 'bid') {
          setFlash(diff > 0 ? 'bid-increase' : 'bid-decrease')
        } else {
          setFlash(diff > 0 ? 'ask-increase' : 'ask-decrease')
        }
        const timer = setTimeout(() => setFlash(null), 500)
        return () => clearTimeout(timer)
      }
    }
    prevSizeRef.current = size
  }, [size, side])

  const isBid = side === 'bid'
  const depthPct = maxSize > 0 ? (size / maxSize) * 100 : 0

  const flashClasses = {
    'bid-increase': 'bg-green-500/25',
    'bid-decrease': 'bg-green-800/15',
    'ask-increase': 'bg-red-500/25',
    'ask-decrease': 'bg-red-800/15',
  }
  const flashClass = flash ? (flashClasses[flash] || '') : ''

  return (
    <div className={`relative grid grid-cols-3 py-[2px] px-3 text-[11px] font-mono transition-colors duration-200 ${flashClass} hover:bg-gray-800/30`}>
      {/* Depth bar — fills from right for both sides (Hyperliquid style) */}
      <div
        className={`absolute right-0 top-0 bottom-0 transition-all duration-300 ${
          isBid ? 'bg-green-500/15' : 'bg-red-500/15'
        }`}
        style={{ width: `${Math.min(depthPct, 100)}%` }}
      />
      <span className={`relative z-10 ${isBid ? 'text-green-400' : 'text-red-400'}`}>
        {fmtPrice(price)}
      </span>
      <span className="text-gray-300 text-right relative z-10">{fmtSize(size)}</span>
      <span className="text-gray-500 text-right relative z-10">{fmtSize(cumulative)}</span>
    </div>
  )
}