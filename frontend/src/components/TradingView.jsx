import React, { useState, useEffect, useCallback, useRef } from 'react'
import { getHeaders } from './trading/formatters'
import ChartToolbar from './trading/ChartToolbar'
import StatsBar from './trading/StatsBar'
import CandlestickChart from './trading/CandlestickChart'
import OrderBookPanel from './trading/OrderBookPanel'

const DEFAULT_COINS = ['BTC', 'ETH', 'SOL', 'BNB', 'XRP', 'ADA', 'DOGE', 'AVAX', 'LINK', 'SUI']
const PANEL_HEIGHT = 520
const HYPERLIQUID_INFO_URL = 'https://api.hyperliquid.xyz/info'

function safeNum(v, fallback = 0) {
  if (v == null || isNaN(v)) return fallback
  return v
}

async function fetchFromHyperliquid(payload) {
  const res = await fetch(HYPERLIQUID_INFO_URL, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!res.ok) return null
  return res.json()
}

export default function TradingView({ tradingPairs }) {
  const coins = tradingPairs && tradingPairs.length > 0 ? tradingPairs : DEFAULT_COINS
  const [selectedCoin, setSelectedCoin] = useState(coins[0])
  const [interval, setInterval_] = useState('1h')
  const [candles, setCandles] = useState([])
  const [bids, setBids] = useState([])
  const [asks, setAsks] = useState([])
  const [spread, setSpread] = useState(0)
  const [spreadPct, setSpreadPct] = useState(0)
  const [nSigFigs, setNSigFigs] = useState(5)
  const [chartLoading, setChartLoading] = useState(true)
  const [obLoading, setObLoading] = useState(true)
  const [lastPrice, setLastPrice] = useState(null)
  const [stats24h, setStats24h] = useState(null)
  const mountedRef = useRef(true)
  const obErrorLoggedRef = useRef(false)

  // ─── Fetch candles ─────────────────────────────────────────────────────
  const fetchCandles = useCallback(async () => {
    let candleData = null

    // Try proxy
    try {
      const res = await fetch(
        `/api/candles?coin=${selectedCoin}&interval=${interval}&limit=150`,
        { headers: getHeaders() }
      )
      if (res.ok) {
        const json = await res.json()
        if (json.candles && json.candles.length > 0) {
          candleData = json.candles
        }
      }
    } catch { /* proxy down */ }

    // Fallback: direct Hyperliquid
    if (!candleData) {
      try {
        const now = Date.now()
        const msMap = { '1m': 60000, '5m': 300000, '15m': 900000, '1h': 3600000, '4h': 14400000, '1d': 86400000 }
        const ms = msMap[interval] || 900000
        const raw = await fetchFromHyperliquid({
          type: 'candleSnapshot',
          req: { coin: selectedCoin, interval, startTime: now - ms * 150, endTime: now }
        })
        if (Array.isArray(raw) && raw.length > 0) {
          candleData = raw.map(c => ({
            time: c.t || 0,
            open: parseFloat(c.o || 0),
            high: parseFloat(c.h || 0),
            low: parseFloat(c.l || 0),
            close: parseFloat(c.c || 0),
            volume: parseFloat(c.v || 0),
          }))
        }
      } catch { /* direct failed */ }
    }

    if (!mountedRef.current) return
    if (!candleData || candleData.length === 0) {
      setChartLoading(false)
      return
    }

    setCandles(candleData)
    const last = candleData[candleData.length - 1]
    const first = candleData[0]
    setLastPrice(safeNum(last.close, null))

    const high = Math.max(...candleData.map(c => safeNum(c.high, 0)))
    const lowVals = candleData.filter(c => safeNum(c.low, 0) > 0).map(c => c.low)
    const low = lowVals.length > 0 ? Math.min(...lowVals) : 0
    const vol = candleData.reduce((s, c) => s + safeNum(c.volume, 0), 0) * safeNum(last.close, 0)
    const openP = safeNum(first.open, 0)
    const closeP = safeNum(last.close, 0)
    const chg = openP > 0 ? ((closeP - openP) / openP) * 100 : 0

    setStats24h({
      high: safeNum(high, 0),
      low: safeNum(low, 0),
      volume: safeNum(vol, 0),
      change: safeNum(chg, 0),
      open: openP,
      close: closeP,
    })
    setChartLoading(false)
  }, [selectedCoin, interval])

  // ─── Fetch order book ──────────────────────────────────────────────────
  const fetchOrderBook = useCallback(async () => {
    let parsedBids = []
    let parsedAsks = []
    let calcSpread = 0
    let calcSpreadPct = 0

    // Helper to parse Hyperliquid L2 levels
    const parseLevels = (rawLevels) => {
      if (!rawLevels || !Array.isArray(rawLevels)) return []
      return rawLevels
        .map(l => ({
          px: parseFloat(l.px || 0),
          sz: parseFloat(l.sz || 0),
          n: parseInt(l.n || 0),
        }))
        .filter(l => l.sz > 0 && l.px > 0)
    }

    // Try proxy first
    try {
      const res = await fetch(
        `/api/orderbook?coin=${selectedCoin}&nSigFigs=${nSigFigs}`,
        { headers: getHeaders() }
      )
      if (res.ok) {
        const data = await res.json()
        if (data.bids && data.bids.length > 0) {
          parsedBids = data.bids
          parsedAsks = data.asks || []
          calcSpread = safeNum(data.spread, 0)
          calcSpreadPct = safeNum(data.spread_pct, 0)
        }
      }
    } catch { /* proxy unavailable */ }

    // Fallback: direct Hyperliquid
    if (parsedBids.length === 0) {
      try {
        const raw = await fetchFromHyperliquid({
          type: 'l2Book',
          coin: selectedCoin,
          nSigFigs: nSigFigs,
        })

        if (raw && raw.levels && Array.isArray(raw.levels)) {
          parsedBids = parseLevels(raw.levels[0])
          parsedAsks = parseLevels(raw.levels[1])

          if (parsedBids.length > 0 && parsedAsks.length > 0) {
            const bestBid = parsedBids[0].px
            const bestAsk = parsedAsks[0].px
            calcSpread = bestAsk - bestBid
            const mid = (bestAsk + bestBid) / 2
            calcSpreadPct = mid > 0 ? (calcSpread / mid) * 100 : 0
          }

          if (!obErrorLoggedRef.current && parsedBids.length > 0) {
            console.log(`[OrderBook] Direct fetch OK: ${parsedBids.length} bids, ${parsedAsks.length} asks`)
            obErrorLoggedRef.current = true
          }
        }
      } catch (err) {
        if (!obErrorLoggedRef.current) {
          console.warn('[OrderBook] Both proxy and direct fetch failed:', err.message)
          obErrorLoggedRef.current = true
        }
      }
    }

    if (!mountedRef.current) return

    setBids(parsedBids)
    setAsks(parsedAsks)
    setSpread(calcSpread)
    setSpreadPct(calcSpreadPct)
    setObLoading(false)
  }, [selectedCoin, nSigFigs])

  // ─── Reset on coin/interval change + start polling ─────────────────────
  useEffect(() => {
    mountedRef.current = true
    obErrorLoggedRef.current = false
    setChartLoading(true)
    setObLoading(true)
    setCandles([])
    setBids([])
    setAsks([])
    setStats24h(null)
    setLastPrice(null)

    fetchCandles()
    fetchOrderBook()

    const chartTimer = window.setInterval(fetchCandles, 30000)
    const obTimer = window.setInterval(fetchOrderBook, 2000)

    return () => {
      mountedRef.current = false
      window.clearInterval(chartTimer)
      window.clearInterval(obTimer)
    }
  }, [fetchCandles, fetchOrderBook])

  const change = stats24h ? safeNum(stats24h.change, 0) : 0
  const isPositive = change >= 0
  const changePct = stats24h ? change.toFixed(2) : null

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
        {/* Chart */}
        <div className="flex-1 min-w-0">
          {chartLoading && candles.length === 0 ? (
            <div className="flex items-center justify-center text-gray-500" style={{ height: PANEL_HEIGHT }}>
              <div className="text-center">
                <div className="w-full h-[300px] mx-auto flex flex-col gap-2 p-6">
                  {[...Array(8)].map((_, i) => (
                    <div
                      key={i}
                      className="h-4 bg-gray-800 rounded animate-pulse"
                      style={{ width: `${60 + Math.random() * 40}%` }}
                    />
                  ))}
                </div>
                <p className="text-sm text-gray-600">Loading {selectedCoin} chart...</p>
              </div>
            </div>
          ) : candles.length === 0 ? (
            <div className="flex items-center justify-center text-gray-500" style={{ height: PANEL_HEIGHT }}>
              <div className="text-center">
                <div className="text-3xl mb-2">📊</div>
                <p className="text-sm">No chart data available</p>
                <p className="text-xs text-gray-600 mt-1">Check your internet connection</p>
              </div>
            </div>
          ) : (
            <CandlestickChart candles={candles} height={PANEL_HEIGHT} />
          )}
        </div>

        {/* Order Book */}
        <OrderBookPanel
          bids={bids}
          asks={asks}
          spread={spread}
          spreadPct={spreadPct}
          lastPrice={lastPrice}
          isPositive={isPositive}
          nSigFigs={nSigFigs}
          setNSigFigs={setNSigFigs}
          loading={obLoading}
          panelHeight={PANEL_HEIGHT}
        />
      </div>
    </div>
  )
}