import React from 'react'
import OrderBookRow from './OrderBookRow'
import { fmtPrice } from './formatters'

export default function OrderBookPanel({
  bids,
  asks,
  spread,
  spreadPct,
  lastPrice,
  isPositive,
  obLevels,
  setObLevels,
  loading,
  prevBids,
  prevAsks,
}) {
  const maxBidSize = bids.length > 0 ? Math.max(...bids.map(b => b.size)) : 1
  const maxAskSize = asks.length > 0 ? Math.max(...asks.map(a => a.size)) : 1
  const maxSize = Math.max(maxBidSize, maxAskSize)

  const displayBids = bids.slice(0, obLevels)
  const displayAsks = asks.slice(0, obLevels)

  let bidCum = 0
  const bidsWithCum = displayBids.map(b => { bidCum += b.size; return { ...b, cumulative: bidCum } })
  let askCum = 0
  const asksWithCum = displayAsks.map(a => { askCum += a.size; return { ...a, cumulative: askCum } })

  const totalBidSize = bids.reduce((s, b) => s + b.size, 0)
  const totalAskSize = asks.reduce((s, a) => s + a.size, 0)
  const bidPct = totalBidSize + totalAskSize > 0 ? Math.round((totalBidSize / (totalBidSize + totalAskSize)) * 100) : 50
  const delta = bidPct - 50

  return (
    <div className="w-full lg:w-[290px] border-t lg:border-t-0 lg:border-l border-gray-800 flex flex-col">
      {/* Header */}
      <div className="flex items-center justify-between px-3 py-1.5 border-b border-gray-800 bg-gray-900/50">
        <span className="text-[10px] text-gray-500 uppercase tracking-wider font-semibold">Order Book</span>
        <div className="flex gap-1">
          {[10, 15, 25].map(n => (
            <button
              key={n}
              onClick={() => setObLevels(n)}
              className={`text-[9px] px-1.5 py-0.5 rounded ${
                obLevels === n ? 'bg-blue-600 text-white' : 'text-gray-500 hover:text-gray-300 bg-gray-800'
              }`}
            >
              {n}
            </button>
          ))}
        </div>
      </div>

      {/* Column headers */}
      <div className="grid grid-cols-3 text-[9px] text-gray-600 uppercase tracking-wider px-3 py-1 border-b border-gray-800/50">
        <span>Price</span>
        <span className="text-right">Size</span>
        <span className="text-right">Total</span>
      </div>

      {loading && bids.length === 0 ? (
        <div className="flex-1 flex items-center justify-center py-8">
          <div className="flex flex-col gap-1 w-full px-3">
            {[...Array(10)].map((_, i) => (
              <div key={i} className="h-3 bg-gray-800 rounded animate-pulse" style={{ width: `${50 + Math.random() * 50}%` }} />
            ))}
          </div>
        </div>
      ) : (
        <div className="flex flex-col flex-1 overflow-hidden">
          {/* Asks (reversed — lowest ask at bottom) */}
          <div className="flex-1 overflow-y-auto flex flex-col justify-end" style={{ maxHeight: `${obLevels * 18 + 10}px` }}>
            {[...asksWithCum].reverse().map((ask, idx) => (
              <OrderBookRow
                key={`a-${idx}`}
                price={ask.price}
                size={ask.size}
                cumulative={ask.cumulative}
                maxSize={maxSize}
                side="ask"
                prevSize={prevAsks[ask.price]}
              />
            ))}
          </div>

          {/* Spread + Last Price */}
          <div className="flex items-center justify-between px-3 py-1.5 border-y border-gray-800 bg-gray-800/20">
            <span className={`text-sm font-bold font-mono ${isPositive ? 'text-green-400' : 'text-red-400'}`}>
              {lastPrice ? `$${fmtPrice(lastPrice)}` : '—'}
            </span>
            <div className="flex items-center gap-2 text-[10px]">
              <span className="text-gray-500">Spread</span>
              <span className="text-yellow-400 font-mono">{fmtPrice(spread)}</span>
              <span className="text-gray-600">({spreadPct.toFixed(3)}%)</span>
            </div>
          </div>

          {/* Bids */}
          <div className="flex-1 overflow-y-auto" style={{ maxHeight: `${obLevels * 18 + 10}px` }}>
            {bidsWithCum.map((bid, idx) => (
              <OrderBookRow
                key={`b-${idx}`}
                price={bid.price}
                size={bid.size}
                cumulative={bid.cumulative}
                maxSize={maxSize}
                side="bid"
                prevSize={prevBids[bid.price]}
              />
            ))}
          </div>

          {/* Bid/Ask Imbalance */}
          <div className="px-3 py-2 border-t border-gray-800">
            <div className="flex items-center justify-between text-[10px] text-gray-500 mb-1">
              <span>Bids {bidPct}%</span>
              <span className={`font-bold ${delta > 0 ? 'text-green-400' : delta < 0 ? 'text-red-400' : 'text-gray-400'}`}>
                Δ {delta > 0 ? '+' : ''}{delta}%
              </span>
              <span>Asks {100 - bidPct}%</span>
            </div>
            <div className="w-full h-1.5 bg-gray-800 rounded-full overflow-hidden flex">
              <div
                className="h-full bg-green-500 transition-all duration-500"
                style={{ width: `${bidPct}%`, borderRadius: bidPct >= 100 ? '9999px' : '9999px 0 0 9999px' }}
              />
              <div
                className="h-full bg-red-500 transition-all duration-500"
                style={{ width: `${100 - bidPct}%`, borderRadius: bidPct <= 0 ? '9999px' : '0 9999px 9999px 0' }}
              />
            </div>
          </div>
        </div>
      )}
    </div>
  )
}