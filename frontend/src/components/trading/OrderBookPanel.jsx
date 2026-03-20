import React, { useMemo } from 'react'
import { fmtPrice, fmtSize } from './formatters'

const SIG_FIG_OPTIONS = [
  { value: 2, label: '2' },
  { value: 3, label: '3' },
  { value: 4, label: '4' },
  { value: 5, label: '5' },
]

function safeNum(v, fallback = 0) {
  if (v == null || isNaN(v)) return fallback
  return Number(v)
}

export default function OrderBookPanel({
  bids,
  asks,
  spread,
  spreadPct,
  lastPrice,
  isPositive,
  nSigFigs,
  setNSigFigs,
  loading,
  panelHeight,
}) {
  const safeBids = Array.isArray(bids) ? bids : []
  const safeAsks = Array.isArray(asks) ? asks : []
  const safeSpread = safeNum(spread)
  const safeSpreadPct = safeNum(spreadPct)

  const bidsWithCum = useMemo(() => {
    let cum = 0
    return safeBids.map(b => {
      cum += safeNum(b.sz)
      return { px: safeNum(b.px), sz: safeNum(b.sz), n: safeNum(b.n), cum }
    })
  }, [safeBids])

  const asksWithCum = useMemo(() => {
    let cum = 0
    return safeAsks.map(a => {
      cum += safeNum(a.sz)
      return { px: safeNum(a.px), sz: safeNum(a.sz), n: safeNum(a.n), cum }
    })
  }, [safeAsks])

  const maxSize = useMemo(() => {
    const allSizes = [...safeBids.map(b => safeNum(b.sz)), ...safeAsks.map(a => safeNum(a.sz))]
    return allSizes.length > 0 ? Math.max(...allSizes, 0.0001) : 0.0001
  }, [safeBids, safeAsks])

  const totalBidSize = bidsWithCum.length > 0 ? bidsWithCum[bidsWithCum.length - 1].cum : 0
  const totalAskSize = asksWithCum.length > 0 ? asksWithCum[asksWithCum.length - 1].cum : 0
  const totalSize = totalBidSize + totalAskSize
  const bidPct = totalSize > 0 ? Math.round((totalBidSize / totalSize) * 100) : 50

  const overhead = 140
  const availableHeight = panelHeight - overhead
  const halfHeight = Math.max(60, Math.floor(availableHeight / 2))

  const isEmpty = safeBids.length === 0 && safeAsks.length === 0
  const isLoading = loading && isEmpty

  return (
    <div
      className="w-full lg:w-[280px] border-t lg:border-t-0 lg:border-l border-gray-800 flex flex-col bg-gray-950/50"
      style={{ height: panelHeight }}
    >
      {/* Header */}
      <div className="flex items-center justify-between px-3 py-2 border-b border-gray-800">
        <span className="text-[11px] text-gray-400 font-medium">Order Book</span>
        <div className="flex items-center gap-1">
          <span className="text-[9px] text-gray-600 mr-1">Sig</span>
          {SIG_FIG_OPTIONS.map(opt => (
            <button
              key={opt.value}
              onClick={() => setNSigFigs(opt.value)}
              className={`text-[10px] w-5 h-5 rounded flex items-center justify-center transition-colors ${
                nSigFigs === opt.value
                  ? 'bg-blue-600 text-white'
                  : 'text-gray-500 hover:text-gray-300 bg-gray-800/80 hover:bg-gray-700'
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

      {isLoading ? (
        <div className="flex-1 flex items-center justify-center">
          <div className="flex flex-col gap-1.5 w-full px-3">
            {[...Array(16)].map((_, i) => (
              <div key={i} className="h-[14px] bg-gray-800/40 rounded animate-pulse" style={{ width: `${30 + Math.random() * 65}%` }} />
            ))}
          </div>
        </div>
      ) : isEmpty ? (
        <div className="flex-1 flex items-center justify-center">
          <div className="text-center text-gray-600">
            <div className="text-2xl mb-2">📖</div>
            <p className="text-xs">No order book data</p>
            <p className="text-[10px] text-gray-700 mt-1">Connecting to Hyperliquid...</p>
          </div>
        </div>
      ) : (
        <div className="flex flex-col flex-1 overflow-hidden">
          {/* Asks (reversed: lowest ask at bottom near spread) */}
          <div className="overflow-y-auto flex flex-col justify-end" style={{ height: halfHeight }}>
            {[...asksWithCum].reverse().map((ask, idx) => (
              <Row
                key={`a-${idx}`}
                price={ask.px}
                size={ask.sz}
                cumulative={ask.cum}
                maxSize={maxSize}
                side="ask"
              />
            ))}
          </div>

          {/* Spread + Last Price */}
          <div className="flex items-center justify-between px-3 py-1.5 border-y border-gray-800 bg-gray-900/60 shrink-0">
            <div className="flex items-center gap-2">
              <span className={`text-[13px] font-bold font-mono ${isPositive ? 'text-green-400' : 'text-red-400'}`}>
                {lastPrice != null ? fmtPrice(lastPrice) : '—'}
              </span>
              {isPositive ? (
                <svg width="10" height="10" viewBox="0 0 10 10" className="text-green-400">
                  <path d="M5 1 L9 7 L1 7 Z" fill="currentColor" />
                </svg>
              ) : (
                <svg width="10" height="10" viewBox="0 0 10 10" className="text-red-400">
                  <path d="M5 9 L9 3 L1 3 Z" fill="currentColor" />
                </svg>
              )}
            </div>
            <div className="text-[10px] text-gray-500 font-mono">
              <span className="text-gray-600">Spd </span>
              <span className="text-yellow-400/80">{fmtPrice(safeSpread)}</span>
              <span className="text-gray-700 ml-1">({safeSpreadPct.toFixed(3)}%)</span>
            </div>
          </div>

          {/* Bids */}
          <div className="overflow-y-auto" style={{ height: halfHeight }}>
            {bidsWithCum.map((bid, idx) => (
              <Row
                key={`b-${idx}`}
                price={bid.px}
                size={bid.sz}
                cumulative={bid.cum}
                maxSize={maxSize}
                side="bid"
              />
            ))}
          </div>

          {/* Imbalance bar */}
          <div className="px-3 py-2 border-t border-gray-800 shrink-0">
            <div className="flex items-center justify-between text-[10px] mb-1">
              <span className="text-green-400/70">B {bidPct}%</span>
              <span className="text-red-400/70">S {100 - bidPct}%</span>
            </div>
            <div className="w-full h-1 bg-gray-800 rounded-full overflow-hidden flex">
              <div className="h-full bg-green-500/80 transition-all duration-500" style={{ width: `${bidPct}%` }} />
              <div className="h-full bg-red-500/80 transition-all duration-500" style={{ width: `${100 - bidPct}%` }} />
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

function Row({ price, size, cumulative, maxSize, side }) {
  const isBid = side === 'bid'
  const sz = safeNumLocal(size)
  const depthPct = maxSize > 0 ? Math.min((sz / maxSize) * 100, 100) : 0

  return (
    <div className="relative grid grid-cols-3 py-[1.5px] px-3 text-[11px] font-mono hover:bg-white/[0.03] transition-colors">
      <div
        className={`absolute right-0 top-0 bottom-0 pointer-events-none transition-all duration-300 ${
          isBid ? 'bg-green-500/[0.12]' : 'bg-red-500/[0.12]'
        }`}
        style={{ width: `${depthPct}%` }}
      />
      <span className={`relative z-10 ${isBid ? 'text-green-400' : 'text-red-400'}`}>
        {fmtPrice(price)}
      </span>
      <span className="text-gray-300 text-right relative z-10">
        {fmtSize(size)}
      </span>
      <span className="text-gray-500 text-right relative z-10">
        {fmtSize(cumulative)}
      </span>
    </div>
  )
}

function safeNumLocal(v) {
  if (v == null || isNaN(v)) return 0
  return Number(v)
}