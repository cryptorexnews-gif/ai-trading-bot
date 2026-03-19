import React, { useMemo } from 'react'
import OrderBookRow from './OrderBookRow'
import { fmtPrice } from './formatters'

/**
 * Group order book levels by tick size.
 */
function groupLevels(levels, tickSize, side) {
  if (!tickSize || tickSize <= 0) return levels

  const grouped = {}
  for (const level of levels) {
    let bucket
    if (side === 'bid') {
      bucket = Math.floor(level.price / tickSize) * tickSize
    } else {
      bucket = Math.ceil(level.price / tickSize) * tickSize
    }
    if (!grouped[bucket]) {
      grouped[bucket] = { price: bucket, size: 0, orders: 0 }
    }
    grouped[bucket].size += level.size
    grouped[bucket].orders += (level.orders || 1)
  }

  const result = Object.values(grouped)
  if (side === 'bid') {
    result.sort((a, b) => b.price - a.price)
  } else {
    result.sort((a, b) => a.price - b.price)
  }
  return result
}

const DEPTH_OPTIONS = [
  { value: 1, label: '±1%' },
  { value: 5, label: '±5%' },
  { value: 10, label: '±10%' },
  { value: 25, label: '±25%' },
  { value: 50, label: '±50%' },
]

const LEVEL_OPTIONS = [
  { value: 10, label: '10' },
  { value: 25, label: '25' },
  { value: 50, label: '50' },
  { value: 100, label: '100' },
  { value: 0, label: 'All' },
]

export default function OrderBookPanel({
  bids,
  asks,
  spread,
  spreadPct,
  lastPrice,
  isPositive,
  obLevels,
  setObLevels,
  tickSize,
  setTickSize,
  tickOptions,
  depthPct,
  setDepthPct,
  loading,
  prevBids,
  prevAsks,
  panelHeight,
  totalBidLevels = 0,
  totalAskLevels = 0,
}) {
  // Group by tick size
  const groupedBids = useMemo(() => groupLevels(bids, tickSize, 'bid'), [bids, tickSize])
  const groupedAsks = useMemo(() => groupLevels(asks, tickSize, 'ask'), [asks, tickSize])

  // 0 means "All"
  const effectiveLevels = obLevels === 0 ? 9999 : obLevels

  const maxBidSize = groupedBids.length > 0 ? Math.max(...groupedBids.map(b => b.size)) : 1
  const maxAskSize = groupedAsks.length > 0 ? Math.max(...groupedAsks.map(a => a.size)) : 1
  const maxSize = Math.max(maxBidSize, maxAskSize)

  const displayBids = groupedBids.slice(0, effectiveLevels)
  const displayAsks = groupedAsks.slice(0, effectiveLevels)

  let bidCum = 0
  const bidsWithCum = displayBids.map(b => { bidCum += b.size; return { ...b, cumulative: bidCum } })
  let askCum = 0
  const asksWithCum = displayAsks.map(a => { askCum += a.size; return { ...a, cumulative: askCum } })

  const totalBidSize = groupedBids.reduce((s, b) => s + b.size, 0)
  const totalAskSize = groupedAsks.reduce((s, a) => s + a.size, 0)
  const bidPct = totalBidSize + totalAskSize > 0 ? Math.round((totalBidSize / (totalBidSize + totalAskSize)) * 100) : 50
  const delta = bidPct - 50

  // Calculate heights
  const overhead = 160
  const availableHeight = panelHeight - overhead
  const halfHeight = Math.max(80, Math.floor(availableHeight / 2))

  return (
    <div className="w-full lg:w-[290px] border-t lg:border-t-0 lg:border-l border-gray-800 flex flex-col" style={{ height: panelHeight }}>
      {/* Header row 1: Title + level count */}
      <div className="flex items-center justify-between px-3 py-1 border-b border-gray-800 bg-gray-900/50">
        <div className="flex items-center gap-1.5">
          <span className="text-[10px] text-gray-500 uppercase tracking-wider font-semibold">Order Book</span>
          <span className="text-[9px] text-gray-600">
            ({totalBidLevels}b/{totalAskLevels}a)
          </span>
        </div>
        {/* Depth % selector */}
        <div className="flex gap-0.5">
          {DEPTH_OPTIONS.map(d => (
            <button
              key={d.value}
              onClick={() => setDepthPct(d.value)}
              className={`text-[8px] px-1 py-0.5 rounded transition-colors ${
                depthPct === d.value ? 'bg-purple-600 text-white' : 'text-gray-500 hover:text-gray-300 bg-gray-800'
              }`}
            >
              {d.label}
            </button>
          ))}
        </div>
      </div>

      {/* Header row 2: Tick size + Levels */}
      <div className="flex items-center justify-between px-3 py-1 border-b border-gray-800/70">
        <div className="flex items-center gap-1">
          <span className="text-[8px] text-gray-600 mr-0.5">Group:</span>
          {tickOptions.map(t => (
            <button
              key={t}
              onClick={() => setTickSize(t)}
              className={`text-[8px] px-1 py-0.5 rounded transition-colors ${
                tickSize === t ? 'bg-yellow-600 text-white' : 'text-gray-500 hover:text-gray-300 bg-gray-800'
              }`}
            >
              {t === 0 ? 'Raw' : t}
            </button>
          ))}
        </div>
        <div className="flex items-center gap-1">
          <span className="text-[8px] text-gray-600 mr-0.5">Show:</span>
          {LEVEL_OPTIONS.map(opt => (
            <button
              key={opt.value}
              onClick={() => setObLevels(opt.value)}
              className={`text-[8px] px-1 py-0.5 rounded transition-colors ${
                obLevels === opt.value ? 'bg-blue-600 text-white' : 'text-gray-500 hover:text-gray-300 bg-gray-800'
              }`}
            >
              {opt.label}
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
          <div className="overflow-y-auto flex flex-col justify-end" style={{ height: halfHeight }}>
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
          <div className="flex items-center justify-between px-3 py-1.5 border-y border-gray-800 bg-gray-800/20 shrink-0">
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
          <div className="overflow-y-auto" style={{ height: halfHeight }}>
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
          <div className="px-3 py-2 border-t border-gray-800 shrink-0">
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