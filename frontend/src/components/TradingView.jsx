import React, { useState, useEffect, useCallback, useRef, useMemo } from 'react'
import { getHeaders } from './trading/formatters'
import ChartToolbar from './trading/ChartToolbar'
import StatsBar from './trading/StatsBar'
import CandlestickChart from './trading/CandlestickChart'
import OrderBookPanel from './trading/OrderBookPanel'

const DEFAULT_COINS = ['BTC', 'ETH', 'SOL', 'BNB', 'XRP', 'ADA', 'DOGE', 'AVAX', 'LINK', 'SUI']

// Shared height for chart and order book
const PANEL_HEIGHT = 520

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
  const [obLevels, setObLevels] = useState(25)
  const [tickSize, setTickSize] = useState(0)
  const mountedRef = useRef(true)
  const prevBidsRef = useRef({})
  const prevAsksRef = useRef({})

  // Compute tick size options based on current price
  const tickOptions = useMemo(() => {
    if (!lastPrice || lastPrice <= 0) return [0, 1, 10, 100]
    if (lastPrice >= 10000) return [0, 1, 10, 50, 100]
    if (lastPrice >= 1000) return [0, 1, 5, 10, 50]
    if (lastPrice >= 100) return [0, 0.5, 1, 5, 10]
    if (lastPrice >= 10) return [0, 0.1, 0.5, 1, 5]
    if (lastPrice >= 1) return [0, 0.01, 0.1, 0.5, 1]
    if (lastPrice >= 0.01) return [0, 0.001, 0.01, 0.1]
    return [0, 0.0001, 0.001, 0.01]
  }, [lastPrice])

  // Reset tick size when coin changes
  useEffect(() => {
    setTickSize(0)
  }, [selectedCoin])

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
        setStats24h({
          high: Math.max(...data.candles.map(c => c.high)),
          low: Math.min(...data.candles.map(c => c.low)),
          volume: data.candles.reduce((sum, c) => sum + c.volume, 0) * last.close,
          change: data.candles[0].open > 0 ? ((last.close - data.candles[0].open) / data.candles[0].open) * 100 : 0,
          open: last.open,
          close: last.close,
        })
      }
      setChartLoading(false)
    } catch { setChartLoading(false) }
  }, [selectedCoin, interval])

  // ─── Fetch ALL order book levels ───────────────────────────────────────
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

  const isPositive = stats24h ? stats24h.change >= 0 : true
  const changePct = stats24h ? stats24h.change.toFixed(2) : null

  // Total available levels for the "All" option
  const totalBidLevels = bids.length
  const totalAskLevels = asks.length

  return (
    <div className="bg-gray-900 rounded-xl border border-gray-800 overflow-hidden">
      <ChartToolbar
        coins={coins}
        selectedCoin={selectedCoin}
        setSelectedCoin={setSelectedCoin}
        interval={interval}
        setInterval={setInterval_}
        lastPrice={lastPrice}
        isPositive={isPositive}
        changePct={changePct}
      />

      <StatsBar stats24h={stats24h} />

      <div className="flex flex-col lg:flex-row">
        {/* Chart — same height as order book */}
        <div className="flex-1 min-w-0">
          {chartLoading && candles.length === 0 ? (
            <div className="flex items-center justify-center text-gray-500" style={{ height: PANEL_HEIGHT }}>
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
            <div className="flex items-center justify-center text-gray-500" style={{ height: PANEL_HEIGHT }}>
              <div className="text-center">
                <div className="text-3xl mb-2">⚠️</div>
                <p className="text-sm">No chart data</p>
                <p className="text-xs text-gray-600 mt-1">Start API server: <code className="bg-gray-800 px-1 rounded">python api_server.py</code></p>
              </div>
            </div>
          ) : (
            <CandlestickChart candles={candles} height={PANEL_HEIGHT} />
          )}
        </div>

        {/* Order Book — same height as chart */}
        <OrderBookPanel
          bids={bids}
          asks={asks}
          spread={spread}
          spreadPct={spreadPct}
          lastPrice={lastPrice}
          isPositive={isPositive}
          obLevels={obLevels}
          setObLevels={setObLevels}
          tickSize={tickSize}
          setTickSize={setTickSize}
          tickOptions={tickOptions}
          loading={obLoading}
          prevBids={prevBidsRef.current}
          prevAsks={prevAsksRef.current}
          panelHeight={PANEL_HEIGHT}
          totalBidLevels={totalBidLevels}
          totalAskLevels={totalAskLevels}
        />
      </div>
    </div>
  )
}