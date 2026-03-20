import React, { useMemo } from 'react'
import { fmtPrice, fmtSize } from './formatters'

const SIG_FIG_OPTIONS = [
  { value: 2, label: '2' },
  { value: 3, label: '3' },
  { value: 4, label: '4' },
  { value: 5, label: '5' },
]

function num(v) {
  if (v == null) return 0
  const n = Number(v)
  return isNaN(n) ? 0 : n
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

  // Parse and accumulate bids
  const bidsRows = useMemo(() => {
    let cum = 0
    return safeBids.map(b => {
      const px = num(b.px)
      const sz = num(b.sz)
      cum += sz
      return { px, sz, cum }
    })
  }, [safeBids])

  // Parse and accumulate asks
  const asksRows = useMemo(() => {
    let cum = 0
    return safeAsks.map(a => {
      const px = num(a.px)
      const sz = num(a.sz)
      cum += sz
      return { px, sz, cum }
    })
  }, [safeAsks])

  // Max size for depth bar scaling
  const maxSize = useMemo(() => {
    const allSizes = [
      ...bidsRows.map(b => b.sz),
      ...asksRows.map(a => a.sz),
    ]
    return allSizes.length > 0 ? Math.max(...allSizes, 0.0001) : 0.0001
  }, [bidsRows, asksRows])

  // Imbalance
  const totalBid = bidsRows.length > 0 ? bidsRows[bidsRows.length - 1].cum : 0
  const totalAsk = asksRows.length > 0 ? asksRows[asksRows.length - 1].cum : 0
  const total = totalBid + totalAsk
  const bidPct = total > 0 ? Math.round((totalBid / total) * 100) : 50

  // Layout heights
  const overhead = 140
  const half = Math.max(60, Math.floor((panelHeight - overhead) / 2))

  const isEmpty = safeBids.length === 0 && safeAsks.length === 0

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

      {loading && isEmpty ? (
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
          {/* ─── Asks (reversed so lowest ask is at bottom near spread) ─── */}
          <div className="overflow-hidden flex flex-col justify-end" style={{ height: half }}>
            {[...asksRows].reverse().map((row, i) => (
              <OBRow key={`a${i}`} px={row.px} sz={row.sz} cum={row.cum} maxSize={maxSize} side="ask" />
            ))}
          </div>

          {/* ─── Spread bar ─── */}
          <div className="flex items-center justify-between px-3 py-1.5 border-y border-gray-800 bg-gray-900/60 shrink-0">
            <div className="flex items-center gap-2">
              <span className={`text-[13px] font-bold font-mono ${isPositive ? 'text-green-400' : 'text-red-400'}`}>
                {lastPrice != null && lastPrice !== 0 ? fmtPrice(lastPrice) : '—'}
              </span>
              {isPositive ? (
                <svg width="10" height="10" viewBox="0 0 10 10" className="text-green-400"><path d="M5 1 L9 7 L1 7 Z" fill="currentColor" /></svg>
              ) : (
                <svg width="10" height="10" viewBox="0 0 10 10" className="text-red-400"><path d="M5 9 L9 3 L1 3 Z" fill="currentColor" /></svg>
              )}
            </div>
            <div className="text-[10px] text-gray-500 font-mono">
              <span className="text-gray-600">Spd </span>
              <span className="text-yellow-400/80">{num(spread) > 0 ? fmtPrice(num(spread)) : '—'}</span>
              <span className="text-gray-700 ml-1">({num(spreadPct).toFixed(3)}%)</span>
            </div>
          </div>

          {/* ─── Bids (no scrollbar) ─── */}
          <div className="overflow-hidden" style={{ height: half }}>
            {bidsRows.map((row, i) => (
              <OBRow key={`b${i}`} px={row.px} sz={row.sz} cum={row.cum} maxSize={maxSize} side="bid" />
            ))}
          </div>

          {/* ─── Imbalance bar ─── */}
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

/* ─── Single order book row ─── */
function OBRow({ px, sz, cum, maxSize, side }) {
  const isBid = side === 'bid'
  const depthPct = maxSize > 0 ? Math.min((sz / maxSize) * 100, 100) : 0

  return (
    <div className="relative grid grid-cols-3 py-[1.5px] px-3 text-[11px] font-mono hover:bg-white/[0.03] transition-colors">
      {/* Depth bar */}
      <div
        className={`absolute right-0 top-0 bottom-0 pointer-events-none ${
          isBid ? 'bg-green-500/[0.12]' : 'bg-red-500/[0.12]'
        }`}
        style={{ width: `${depthPct}%` }}
      />
      <span className={`relative z-10 ${isBid ? 'text-green-400' : 'text-red-400'}`}>
        {fmtPrice(px)}
      </span>
      <span className="text-gray-300 text-right relative z-10">
        {fmtSize(sz)}
      </span>
      <span className="text-gray-500 text-right relative z-10">
        {fmtSize(cum)}
      </span>
    </div>
  )
}