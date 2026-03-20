import React, { useEffect, useMemo, useRef, useState, useCallback } from 'react'
import {
  createChart,
  ColorType,
  CrosshairMode,
  LineStyle,
  CandlestickSeries,
  HistogramSeries,
  LineSeries,
} from 'lightweight-charts'

function fmtPrice(value) {
  const n = Number(value || 0)
  if (!isFinite(n)) return '—'
  if (n >= 1000) return n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })
  if (n >= 1) return n.toFixed(4)
  if (n >= 0.01) return n.toFixed(5)
  return n.toFixed(8)
}

function fmtPct(value) {
  return `${(Number(value) * 100).toFixed(1)}%`
}

function computeEMA(prices, period) {
  if (prices.length < period) return []
  const k = 2 / (period + 1)
  const ema = [prices.slice(0, period).reduce((a, b) => a + b, 0) / period]
  for (let i = period; i < prices.length; i += 1) {
    ema.push(prices[i] * k + ema[ema.length - 1] * (1 - k))
  }
  return ema
}

function computeRSI(closes, period = 14) {
  if (closes.length < period + 1) return []
  const changes = closes.slice(1).map((close, i) => close - closes[i])

  let avgGain = changes.slice(0, period).filter(c => c > 0).reduce((a, b) => a + b, 0) / period
  let avgLoss = Math.abs(changes.slice(0, period).filter(c => c < 0).reduce((a, b) => a + b, 0) / period)

  const rsi = [50]
  for (let i = period; i < changes.length; i += 1) {
    const change = changes[i]
    avgGain = (avgGain * (period - 1) + Math.max(change, 0)) / period
    avgLoss = (avgLoss * (period - 1) + Math.abs(Math.min(change, 0))) / period
    const rs = avgLoss === 0 ? 100 : avgGain / avgLoss
    rsi.push(100 - (100 / (1 + rs)))
  }
  return rsi
}

function computeVWAP(highs, lows, closes, volumes) {
  if (!highs.length) return []
  const typicals = highs.map((h, i) => (h + lows[i] + closes[i]) / 3)
  const tpVol = typicals.map((t, i) => t * volumes[i])

  let cumTPVol = 0
  let cumVol = 0
  return typicals.map((t, i) => {
    cumTPVol += tpVol[i]
    cumVol += volumes[i]
    return cumVol > 0 ? cumTPVol / cumVol : t
  })
}

function computeMACD(closes, fast = 12, slow = 26, signal = 9) {
  if (closes.length < slow) return { macd: [], signal: [], histogram: [] }

  const emaFast = computeEMA(closes, fast)
  const emaSlow = computeEMA(closes, slow)
  const macd = emaFast.map((f, i) => f - (emaSlow[i] || 0))
  const signalLine = computeEMA(macd, signal)
  const histogram = macd.map((m, i) => m - (signalLine[i] || 0))

  return { macd, signal: signalLine, histogram }
}

