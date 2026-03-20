import React, { useState, useEffect, useCallback, useRef } from 'react'
import { getHeaders } from '../hooks/useApi'
import ChartToolbar from './trading/ChartToolbar'
import StatsBar from './trading/StatsBar'
import CandlestickChart from './trading/CandlestickChart'
import ChartSkeleton from './trading/ChartSkeleton'

const DEFAULT_COINS = ['BTC', 'ETH', 'SOL', 'BNB', 'XRP', 'ADA', 'DOGE', 'AVAX', 'LINK', 'SUI']
const CHART_HEIGHT = 500
const HYPERLIQUID_INFO_URL = 'https://api.hyperliquid.xyz/info'

function safeNum(v, fallback = 0) {
  if (v == null || isNaN(v)) return fallback
  return Number(v)
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
  const [chartLoading, setChartLoading] = useState(true)
  const [lastPrice, setLastPrice] = useState(null)
  const [stats24h, setStats24h] = useState(null)
  const mountedRef = useRef(true)

  const fetchCandles = useCallback(async () => {
    let candleData = null

    // Try proxy first
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

  // Reset on coin/interval change + start polling
  useEffect(() => {
    mountedRef.current = true
    setChartLoading(true)
    setCandles([])
    setStats24h(null)
    setLastPrice(null)

    fetchCandles()
    const timer = window.setInterval(fetchCandles, 30000)

    return () => {
      mountedRef.current = false
      window.clearInterval(timer)
    }
  }, [fetchCandles])

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

      {chartLoading && candles.length === 0 ? (
        <ChartSkeleton height={CHART_HEIGHT} />
      ) : candles.length === 0 ? (
        <div className="flex items-center justify-center text-gray-500" style={{ height: CHART_HEIGHT }}>
          <div className="text-center">
            <div className="text-3xl mb-2">📊</div>
            <p className="text-sm">No chart data for {selectedCoin}</p>
            <p className="text-xs text-gray-600 mt-1">Check your internet connection</p>
          </div>
        </div>
      ) : (
        <CandlestickChart candles={candles} height={CHART_HEIGHT} />
      )}
    </div>
  )
}