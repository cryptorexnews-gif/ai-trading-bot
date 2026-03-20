import React from 'react'

export default function OrderBook({ orderBook, coin }) {
  if (!orderBook) {
    return (
      <div className="p-4">
        <h3 className="text-sm font-semibold text-gray-400 mb-2">Order Book</h3>
        <div className="flex items-center justify-center h-64 text-gray-500">
          <div className="text-center">
            <div className="text-3xl mb-2">📊</div>
            <p className="text-xs">Loading order book...</p>
          </div>
        </div>
      </div>
    )
  }

  const { bids, asks, spread, spread_pct } = orderBook
  const bestBid = bids[0]?.px || 0
  const bestAsk = asks[0]?.px || 0

  return (
    <div className="p-4">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-semibold text-gray-400">Order Book</h3>
        <div className="flex items-center gap-2">
          <span className="text-xs text-gray-500">{coin}/USDC</span>
          <span className={`text-xs font-bold ${spread_pct > 0.1 ? 'text-red-400' : 'text-green-400'}`}>
            Spread: {spread_pct > 0 ? `${spread_pct.toFixed(2)}%` : '0.00%'}
          </span>
        </div>
      </div>

      <div className="space-y-1">
        <div className="grid grid-cols-3 text-[10px] text-gray-500 px-2">
          <span>Size</span>
          <span className="text-right">Price</span>
          <span className="text-right">Total</span>
        </div>

        {/* Asks (red) */}
        <div className="space-y-0.5">
          {asks.slice(0, 8).map((ask, i) => (
            <div key={`ask-${i}`} className="grid grid-cols-3 text-xs font-mono">
              <div className="flex items-center">
                <div 
                  className="h-1.5 bg-red-500/20 rounded-full" 
                  style={{ width: `${Math.min(100, (ask.sz / (asks[0]?.sz || 1)) * 100)}%` }}
                />
                <span className="ml-2 text-red-400">{ask.sz.toFixed(4)}</span>
              </div>
              <span className="text-right text-red-400">{ask.px.toFixed(2)}</span>
              <span className="text-right text-gray-500">{(ask.sz * ask.px / 1000).toFixed(1)}K</span>
            </div>
          ))}
        </div>

        {/* Spread highlight */}
        <div className="py-2 flex items-center justify-center gap-2">
          <span className="text-xs text-gray-500">BID</span>
          <span className="text-lg font-bold text-green-400">{bestBid.toFixed(2)}</span>
          <span className="text-xs text-gray-500">-</span>
          <span className="text-lg font-bold text-red-400">{bestAsk.toFixed(2)}</span>
          <span className="text-xs text-gray-500">ASK</span>
        </div>

        {/* Bids (green) */}
        <div className="space-y-0.5">
          {bids.slice(0, 8).map((bid, i) => (
            <div key={`bid-${i}`} className="grid grid-cols-3 text-xs font-mono">
              <div className="flex items-center">
                <div 
                  className="h-1.5 bg-green-500/20 rounded-full" 
                  style={{ width: `${Math.min(100, (bid.sz / (bids[0]?.sz || 1)) * 100)}%` }}
                />
                <span className="ml-2 text-green-400">{bid.sz.toFixed(4)}</span>
              </div>
              <span className="text-right text-green-400">{bid.px.toFixed(2)}</span>
              <span className="text-right text-gray-500">{(bid.sz * bid.px / 1000).toFixed(1)}K</span>
            </div>
          ))}
        </div>
      </div>

      <div className="mt-3 pt-2 border-t border-gray-800">
        <div className="grid grid-cols-2 gap-2 text-xs">
          <div>
            <span className="text-gray-500">Best Bid</span>
            <div className="text-green-400 font-mono">{bestBid.toFixed(2)}</div>
          </div>
          <div>
            <span className="text-gray-500">Best Ask</span>
            <div className="text-red-400 font-mono">{bestAsk.toFixed(2)}</div>
          </div>
        </div>
      </div>
    </div>
  )
}