export default function CandlestickChart({ candles, height = 500 }) {
  const chartContainerRef = useRef(null)
  const chartRef = useRef(null)

  const candleSeriesRef = useRef(null)
  const volumeSeriesRef = useRef(null)
  const ema9SeriesRef = useRef(null)
  const ema21SeriesRef = useRef(null)
  const vwapSeriesRef = useRef(null)
  const rsiSeriesRef = useRef(null)
  const macdSeriesRef = useRef(null)
  const macdSignalSeriesRef = useRef(null)
  const macdHistogramSeriesRef = useRef(null)

  const [hoverData, setHoverData] = useState(null)

  const candleData = useMemo(() => {
    if (!candles?.length) return []
    return candles.slice(-1000).map(c => ({
      time: Math.floor(Number(c.time || 0) / 1000),
      open: Number(c.open),
      high: Number(c.high),
      low: Number(c.low),
      close: Number(c.close),
      volume: Number(c.volume || 0),
    }))
  }, [candles])

  const indicatorData = useMemo(() => {
    if (candleData.length < 50) {
      return { ema9: [], ema21: [], vwap: [], rsi: [], macd: [], macdSignal: [], macdHistogram: [] }
    }

    const closes = candleData.map(c => c.close)
    const highs = candleData.map(c => c.high)
    const lows = candleData.map(c => c.low)
    const volumes = candleData.map(c => c.volume)

    const ema9Raw = computeEMA(closes, 9)
    const ema21Raw = computeEMA(closes, 21)
    const vwapRaw = computeVWAP(highs, lows, closes, volumes)
    const rsiRaw = computeRSI(closes, 14)
    const macdRaw = computeMACD(closes)

    const ema9 = ema9Raw.map((v, i) => ({ time: candleData[i + 8]?.time, value: v })).filter(Boolean)
    const ema21 = ema21Raw.map((v, i) => ({ time: candleData[i + 20]?.time, value: v })).filter(Boolean)
    const vwap = vwapRaw.map((v, i) => ({ time: candleData[i]?.time, value: v }))
    const rsi = rsiRaw.map((v, i) => ({ time: candleData[i + 14]?.time, value: v })).filter(Boolean)

    const macdOffset = 25
    const macd = macdRaw.macd.map((v, i) => ({ time: candleData[i + macdOffset]?.time, value: v })).filter(Boolean)
    const macdSignal = macdRaw.signal.map((v, i) => ({ time: candleData[i + macdOffset + 8]?.time, value: v })).filter(Boolean)
    const macdHistogram = macdRaw.histogram
      .map((v, i) => ({
        time: candleData[i + macdOffset + 8]?.time,
        value: v,
        color: v >= 0 ? '#10b981' : '#ef4444',
      }))
      .filter(d => d.time != null)

    return { ema9, ema21, vwap, rsi, macd, macdSignal, macdHistogram }
  }, [candleData])

  const volumeData = useMemo(
    () =>
      candleData.map(c => ({
        time: c.time,
        value: c.volume * c.close,
        color: c.close >= c.open ? '#10b98135' : '#ef444435',
      })),
    [candleData]
  )

  useEffect(() => {
    if (!chartContainerRef.current) return

    const chart = createChart(chartContainerRef.current, {
      width: chartContainerRef.current.clientWidth,
      height,
      layout: {
        background: { type: ColorType.Solid, color: 'transparent' },
        textColor: '#9ca3af',
      },
      grid: {
        vertLines: { color: '#1f293740', style: LineStyle.Dashed },
        horzLines: { color: '#1f293760', style: LineStyle.Dashed },
      },
      crosshair: {
        mode: CrosshairMode.Normal,
      },
      rightPriceScale: {
        borderColor: '#374151',
      },
      timeScale: {
        borderColor: '#374151',
        rightBarStaysOnScroll: true,
        barSpacing: 3,
      },
      handleScroll: true,
      handleScale: true,
    })

    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor: '#10b981',
      downColor: '#ef4444',
      borderVisible: false,
      wickUpColor: '#10b981',
      wickDownColor: '#ef4444',
    })

    const volumeSeries = chart.addSeries(HistogramSeries, {
      priceFormat: { type: 'volume' },
      priceScaleId: 'volume',
    })
    chart.priceScale('volume').applyOptions({
      scaleMargins: { top: 0.72, bottom: 0 },
      borderVisible: false,
    })

    const ema9Series = chart.addSeries(LineSeries, {
      color: '#10b981',
      lineWidth: 2,
      lineStyle: LineStyle.Solid,
    })

    const ema21Series = chart.addSeries(LineSeries, {
      color: '#f59e0b',
      lineWidth: 2,
      lineStyle: LineStyle.Solid,
    })

    const vwapSeries = chart.addSeries(LineSeries, {
      color: '#facc15',
      lineWidth: 2,
      lineStyle: LineStyle.Dashed,
    })

    const rsiSeries = chart.addSeries(LineSeries, {
      color: '#3b82f6',
      lineWidth: 1,
      priceScaleId: 'rsi',
    })
    chart.priceScale('rsi').applyOptions({
      scaleMargins: { top: 0.82, bottom: 0.06 },
      borderVisible: false,
    })

    const rsiOverbought = chart.addSeries(LineSeries, {
      color: '#ef4444',
      lineWidth: 1,
      lineStyle: LineStyle.Dashed,
      priceScaleId: 'rsi',
    })

    const rsiOversold = chart.addSeries(LineSeries, {
      color: '#10b981',
      lineWidth: 1,
      lineStyle: LineStyle.Dashed,
      priceScaleId: 'rsi',
    })

    const macdSeries = chart.addSeries(LineSeries, {
      color: '#3b82f6',
      lineWidth: 1,
      priceScaleId: 'macd',
    })

    const macdSignalSeries = chart.addSeries(LineSeries, {
      color: '#f59e0b',
      lineWidth: 1,
      lineStyle: LineStyle.Dashed,
      priceScaleId: 'macd',
    })

    const macdHistogramSeries = chart.addSeries(HistogramSeries, {
      priceScaleId: 'macd',
    })
    chart.priceScale('macd').applyOptions({
      scaleMargins: { top: 0.7, bottom: 0.15 },
      borderVisible: false,
    })

    candleSeriesRef.current = candleSeries
    volumeSeriesRef.current = volumeSeries
    ema9SeriesRef.current = ema9Series
    ema21SeriesRef.current = ema21Series
    vwapSeriesRef.current = vwapSeries
    rsiSeriesRef.current = rsiSeries
    macdSeriesRef.current = macdSeries
    macdSignalSeriesRef.current = macdSignalSeries
    macdHistogramSeriesRef.current = macdHistogramSeries
    chartRef.current = chart

    const firstTime = candleData[0]?.time ?? 0
    const lastTime = candleData[candleData.length - 1]?.time ?? 0
    rsiOverbought.setData([{ time: firstTime, value: 70 }, { time: lastTime, value: 70 }])
    rsiOversold.setData([{ time: firstTime, value: 30 }, { time: lastTime, value: 30 }])

    const handleResize = () => {
      if (chartContainerRef.current) {
        chart.applyOptions({ width: chartContainerRef.current.clientWidth })
      }
    }
    window.addEventListener('resize', handleResize)

    return () => {
      window.removeEventListener('resize', handleResize)
      chart.remove()
    }
  }, [height, candleData])

  useEffect(() => {
    if (!candleSeriesRef.current || !candleData.length) return

    candleSeriesRef.current.setData(candleData.map(({ time, open, high, low, close }) => ({ time, open, high, low, close })))
    volumeSeriesRef.current?.setData(volumeData)

    ema9SeriesRef.current?.setData(indicatorData.ema9)
    ema21SeriesRef.current?.setData(indicatorData.ema21)
    vwapSeriesRef.current?.setData(indicatorData.vwap)
    rsiSeriesRef.current?.setData(indicatorData.rsi)

    macdSeriesRef.current?.setData(indicatorData.macd)
    macdSignalSeriesRef.current?.setData(indicatorData.macdSignal)
    macdHistogramSeriesRef.current?.setData(indicatorData.macdHistogram)

    chartRef.current?.timeScale().fitContent()
  }, [candleData, volumeData, indicatorData])

  const handleCrosshairMove = useCallback(
    param => {
      if (!param || !param.seriesData || !candleSeriesRef.current) {
        setHoverData(null)
        return
      }

      const c = param.seriesData.get(candleSeriesRef.current)
      if (!c) {
        setHoverData(null)
        return
      }

      const o = c.open ?? c.openValue ?? 0
      const h = c.high ?? c.highValue ?? 0
      const l = c.low ?? c.lowValue ?? 0
      const cl = c.close ?? c.value ?? 0

      const rsiVal = param.seriesData.get(rsiSeriesRef.current)?.value ?? 50
      const macdVal = param.seriesData.get(macdSeriesRef.current)?.value ?? 0
      const ema9Val = param.seriesData.get(ema9SeriesRef.current)?.value ?? 0
      const ema21Val = param.seriesData.get(ema21SeriesRef.current)?.value ?? 0
      const vwapVal = param.seriesData.get(vwapSeriesRef.current)?.value ?? 0

      setHoverData({
        o,
        h,
        l,
        c: cl,
        rsi: rsiVal,
        macd: macdVal,
        ema9: ema9Val,
        ema21: ema21Val,
        vwap: vwapVal,
      })
    },
    []
  )

  useEffect(() => {
    if (!chartRef.current) return
    chartRef.current.subscribeCrosshairMove(handleCrosshairMove)
    return () => {
      chartRef.current?.unsubscribeCrosshairMove(handleCrosshairMove)
    }
  }, [handleCrosshairMove])

  if (!candleData.length) return null

  const change = hoverData ? (hoverData.c - hoverData.o) / (hoverData.o || 1) : 0
  const isPositive = change >= 0

  return (
    <div className="w-full h-[500px] md:h-[550px] relative">
      <div ref={chartContainerRef} className="w-full h-full" />

      {hoverData && (
        <div className="absolute top-2 left-2 right-2 pointer-events-none z-20">
          <div className="bg-gray-900/95 border border-gray-700/80 backdrop-blur-md rounded-xl p-3 shadow-2xl max-w-md mx-auto">
            <div className="grid grid-cols-2 gap-3 text-xs font-mono">
              <div><div className="text-gray-400 mb-1">Open</div><div className="font-bold text-white">{fmtPrice(hoverData.o)}</div></div>
              <div><div className="text-gray-400 mb-1">High</div><div className="font-bold text-green-400">{fmtPrice(hoverData.h)}</div></div>
              <div><div className="text-gray-400 mb-1">Low</div><div className="font-bold text-red-400">{fmtPrice(hoverData.l)}</div></div>
              <div><div className="text-gray-400 mb-1">Close</div><div className={`font-bold ${isPositive ? 'text-green-400' : 'text-red-400'}`}>{fmtPrice(hoverData.c)}</div></div>
              <div className="col-span-2">
                <div className="text-gray-400 mb-1">Change</div>
                <div className={`font-bold text-sm ${isPositive ? 'text-green-400' : 'text-red-400'}`}>{isPositive ? '+' : ''}{fmtPct(change)}</div>
              </div>
              <div><div className="text-gray-400 mb-1">RSI</div><div className="font-bold text-blue-400">{fmtPrice(hoverData.rsi)}</div></div>
              <div><div className="text-gray-400 mb-1">MACD</div><div className="font-bold text-blue-400">{fmtPrice(hoverData.macd)}</div></div>
              <div><div className="text-gray-400 mb-1">EMA9</div><div className="font-bold text-green-400">{fmtPrice(hoverData.ema9)}</div></div>
              <div><div className="text-gray-400 mb-1">EMA21</div><div className="font-bold text-orange-400">{fmtPrice(hoverData.ema21)}</div></div>
              <div className="col-span-2"><div className="text-gray-400 mb-1">VWAP</div><div className="font-bold text-yellow-400">{fmtPrice(hoverData.vwap)}</div></div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}