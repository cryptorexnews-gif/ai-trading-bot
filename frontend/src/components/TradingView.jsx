import React, { useState, useEffect, useCallback, useRef, useMemo } from 'react'
import { createChart, ColorType, CrosshairMode, LineStyle } from 'lightweight-charts'

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

/* ─── Price formatting ────────────────────────────────────────────────────── */
function fmtPrice(p) {
  if (p >= 10000) return p.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })
  if (p >= 100) return p.toFixed(2)
  if (p >= 1) return p.toFixed(4)
  if (p >= 0.01) return p.toFixed(5)
  return p.toFixed(8)
}

function fmtSize(s) {
  if (s >= 1000000) return `${(s / 1000000).toFixed(2)}M`
  if (s >= 1000) return `${(s / 1000).toFixed(1)}k`
  if (s >= 1) return s.toFixed(3)
  return s.toFixed(6)
}

function fmtVol(v) {
  if (v >= 1e9) return `$${(v / 1e9).toFixed(2)}B`
  if (v >= 1e6) return `$${(v / 1e6).toFixed(2)}M`
  if (v >= 1e3) return `$${(v / 1e3).toFixed(1)}K`
  return `$${v.toFixed(0)}`
}

/* ─── Candlestick Chart Component ─────────────────────────────────────────── */
function CandlestickChart({ candles, isPositive, height = 460 }) {
  const chartContainerRef = useRef(null)
  const chartRef = useRef(null)
  const candleSeriesRef = useRef(null)
  const volumeSeriesRef = useRef(null)

  useEffect(() => {
    if (!chartContainerRef.current) return

    const chart = createChart(chartContainerRef.current, {
      width: chartContainerRef.current.clientWidth,
      height: height,
      layout: {
        background: { type: ColorType.Solid, color: 'transparent' },
        textColor: '#6b7280',
        fontSize: 11,
      },
      grid: {
        vertLines: { color: '#1f293720' },
        horzLines: { color: '#1f293740' },
      },
      crosshair: {
        mode: CrosshairMode.Normal,
        vertLine: {
          color: '#6b728050',
          width: 1,
          style: LineStyle.Dashed,
          labelBackgroundColor: '#374151',
        },
        horzLine: {
          color: '#6b728050',
          width: 1,
          style: LineStyle.Dashed,
          labelBackgroundColor: '#374151',
        },
      },
      rightPriceScale: {
        borderColor: '#1f2937',
        scaleMargins: { top: 0.1, bottom: 0.25 },
      },
      timeScale: {
        borderColor: '#1f2937',
        timeVisible: true,
        secondsVisible: false,
      },
      handleScroll: { vertTouchDrag: false },
    })

    // Candlestick series
    const candleSeries = chart.addCandlestickSeries({
      upColor: '#10b981',
      downColor: '#ef4444',
      borderUpColor: '#10b981',
      borderDownColor: '#ef4444',
      wickUpColor: '#10b98180',
      wickDownColor: '#ef444480',
    })

    // Volume series
    const volumeSeries = chart.addHistogramSeries({
      priceFormat: { type: 'volume' },
      priceScaleId: 'volume',
      scaleMargins: { top: 0.8, bottom: 0 },
    })

    chart.priceScale('volume').applyOptions({
      scaleMargins: { top: 0.8, bottom: 0 },
    })

    chartRef.current = chart
    candleSeriesRef.current = candleSeries
    volumeSeriesRef.current = volumeSeries

    // Resize observer
    const resizeObserver = new ResizeObserver((entries) => {
      for (const entry of entries) {
        chart.applyOptions({ width: entry.contentRect.width })
      }
    })
    resizeObserver.observe(chartContainerRef.current)

    return () => {
      resizeObserver.disconnect()
      chart.remove()
      chartRef.current = null
      candleSeriesRef.current = null
      volumeSeriesRef.current = null
    }
  }, [height])

  // Update data
  useEffect(() => {
    if (!candleSeriesRef.current || !volumeSeriesRef.current || !candles || candles.length === 0) return

    const candleData = candles.map(c => ({
      time: Math.floor(c.time / 1000),
      open: c.open,
      high: c.high,
      low: c.low,
      close: c.close,
    }))

    const volumeData = candles.map(c => ({
      time: Math.floor(c.time / 1000),
      value: c.volume,
      color: c.close >= c.open ? '#10b98130' : '#ef444430',
    }))

    candleSeriesRef.current.setData(candleData)
    volumeSeriesRef.current.setData(volumeData)

    // Auto-fit
    if (chartRef.current) {
      chartRef.current.timeScale().fitContent()
    }
  }, [candles])

  return <div ref={chartContainerRef} className="w-full" />
}

