import React, { useState, useEffect, useCallback, useRef } from 'react'
import { getHeaders, getApiBase } from '../hooks/useApi'
import ChartToolbar from './trading/ChartToolbar'
import StatsBar from './trading/StatsBar'
import CandlestickChart from './trading/CandlestickChart'
import ChartSkeleton from './trading/ChartSkeleton'

const DEFAULT_COINS = ['BTC', 'ETH', 'SOL', 'BNB', 'XRP', 'ADA', 'DOGE', 'AVAX', 'LINK', 'SUI']
const CHART_HEIGHT = 500

function safeNum(v, fallback = 0) {
  if (v == null || isNaN(v)) return fallback
  return Number(v)
}

export default function TradingView({ tradingPairs }) {
  const coins = tradingPairs && tradingPairs.length > 0 ? tradingPairs : DEFAULT_COINS
  const [selectedCoin, setSelectedCoin] = useState(coins[0])
  const [interval, setInterval_] = useState('4h')
  const [candles, setCandles] = useState([])
  const [chartLoading, setChartLoading] = useState(true)
  const [lastPrice, setLastPrice] = useState(null)
  const [stats24h, setStats24h] = useState(null)
  const mountedRef = useRef(true)
  const apiBase = getApiBase()

  const fetchCandles = useCallback(async () => {
    let candleData = null

    try {
      const res = await fetch(
        `${apiBase}/candles?coin=${selectedCoin}&interval=${interval}&limit=150`,
        { headers: getHeaders(), credentials: 'same-origin' }
      )

      if (res.ok) {
        const json = await res.json()
        if (json.candles && json.candles.length > 0) {
          candleData = json.candles.map(c => ({
            time: c.time || 0,
            open: parseFloat(c.open || 0),
            high: parseFloat(c.high || 0),
            low: parseFloat(c.low || 0),
            close: parseFloat(c.close || 0),
            volume: parseFloat(c.volume || 0),
          }))
        }
      }
    } catch {
      // handled by empty data fallback
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
  }, [apiBase, selectedCoin, interval])

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
            <div className="text-4xl mb-2">📊</div>
            <p className="text-sm">No chart data for {selectedCoin}</p>
            <p className="text-xs text-gray-600 mt-1">Check backend API connection</p>
          </div>
        </div>
      ) : (
        <CandlestickChart
          candles={candles}
          height={CHART_HEIGHT}
          selectedCoin={selectedCoin}
          interval={interval}
        />
      )}
    </div>
  )
}