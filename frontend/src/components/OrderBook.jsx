import React, { useState, useEffect, useCallback, useRef } from 'react'

const DEFAULT_COINS = ['BTC', 'ETH', 'SOL', 'BNB', 'XRP']

export default function OrderBook({ tradingPairs }) {
  const coins = tradingPairs && tradingPairs.length > 0 ? tradingPairs : DEFAULT_COINS
  const [selectedCoin, setSelectedCoin] = useState(coins[0])
  const [bids, setBids] = useState([])
  const [asks, setAsks] = useState([])
  const [spread, setSpread] = useState(0)
  const [spreadPct, setSpreadPct] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const mountedRef = useRef(true)

  const fetchOrderBook = useCallback(async () => {
    try {
      const headers = {}
      if (typeof window !== 'undefined' && window.__DASHBOARD_API_KEY__) {
        headers['X-API-Key'] = window.__DASHBOARD_API_KEY__
      }
      const response = await fetch(`/api/orderbook?coin=${selectedCoin}`, { headers })
      if (!response.ok) throw new Error(`HTTP ${response.status}`)
      const data = await response.json()

      if (mountedRef.current) {
        setBids(data.bids || [])
        setAsks(data.asks || [])
        setSpread(data.spread || 0)
        setSpreadPct(data.spread_pct || 0)
        setError(null)
      }
    } catch (err) {
      if (mountedRef.current) {
        setError(err.message)
      }
    } finally {
      if (mountedRef.current) setLoading(false)
    }
  }, [selectedCoin])

  useEffect(() => {
    mountedRef.current = true
    setLoading(true)
    fetchOrderBook()
    const timer = setInterval(fetchOrderBook, 5000)
    return () => {
      mountedRef.current = false
      clearInterval(timer)
    }
  }, [fetchOrderBook])

  // Calculate max size for depth bars
  const maxBidSize = bids.length > 0 ? Math.max(...bids.map(b => b.size)) : 1
  const maxAskSize = asks.length > 0 ? Math.max(...asks.map(a => a.size)) : 1
  const maxSize = Math.max(maxBidSize, maxAskSize)

  // Calculate cumulative sizes
  let bidCumulative = 0
  const bidsWithCum = bids.map(b => {
    bidCumulative += b.size
    return { ...b, cumulative: bidCumulative }
  })

  let askCumulative = 0
  const asksWithCum = asks.map(a => {
    askCumulative += a.size
    return { ...a, cumulative: askCumulative }
  })

  const totalBidSize = bidCumulative
  const totalAskSize = askCumulative
  const bidAskRatio = totalBidSize + totalAskSize > 0
    ? ((totalBidSize / (totalBidSize + totalAskSize)) * 100).toFixed(0)
    : 50

  const formatPrice = (price) => {
    if (price >= 1000) return price.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })
    if (price >= 1) return price.toFixed(4)
    return price.toFixed(6)
  }

  const formatSize = (size) => {
    if (size >= 1000) return `${(size / 1000).toFixed(1)}k`
    if (size >= 1) return size.toFixed(3)
    return size.toFixed(6)
  }

  return (
    <div className="bg-gray-900 rounded-xl p-6 border border-gray-800">
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-lg font-semibold">Order Book</h3>
        <select
          value={selectedCoin}
          onChange={(e) => setSelectedCoin(e.target.value)}
          className="bg-gray-800 border border-gray-700 rounded-lg px-3 py-1.5 text-sm text-white focus:outline-none focus:border-blue-500"
        >
          {coins.map(c => (
            <option key={c} value={c}>{c}</option>
          ))}
        </select>
      </div>

      {loading && bids.length === 0 ? (
        <div className="flex items-center justify-center py-12 text-gray-500">
          <div className="text-center">
            <div className="text-3xl mb-2 animate-pulse">📖</div>
            <p className="text-sm">Loading order book...</p>
          </div>
        </div>
      ) : error && bids.length === 0 ? (
        <div className="flex items-center justify-center py-12 text-gray-500">
          <div className="text-center">
            <div className="text-3xl mb-2">⚠️</div>
            <p className="text-sm">Failed to load order book</p>
            <p className="text-xs text-gray-600 mt-1">Start the API server</p>
          </div>
        </div>
      ) : (
        <>
          {/* Column headers */}
          <div className="grid grid-cols-3 text-[10px] text-gray-500 uppercase tracking-wider mb-1 px-1">
            <span>Price</span>
            <span className="text-right">Size</span>
            <span className="text-right">Total</span>
          </div>

          {/* Asks (reversed so lowest ask is at bottom) */}
          <div className="space-y-0 mb-1 max-h-[200px] overflow-y-auto">
            {[...asksWithCum].reverse().map((ask, idx) => (
              <div key={`ask-${idx}`} className="relative grid grid-cols-3 py-0.5 px-1 text-xs font-mono hover:bg-red-900/10 transition-colors">
                <div
                  className="absolute right-0 top-0 bottom-0 bg-red-500/10"
                  style={{ width: `${(ask.size / maxSize) * 100}%` }}
                />
                <span className="text-red-400 relative z-10">{formatPrice(ask.price)}</span>
                <span className="text-gray-300 text-right relative z-10">{formatSize(ask.size)}</span>
                <span className="text-gray-500 text-right relative z-10">{formatSize(ask.cumulative)}</span>
              </div>
            ))}
          </div>

          {/* Spread indicator */}
          <div className="flex items-center justify-center gap-3 py-2 my-1 border-y border-gray-800">
            <span className="text-xs text-gray-500">Spread</span>
            <span className="text-sm font-bold font-mono text-yellow-400">
              ${formatPrice(spread)}
            </span>
            <span className="text-[10px] text-gray-500">
              ({spreadPct.toFixed(3)}%)
            </span>
          </div>

          {/* Bids */}
          <div className="space-y-0 mt-1 max-h-[200px] overflow-y-auto">
            {bidsWithCum.map((bid, idx) => (
              <div key={`bid-${idx}`} className="relative grid grid-cols-3 py-0.5 px-1 text-xs font-mono hover:bg-green-900/10 transition-colors">
                <div
                  className="absolute left-0 top-0 bottom-0 bg-green-500/10"
                  style={{ width: `${(bid.size / maxSize) * 100}%` }}
                />
                <span className="text-green-400 relative z-10">{formatPrice(bid.price)}</span>
                <span className="text-gray-300 text-right relative z-10">{formatSize(bid.size)}</span>
                <span className="text-gray-500 text-right relative z-10">{formatSize(bid.cumulative)}</span>
              </div>
            ))}
          </div>

          {/* Bid/Ask ratio bar */}
          <div className="mt-3 pt-3 border-t border-gray-800">
            <div className="flex items-center justify-between text-[10px] text-gray-500 mb-1">
              <span>Bids {bidAskRatio}%</span>
              <span>Asks {100 - parseInt(bidAskRatio)}%</span>
            </div>
            <div className="w-full h-1.5 bg-gray-800 rounded-full overflow-hidden flex">
              <div
                className="h-full bg-green-500 rounded-l-full transition-all duration-500"
                style={{ width: `${bidAskRatio}%` }}
              />
              <div
                className="h-full bg-red-500 rounded-r-full transition-all duration-500"
                style={{ width: `${100 - parseInt(bidAskRatio)}%` }}
              />
            </div>
          </div>
        </>
      )}
    </div>
  )
}