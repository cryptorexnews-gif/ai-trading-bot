import React, { useState, useEffect, useCallback, useRef } from 'react'
import {
  ComposedChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, Line, Area
} from 'recharts'

const INTERVALS = [
  { value: '1m', label: '1m' },
  { value: '5m', label: '5m' },
  { value: '15m', label: '15m' },
  { value: '1h', label: '1H' },
  { value: '4h', label: '4H' },
  { value: '1d', label: '1D' },
]

const DEFAULT_COINS = ['BTC', 'ETH', 'SOL', 'BNB', 'XRP', 'ADA', 'DOGE', 'AVAX', 'LINK', 'SUI']

function CandleTooltip({ active, payload }) {
  if (!active || !payload || !payload.length) return null
  const d = payload[0].payload
  const change = d.close - d.open
  const changePct = d.open > 0 ? ((change / d.open) * 100).toFixed(2) : '0.00'
  const isGreen = change >= 0

  return (
    <div className="bg-gray-800 border border-gray-700 rounded-lg p-3 shadow-xl text-xs min-w-[160px]">
      <div className="text-gray-400 mb-2">{d.timeLabel}</div>
      <div className="grid grid-cols-2 gap-x-4 gap-y-1">
        <span className="text-gray-500">Open</span>
        <span className="text-white text-right font-mono">${d.open?.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span>
        <span className="text-gray-500">High</span>
        <span className="text-green-400 text-right font-mono">${d.high?.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span>
        <span className="text-gray-500">Low</span>
        <span className="text-red-400 text-right font-mono">${d.low?.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span>
        <span className="text-gray-500">Close</span>
        <span className={`text-right font-mono font-bold ${isGreen ? 'text-green-400' : 'text-red-400'}`}>
          ${d.close?.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
        </span>
        <span className="text-gray-500">Change</span>
        <span className={`text-right font-mono ${isGreen ? 'text-green-400' : 'text-red-400'}`}>
          {isGreen ? '+' : ''}{changePct}%
        </span>
        <span className="text-gray-500">Volume</span>
        <span className="text-blue-400 text-right font-mono">{d.volume?.toLocaleString(undefined, { maximumFractionDigits: 0 })}</span>
      </div>
    </div>
  )
}

export default function PriceChart({ tradingPairs }) {
  const coins = tradingPairs && tradingPairs.length > 0 ? tradingPairs : DEFAULT_COINS
  const [selectedCoin, setSelectedCoin] = useState(coins[0])
  const [interval, setInterval_] = useState('15m')
  const [candles, setCandles] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [lastPrice, setLastPrice] = useState(null)
  const mountedRef = useRef(true)

  const fetchCandles = useCallback(async () => {
    try {
      const headers = {}
      if (typeof window !== 'undefined' && window.__DASHBOARD_API_KEY__) {
        headers['X-API-Key'] = window.__DASHBOARD_API_KEY__
      }
      const response = await fetch(
        `/api/candles?coin=${selectedCoin}&interval=${interval}&limit=80`,
        { headers }
      )
      if (!response.ok) throw new Error(`HTTP ${response.status}`)
      const data = await response.json()

      if (mountedRef.current && data.candles) {
        const formatted = data.candles.map((c) => {
          const date = new Date(c.time)
          const timeLabel = interval.includes('d')
            ? date.toLocaleDateString([], { month: 'short', day: 'numeric' })
            : date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })

          return {
            ...c,
            timeLabel,
            // For bar coloring
            isGreen: c.close >= c.open,
            bodyTop: Math.max(c.open, c.close),
            bodyBottom: Math.min(c.open, c.close),
            bodyHeight: Math.abs(c.close - c.open),
          }
        })
        setCandles(formatted)
        if (formatted.length > 0) {
          setLastPrice(formatted[formatted.length - 1].close)
        }
        setError(null)
      }
    } catch (err) {
      if (mountedRef.current) {
        setError(err.message)
      }
    } finally {
      if (mountedRef.current) setLoading(false)
    }
  }, [selectedCoin, interval])

  useEffect(() => {
    mountedRef.current = true
    setLoading(true)
    fetchCandles()
    const timer = window.setInterval(fetchCandles, 30000)
    return () => {
      mountedRef.current = false
      window.clearInterval(timer)
    }
  }, [fetchCandles])

  const priceChange = candles.length >= 2
    ? candles[candles.length - 1].close - candles[0].open
    : 0
  const priceChangePct = candles.length >= 2 && candles[0].open > 0
    ? ((priceChange / candles[0].open) * 100).toFixed(2)
    : '0.00'
  const isPositive = priceChange >= 0

  return (
    <div className="bg-gray-900 rounded-xl p-6 border border-gray-800">
      {/* Header */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between mb-4 gap-3">
        <div className="flex items-center gap-3">
          <h3 className="text-lg font-semibold">Price Chart</h3>
          {lastPrice && (
            <div className="flex items-center gap-2">
              <span className="text-xl font-bold font-mono">
                ${lastPrice.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
              </span>
              <span className={`text-sm font-bold ${isPositive ? 'text-green-400' : 'text-red-400'}`}>
                {isPositive ? '+' : ''}{priceChangePct}%
              </span>
            </div>
          )}
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          <select
            value={selectedCoin}
            onChange={(e) => setSelectedCoin(e.target.value)}
            className="bg-gray-800 border border-gray-700 rounded-lg px-3 py-1.5 text-sm text-white focus:outline-none focus:border-blue-500"
          >
            {coins.map(c => (
              <option key={c} value={c}>{c}</option>
            ))}
          </select>
          <div className="flex bg-gray-800 rounded-lg border border-gray-700 overflow-hidden">
            {INTERVALS.map(i => (
              <button
                key={i.value}
                onClick={() => setInterval_(i.value)}
                className={`px-2.5 py-1.5 text-xs font-medium transition-colors ${
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

      {/* Chart */}
      {loading && candles.length === 0 ? (
        <div className="flex items-center justify-center py-16 text-gray-500">
          <div className="text-center">
            <div className="text-3xl mb-2 animate-pulse">📊</div>
            <p className="text-sm">Loading {selectedCoin} chart...</p>
          </div>
        </div>
      ) : error && candles.length === 0 ? (
        <div className="flex items-center justify-center py-16 text-gray-500">
          <div className="text-center">
            <div className="text-3xl mb-2">⚠️</div>
            <p className="text-sm">Failed to load chart data</p>
            <p className="text-xs text-gray-600 mt-1">Start the API server: python api_server.py</p>
          </div>
        </div>
      ) : (
        <ResponsiveContainer width="100%" height={320}>
          <ComposedChart data={candles} margin={{ top: 5, right: 5, bottom: 5, left: 5 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
            <XAxis
              dataKey="timeLabel"
              stroke="#4b5563"
              fontSize={10}
              tickLine={false}
              interval="preserveStartEnd"
            />
            <YAxis
              stroke="#4b5563"
              fontSize={10}
              tickLine={false}
              domain={['auto', 'auto']}
              tickFormatter={(v) => {
                if (v >= 10000) return `$${(v / 1000).toFixed(0)}k`
                if (v >= 100) return `$${v.toFixed(0)}`
                if (v >= 1) return `$${v.toFixed(2)}`
                return `$${v.toFixed(4)}`
              }}
              width={65}
            />
            <YAxis
              yAxisId="volume"
              orientation="right"
              stroke="#4b5563"
              fontSize={9}
              tickLine={false}
              tickFormatter={(v) => v >= 1000 ? `${(v / 1000).toFixed(0)}k` : v.toFixed(0)}
              width={45}
              domain={[0, (dataMax) => dataMax * 4]}
            />
            <Tooltip content={<CandleTooltip />} />
            {/* Volume bars */}
            <Bar
              yAxisId="volume"
              dataKey="volume"
              fill="#3b82f620"
              stroke="none"
              barSize={6}
            />
            {/* Price line with area fill */}
            <Area
              type="monotone"
              dataKey="close"
              stroke={isPositive ? '#10b981' : '#ef4444'}
              fill={isPositive ? '#10b98115' : '#ef444415'}
              strokeWidth={2}
              dot={false}
              activeDot={{ r: 4, fill: isPositive ? '#10b981' : '#ef4444', stroke: '#fff', strokeWidth: 2 }}
            />
            {/* High/Low range as thin lines */}
            <Line
              type="monotone"
              dataKey="high"
              stroke="#10b98140"
              strokeWidth={1}
              strokeDasharray="2 4"
              dot={false}
              activeDot={false}
            />
            <Line
              type="monotone"
              dataKey="low"
              stroke="#ef444440"
              strokeWidth={1}
              strokeDasharray="2 4"
              dot={false}
              activeDot={false}
            />
          </ComposedChart>
        </ResponsiveContainer>
      )}
    </div>
  )
}