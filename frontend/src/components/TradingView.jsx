import React, { useState, useEffect, useCallback, useRef } from 'react'
import {
  ComposedChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, Line, Area
} from 'recharts'

const INTERVALS = [
  { value: '5m', label: '5m' },
  { value: '15m', label: '15m' },
  { value: '1h', label: '1H' },
  { value: '4h', label: '4H' },
  { value: '1d', label: 'D' },
]

const DEFAULT_COINS = ['BTC', 'ETH', 'SOL', 'BNB', 'XRP', 'ADA', 'DOGE', 'AVAX', 'LINK', 'SUI']

function getApiKey() {
  if (typeof window !== 'undefined' && window.__DASHBOARD_API_KEY__) return window.__DASHBOARD_API_KEY__
  const meta = document.querySelector('meta[name="dashboard-api-key"]')
  return meta ? meta.getAttribute('content') : ''
}

function getHeaders() {
  const headers = {}
  const key = getApiKey()
  if (key) headers['X-API-Key'] = key
  return headers
}

/* ─── Candle Tooltip ──────────────────────────────────────────────────────── */
function CandleTooltip({ active, payload }) {
  if (!active || !payload || !payload.length) return null
  const d = payload[0].payload
  const change = d.close - d.open
  const changePct = d.open > 0 ? ((change / d.open) * 100).toFixed(2) : '0.00'
  const isGreen = change >= 0
  const fmt = (v) => v?.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })

  return (
    <div className="bg-gray-800/95 border border-gray-700 rounded-lg p-3 shadow-2xl text-xs min-w-[170px] backdrop-blur-sm">
      <div className="text-gray-400 mb-2 font-medium">{d.timeLabel}</div>
      <div className="grid grid-cols-2 gap-x-4 gap-y-1">
        <span className="text-gray-500">O</span>
        <span className="text-white text-right font-mono">${fmt(d.open)}</span>
        <span className="text-gray-500">H</span>
        <span className="text-green-400 text-right font-mono">${fmt(d.high)}</span>
        <span className="text-gray-500">L</span>
        <span className="text-red-400 text-right font-mono">${fmt(d.low)}</span>
        <span className="text-gray-500">C</span>
        <span className={`text-right font-mono font-bold ${isGreen ? 'text-green-400' : 'text-red-400'}`}>${fmt(d.close)}</span>
        <span className="text-gray-500">Chg</span>
        <span className={`text-right font-mono ${isGreen ? 'text-green-400' : 'text-red-400'}`}>{isGreen ? '+' : ''}{changePct}%</span>
        <span className="text-gray-500">Vol</span>
        <span className="text-blue-400 text-right font-mono">{d.volume?.toLocaleString(undefined, { maximumFractionDigits: 0 })}</span>
      </div>
    </div>
  )
}