/* ─── Order Book Row with Flash ───────────────────────────────────────────── */
function OrderBookRow({ price, size, cumulative, maxSize, side, prevSize }) {
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
      {/* Depth bar */}
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

/* ─── Main TradingView Component ──────────────────────────────────────────── */
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
  const [stats24h, setStats24h] = useState(null)
  const [obLevels, setObLevels] = useState(15)
  const mountedRef = useRef(true)
  const prevBidsRef = useRef({})
  const prevAsksRef = useRef({})

  // ─── Fetch candles ─────────────────────────────────────────────────────
  const fetchCandles = useCallback(async () => {
    try {
      const res = await fetch(`/api/candles?coin=${selectedCoin}&interval=${interval}&limit=150`, { headers: getHeaders() })
      if (!res.ok) return
      const data = await res.json()
      if (!mountedRef.current || !data.candles) return

      setCandles(data.candles)
      if (data.candles.length > 0) {
        const last = data.candles[data.candles.length - 1]
        setLastPrice(last.close)

        // Calculate 24h stats
        const high24h = Math.max(...data.candles.map(c => c.high))
        const low24h = Math.min(...data.candles.map(c => c.low))
        const vol24h = data.candles.reduce((sum, c) => sum + c.volume, 0)
        const firstOpen = data.candles[0].open
        const change24h = firstOpen > 0 ? ((last.close - firstOpen) / firstOpen) * 100 : 0

        setStats24h({
          high: high24h,
          low: low24h,
          volume: vol24h * last.close,
          change: change24h,
          open: last.open,
          close: last.close,
        })
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

      // Store previous sizes for flash detection
      const newPrevBids = {}
      const newPrevAsks = {}
      bids.forEach(b => { newPrevBids[b.price] = b.size })
      asks.forEach(a => { newPrevAsks[a.price] = a.size })
      prevBidsRef.current = newPrevBids
      prevAsksRef.current = newPrevAsks

      setBids(data.bids || [])
      setAsks(data.asks || [])
      setSpread(data.spread || 0)
      setSpreadPct(data.spread_pct || 0)
      setObLoading(false)
    } catch { setObLoading(false) }
  }, [selectedCoin, bids, asks])

  useEffect(() => {
    mountedRef.current = true
    setChartLoading(true)
    setObLoading(true)
    fetchCandles()
    fetchOrderBook()
    const chartTimer = window.setInterval(fetchCandles, 30000)
    const obTimer = window.setInterval(fetchOrderBook, 2000)
    return () => {
      mountedRef.current = false
      window.clearInterval(chartTimer)
      window.clearInterval(obTimer)
    }
  }, [selectedCoin, interval])

  // ─── Derived values ────────────────────────────────────────────────────
  const isPositive = stats24h ? stats24h.change >= 0 : true

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
    <div className="bg-gray-900 rounded-xl border border-gray-800 overflow-hidden">
      {/* ─── Top Bar ─── */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between px-4 py-3 border-b border-gray-800 gap-2">
        <div className="flex items-center gap-3 flex-wrap">
          <select
            value={selectedCoin}
            onChange={(e) => setSelectedCoin(e.target.value)}
            className="bg-gray-800 border border-gray-700 rounded-lg px-3 py-1.5 text-sm font-bold text-white focus:outline-none focus:border-blue-500"
          >
            {coins.map(c => <option key={c} value={c}>{c}/USDC</option>)}
          </select>

          {lastPrice && (
            <span className={`text-xl font-bold font-mono ${isPositive ? 'text-green-400' : 'text-red-400'}`}>
              ${fmtPrice(lastPrice)}
            </span>
          )}
          {stats24h && (
            <span className={`text-sm font-bold ${isPositive ? 'text-green-400' : 'text-red-400'}`}>
              {isPositive ? '+' : ''}{stats24h.change.toFixed(2)}%
            </span>
          )}
        </div>

        <div className="flex items-center gap-2">
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
      </div>

      {/* ─── 24h Stats Bar ─── */}
      {stats24h && (
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
      )}

      {/* ─── Main Content: Chart + Order Book ─── */}
      <div className="flex flex-col lg:flex-row">
        {/* Chart */}
        <div className="flex-1 min-w-0">
          {chartLoading && candles.length === 0 ? (
            <div className="flex items-center justify-center h-[460px] text-gray-500">
              <div className="text-center">
                <div className="w-full h-[300px] mx-auto flex flex-col gap-2 p-6">
                  {[...Array(8)].map((_, i) => (
                    <div key={i} className="h-4 bg-gray-800 rounded animate-pulse" style={{ width: `${60 + Math.random() * 40}%` }} />
                  ))}
                </div>
                <p className="text-sm text-gray-600">Loading {selectedCoin} chart...</p>
              </div>
            </div>
          ) : candles.length === 0 ? (
            <div className="flex items-center justify-center h-[460px] text-gray-500">
              <div className="text-center">
                <div className="text-3xl mb-2">⚠️</div>
                <p className="text-sm">No chart data</p>
                <p className="text-xs text-gray-600 mt-1">Start API server: <code className="bg-gray-800 px-1 rounded">python api_server.py</code></p>
              </div>
            </div>
          ) : (
            <CandlestickChart candles={candles} isPositive={isPositive} height={460} />
          )}
        </div>

        {/* Order Book */}
        <div className="w-full lg:w-[290px] border-t lg:border-t-0 lg:border-l border-gray-800 flex flex-col">
          {/* OB Header */}
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

          {obLoading && bids.length === 0 ? (
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
                    prevSize={prevAsksRef.current[ask.price]}
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
                    prevSize={prevBidsRef.current[bid.price]}
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
      </div>
    </div>
  )
}