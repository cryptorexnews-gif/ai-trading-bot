import React, { useState, useEffect, useRef } from 'react'
import { fmtPrice, fmtSize } from './formatters'

export default function OrderBookRow({ price, size, cumulative, maxSize, side, prevSize }) {
  const [flash, setFlash] = useState(null)
  const prevSizeRef = useRef(size)

  useEffect(() => {
    if (prevSizeRef.current !== size && prevSizeRef.current !== undefined) {
      const diff = size - prevSizeRef.current
      if (Math.abs(diff) > 0.001) {
        setFlash(diff > 0 ? 'increase' : 'decrease')
        const timer = setTimeout(() => setFlash(null), 400)
        return () => clearTimeout(timer)
      }
    }
    prevSizeRef.current = size
  }, [size])

  const isBid = side === 'bid'
  const depthPct = maxSize > 0 ? (size / maxSize) * 100 : 0

  const flashClass = flash === 'increase'
    ? 'bg-green-500/20'
    : flash === 'decrease'
    ? 'bg-red-500/20'
    : ''

  return (
    <div className={`relative grid grid-cols-3 py-[2px] px-3 text-[11px] font-mono transition-colors duration-150 ${flashClass} hover:bg-gray-800/40`}>
      <div
        className={`absolute top-0 bottom-0 ${isBid ? 'left-0 bg-green-500/12' : 'right-0 bg-red-500/12'}`}
        style={{ width: `${depthPct}%` }}
      />
      <span className={`relative z-10 ${isBid ? 'text-green-400' : 'text-red-400'}`}>
        {fmtPrice(price)}
      </span>
      <span className="text-gray-300 text-right relative z-10">{fmtSize(size)}</span>
      <span className="text-gray-500 text-right relative z-10">{fmtSize(cumulative)}</span>
    </div>
  )
}