/* ─── Main Component ──────────────────────────────────────────────────────── */
export default function TradingView({ tradingPairs }) {
  const coins = tradingPairs && tradingPairs.length > 0 ? tradingPairs : DEFAULT_COINS
  const [selectedCoin, setSelectedCoin] = useState(coins[0])
  const [interval, setInterval_] = useState('1h')
  const [candles, setCandles] = useState([])
  const [bids, setBids] = useState([])
  const [asks, setAsks] = useState([])
  const [spread, setSpread] = useState(0)
  const [spreadPct, setSpreadPct] = useState(0)
  const [chartLoading, setChartLoading] = useState(true)
  const [obLoading, setObLoading] = useState(true)
  const [lastPrice, setLastPrice] = useState(null)
  const [ohlc, setOhlc] = useState(null)
  const mountedRef = useRef(true)

  // ─── Fetch candles ─────────────────────────────────────────────────────
  const fetchCandles = useCallback(async () => {
    try {
      const res = await fetch(`/api/candles?coin=${selectedCoin}&interval=${interval}&limit=100`, { headers: getHeaders() })
      if (!res.ok) return
      const data = await res.json()
      if (!mountedRef.current || !data.candles) return

      const formatted = data.candles.map((c) => {
        const date = new Date(c.time)
        const timeLabel = interval === '1d'
          ? date.toLocaleDateString([], { month: 'short', day: 'numeric' })
          : date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
        return { ...c, timeLabel, isGreen: c.close >= c.open }
      })
      setCandles(formatted)
      if (formatted.length > 0) {
        const last = formatted[formatted.length - 1]
        setLastPrice(last.close)
        setOhlc(last)
      }
      setChartLoading(false)
    } catch { setChartLoading(false) }
  }, [selectedCoin, interval])

  // ─── Fetch order book ──────────────────────────────────────────────────
  const fetchOrderBook = useCallback(async () => {
    try {
      const res = await fetch(`/api/orderbook?coin=${selectedCoin}`, { headers: getHeaders() })
      if (!res.ok) return
      const data = await res.json()
      if (!mountedRef.current) return
      setBids(data.bids || [])
      setAsks(data.asks || [])
      setSpread(data.spread || 0)
      setSpreadPct(data.spread_pct || 0)
      setObLoading(false)
    } catch { setObLoading(false) }
  }, [selectedCoin])

  useEffect(() => {
    mountedRef.current = true
    setChartLoading(true)
    setObLoading(true)
    fetchCandles()
    fetchOrderBook()
    const chartTimer = window.setInterval(fetchCandles, 30000)
    const obTimer = window.setInterval(fetchOrderBook, 3000)
    return () => {
      mountedRef.current = false
      window.clearInterval(chartTimer)
      window.clearInterval(obTimer)
    }
  }, [fetchCandles, fetchOrderBook])

  // ─── Derived values ────────────────────────────────────────────────────
  const priceChange = candles.length >= 2 ? candles[candles.length - 1].close - candles[0].open : 0
  const priceChangePct = candles.length >= 2 && candles[0].open > 0 ? ((priceChange / candles[0].open) * 100).toFixed(2) : '0.00'
  const isPositive = priceChange >= 0

  const totalVolume = candles.reduce((sum, c) => sum + (c.volume || 0), 0)
  const fmtVol = (v) => v >= 1e9 ? `${(v / 1e9).toFixed(2)}B` : v >= 1e6 ? `${(v / 1e6).toFixed(2)}M` : v >= 1e3 ? `${(v / 1e3).toFixed(1)}K` : v.toFixed(0)

  // Order book calculations
  const maxBidSize = bids.length > 0 ? Math.max(...bids.map(b => b.size)) : 1
  const maxAskSize = asks.length > 0 ? Math.max(...asks.map(a => a.size)) : 1
  const maxSize = Math.max(maxBidSize, maxAskSize)

  let bidCum = 0
  const bidsWithCum = bids.map(b => { bidCum += b.size; return { ...b, cumulative: bidCum } })
  let askCum = 0
  const asksWithCum = asks.map(a => { askCum += a.size; return { ...a, cumulative: askCum } })

  const fmtPrice = (p) => {
    if (p >= 1000) return p.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })
    if (p >= 1) return p.toFixed(4)
    return p.toFixed(6)
  }
  const fmtSize = (s) => s >= 1000 ? `${(s / 1000).toFixed(1)}k` : s >= 1 ? s.toFixed(3) : s.toFixed(6)

  return (
    <div className="bg-gray-900 rounded-xl border border-gray-800 overflow-hidden">
      {/* ─── Top Bar: Coin selector + Price info + Interval ─── */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between px-4 py-3 border-b border-gray-800 gap-2">
        <div className="flex items-center gap-3 flex-wrap">
          {/* Coin selector */}
          <select
            value={selectedCoin}
            onChange={(e) => setSelectedCoin(e.target.value)}
            className="bg-gray-800 border border-gray-700 rounded-lg px-3 py-1.5 text-sm font-bold text-white focus:outline-none focus:border-blue-500"
          >
            {coins.map(c => <option key={c} value={c}>{c}/USDC</option>)}
          </select>

          {/* Price + OHLC info */}
          {lastPrice && (
            <div className="flex items-center gap-4">
              <span className={`text-xl font-bold font-mono ${isPositive ? 'text-green-400' : 'text-red-400'}`}>
                ${fmtPrice(lastPrice)}
              </span>
              <span className={`text-sm font-bold ${isPositive ? 'text-green-400' : 'text-red-400'}`}>
                {isPositive ? '+' : ''}{priceChangePct}%
              </span>
              {ohlc && (
                <div className="hidden md:flex items-center gap-3 text-[11px] text-gray-400 font-mono">
                  <span>O <span className="text-gray-300">{fmtPrice(ohlc.open)}</span></span>
                  <span>H <span className="text-green-400">{fmtPrice(ohlc.high)}</span></span>
                  <span>L <span className="text-red-400">{fmtPrice(ohlc.low)}</span></span>
                  <span>C <span className="text-white">{fmtPrice(ohlc.close)}</span></span>
                  <span>Vol <span className="text-blue-400">{fmtVol(totalVolume)}</span></span>
                </div>
              )}
            </div>
          )}
        </div>

        {/* Interval buttons */}
        <div className="flex bg-gray-800 rounded-lg border border-gray-700 overflow-hidden">
          {INTERVALS.map(i => (
            <button
              key={i.value}
              onClick={() => setInterval_(i.value)}
              className={`px-3 py-1.5 text-xs font-medium transition-colors ${
                interval === i.value
                  ? 'bg-blue-600 text-white'
                  : 'text-gray-400 hover:text-white hover:bg-gray-700'
              }`}
            >
              {i.label}
            </button>
          ))}
        </div>
      </div>

      {/* ─── Main Content: Chart (left) + Order Book (right) ─── */}
      <div className="flex flex-col lg:flex-row">
        {/* Chart */}
        <div className="flex-1 min-w-0 p-2">
          {chartLoading && candles.length === 0 ? (
            <div className="flex items-center justify-center h-[400px] text-gray-500">
              <div className="text-center">
                <div className="text-3xl mb-2 animate-pulse">📊</div>
                <p className="text-sm">Loading {selectedCoin} chart...</p>
              </div>
            </div>
          ) : candles.length === 0 ? (
            <div className="flex items-center justify-center h-[400px] text-gray-500">
              <div className="text-center">
                <div className="text-3xl mb-2">⚠️</div>
                <p className="text-sm">No chart data — start API server</p>
              </div>
            </div>
          ) : (
            <ResponsiveContainer width="100%" height={400}>
              <ComposedChart data={candles} margin={{ top: 10, right: 10, bottom: 0, left: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
                <XAxis dataKey="timeLabel" stroke="#4b5563" fontSize={10} tickLine={false} interval="preserveStartEnd" />
                <YAxis
                  stroke="#4b5563" fontSize={10} tickLine={false}
                  domain={['auto', 'auto']}
                  tickFormatter={(v) => v >= 10000 ? `$${(v / 1000).toFixed(0)}k` : v >= 100 ? `$${v.toFixed(0)}` : v >= 1 ? `$${v.toFixed(2)}` : `$${v.toFixed(4)}`}
                  width={60}
                />
                <YAxis
                  yAxisId="volume" orientation="right" stroke="#4b5563" fontSize={9} tickLine={false}
                  tickFormatter={(v) => v >= 1000 ? `${(v / 1000).toFixed(0)}k` : v.toFixed(0)}
                  width={40} domain={[0, (dataMax) => dataMax * 4]}
                />
                <Tooltip content={<CandleTooltip />} />
                {/* Volume bars — colored by direction */}
                <Bar
                  yAxisId="volume" dataKey="volume" barSize={4} stroke="none"
                  fill="#3b82f620"
                  shape={(props) => {
                    const { x, y, width, height, payload } = props
                    const color = payload.isGreen ? 'rgba(16,185,129,0.25)' : 'rgba(239,68,68,0.25)'
                    return <rect x={x} y={y} width={width} height={height} fill={color} />
                  }}
                />
                {/* Price area */}
                <Area
                  type="monotone" dataKey="close"
                  stroke={isPositive ? '#10b981' : '#ef4444'}
                  fill={isPositive ? '#10b98110' : '#ef444410'}
                  strokeWidth={2} dot={false}
                  activeDot={{ r: 4, fill: isPositive ? '#10b981' : '#ef4444', stroke: '#fff', strokeWidth: 2 }}
                />
                {/* High/Low wicks */}
                <Line type="monotone" dataKey="high" stroke="#10b98130" strokeWidth={1} strokeDasharray="2 4" dot={false} activeDot={false} />
                <Line type="monotone" dataKey="low" stroke="#ef444430" strokeWidth={1} strokeDasharray="2 4" dot={false} activeDot={false} />
              </ComposedChart>
            </ResponsiveContainer>
          )}
        </div>

        {/* Order Book */}
        <div className="w-full lg:w-[280px] border-t lg:border-t-0 lg:border-l border-gray-800 flex flex-col">
          {/* OB Header */}
          <div className="grid grid-cols-3 text-[10px] text-gray-500 uppercase tracking-wider px-3 py-2 border-b border-gray-800 bg-gray-900/50">
            <span>Price ({selectedCoin})</span>
            <span className="text-right">Size</span>
            <span className="text-right">Total</span>
          </div>

          {obLoading && bids.length === 0 ? (
            <div className="flex items-center justify-center py-12 text-gray-500 text-sm">
              <span className="animate-pulse">Loading...</span>
            </div>
          ) : (
            <div className="flex flex-col flex-1 overflow-hidden">
              {/* Asks (reversed) */}
              <div className="flex-1 overflow-y-auto max-h-[170px] flex flex-col justify-end">
                {[...asksWithCum].reverse().map((ask, idx) => (
                  <div key={`a-${idx}`} className="relative grid grid-cols-3 py-[2px] px-3 text-[11px] font-mono hover:bg-red-900/10">
                    <div className="absolute right-0 top-0 bottom-0 bg-red-500/8" style={{ width: `${(ask.size / maxSize) * 100}%` }} />
                    <span className="text-red-400 relative z-10">{fmtPrice(ask.price)}</span>
                    <span className="text-gray-300 text-right relative z-10">{fmtSize(ask.size)}</span>
                    <span className="text-gray-500 text-right relative z-10">{fmtSize(ask.cumulative)}</span>
                  </div>
                ))}
              </div>

              {/* Spread */}
              <div className="flex items-center justify-between px-3 py-1.5 border-y border-gray-800 bg-gray-800/30">
                <span className={`text-sm font-bold font-mono ${isPositive ? 'text-green-400' : 'text-red-400'}`}>
                  {lastPrice ? `$${fmtPrice(lastPrice)}` : '—'}
                </span>
                <div className="flex items-center gap-2 text-[10px] text-gray-500">
                  <span>Spread</span>
                  <span className="text-yellow-400 font-mono">{fmtPrice(spread)}</span>
                  <span className="text-gray-600">{spreadPct.toFixed(3)}%</span>
                </div>
              </div>

              {/* Bids */}
              <div className="flex-1 overflow-y-auto max-h-[170px]">
                {bidsWithCum.map((bid, idx) => (
                  <div key={`b-${idx}`} className="relative grid grid-cols-3 py-[2px] px-3 text-[11px] font-mono hover:bg-green-900/10">
                    <div className="absolute left-0 top-0 bottom-0 bg-green-500/8" style={{ width: `${(bid.size / maxSize) * 100}%` }} />
                    <span className="text-green-400 relative z-10">{fmtPrice(bid.price)}</span>
                    <span className="text-gray-300 text-right relative z-10">{fmtSize(bid.size)}</span>
                    <span className="text-gray-500 text-right relative z-10">{fmtSize(bid.cumulative)}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}