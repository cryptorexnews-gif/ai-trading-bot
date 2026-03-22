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

function toUnixTime(rawTime) {
  const t = Number(rawTime)
  if (!Number.isFinite(t) || t <= 0) return null
  return t > 1e12 ? Math.floor(t / 1000) : Math.floor(t)
}

function isValidPoint(point) {
  return point && point.time != null && Number.isFinite(point.time) && Number.isFinite(point.value)
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

export default function CandlestickChart({ candles, height = 500, selectedCoin, interval }) {
  const chartContainerRef = useRef(null)
  const chartRef = useRef(null)

  const candleSeriesRef = useRef(null)
  const volumeSeriesRef = useRef(null)
  const ema9SeriesRef = useRef(null)
  const ema21SeriesRef = useRef(null)
  const vwapSeriesRef = useRef(null)
  const rsiSeriesRef = useRef(null)
  const rsiOverboughtSeriesRef = useRef(null)
  const rsiOversoldSeriesRef = useRef(null)
  const macdSeriesRef = useRef(null)
  const macdSignalSeriesRef = useRef(null)
  const macdHistogramSeriesRef = useRef(null)

  const [hoverData, setHoverData] = useState(null)

  const lastFittedSeriesKeyRef = useRef('')

  const seriesKey = `${selectedCoin || 'default'}-${interval || 'default'}`

  const candleData = useMemo(() => {
    if (!candles?.length) return []
    return candles
      .slice(-1000)
      .map(c => {
        const time = toUnixTime(c.time)
        const open = Number(c.open)
        const high = Number(c.high)
        const low = Number(c.low)
        const close = Number(c.close)
        const volume = Number(c.volume || 0)

        if (time == null) return null
        if (![open, high, low, close].every(Number.isFinite)) return null
        return { time, open, high, low, close, volume: Number.isFinite(volume) ? volume : 0 }
      })
      .filter(Boolean)
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

    const ema9 = ema9Raw
      .map((v, i) => ({ time: candleData[i + 8]?.time ?? null, value: Number(v) }))
      .filter(isValidPoint)

    const ema21 = ema21Raw
      .map((v, i) => ({ time: candleData[i + 20]?.time ?? null, value: Number(v) }))
      .filter(isValidPoint)

    const vwap = vwapRaw
      .map((v, i) => ({ time: candleData[i]?.time ?? null, value: Number(v) }))
      .filter(isValidPoint)

    const rsi = rsiRaw
      .map((v, i) => ({ time: candleData[i + 14]?.time ?? null, value: Number(v) }))
      .filter(isValidPoint)

    const macdOffset = 25
    const macd = macdRaw.macd
      .map((v, i) => ({ time: candleData[i + macdOffset]?.time ?? null, value: Number(v) }))
      .filter(isValidPoint)

    const macdSignal = macdRaw.signal
      .map((v, i) => ({ time: candleData[i + macdOffset + 8]?.time ?? null, value: Number(v) }))
      .filter(isValidPoint)

    const macdHistogram = macdRaw.histogram
      .map((v, i) => ({
        time: candleData[i + macdOffset + 8]?.time ?? null,
        value: Number(v),
        color: Number(v) >= 0 ? '#10b981' : '#ef4444',
      }))
      .filter(d => d.time != null && Number.isFinite(d.time) && Number.isFinite(d.value))

    return { ema9, ema21, vwap, rsi, macd, macdSignal, macdHistogram }
  }, [candleData])

  const volumeData = useMemo(
    () =>
      candleData
        .map(c => ({
          time: c.time,
          value: c.volume * c.close,
          color: c.close >= c.open ? '#10b98135' : '#ef444435',
        }))
        .filter(d => d.time != null && Number.isFinite(d.time) && Number.isFinite(d.value)),
    [candleData]
  )

  useEffect(() => {
    if (!chartContainerRef.current || chartRef.current) return

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
      handleScroll: {
        mouseWheel: false,
        pressedMouseMove: true,
        horzTouchDrag: true,
        vertTouchDrag: true,
      },
      handleScale: {
        mouseWheel: false,
        pinch: true,
        axisPressedMouseMove: true,
        axisDoubleClickReset: true,
      },
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
    rsiOverboughtSeriesRef.current = rsiOverbought
    rsiOversoldSeriesRef.current = rsiOversold
    macdSeriesRef.current = macdSeries
    macdSignalSeriesRef.current = macdSignalSeries
    macdHistogramSeriesRef.current = macdHistogramSeries
    chartRef.current = chart

    const handleResize = () => {
      if (chartContainerRef.current && chartRef.current) {
        chartRef.current.applyOptions({ width: chartContainerRef.current.clientWidth, height })
      }
    }
    window.addEventListener('resize', handleResize)

    return () => {
      window.removeEventListener('resize', handleResize)
      chart.remove()
      chartRef.current = null
      candleSeriesRef.current = null
      volumeSeriesRef.current = null
      ema9SeriesRef.current = null
      ema21SeriesRef.current = null
      vwapSeriesRef.current = null
      rsiSeriesRef.current = null
      rsiOverboughtSeriesRef.current = null
      rsiOversoldSeriesRef.current = null
      macdSeriesRef.current = null
      macdSignalSeriesRef.current = null
      macdHistogramSeriesRef.current = null
    }
  }, [height])

  useEffect(() => {
    if (!chartRef.current) return
    chartRef.current.applyOptions({ height })
  }, [height])

  useEffect(() => {
    if (!candleSeriesRef.current || !chartRef.current || !candleData.length) return

    candleSeriesRef.current.setData(
      candleData
        .map(({ time, open, high, low, close }) => ({ time, open, high, low, close }))
        .filter(d => d.time != null)
    )
    volumeSeriesRef.current?.setData(volumeData)

    ema9SeriesRef.current?.setData(indicatorData.ema9)
    ema21SeriesRef.current?.setData(indicatorData.ema21)
    vwapSeriesRef.current?.setData(indicatorData.vwap)
    rsiSeriesRef.current?.setData(indicatorData.rsi)

    macdSeriesRef.current?.setData(indicatorData.macd)
    macdSignalSeriesRef.current?.setData(indicatorData.macdSignal)
    macdHistogramSeriesRef.current?.setData(indicatorData.macdHistogram)

    const firstTime = candleData[0]?.time
    const lastTime = candleData[candleData.length - 1]?.time
    if (firstTime != null && lastTime != null) {
      rsiOverboughtSeriesRef.current?.setData([{ time: firstTime, value: 70 }, { time: lastTime, value: 70 }])
      rsiOversoldSeriesRef.current?.setData([{ time: firstTime, value: 30 }, { time: lastTime, value: 30 }])
    }

    if (lastFittedSeriesKeyRef.current !== seriesKey) {
      chartRef.current.timeScale().fitContent()
      lastFittedSeriesKeyRef.current = seriesKey
    }
  }, [candleData, volumeData, indicatorData, seriesKey])

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
        <div className="absolute top-0 left-0 right-0 pointer-events-none z-20 border-b border-gray-700/70 bg-gray-950/88 backdrop-blur-sm">
          <div className="px-2 py-1.5 overflow-x-auto">
            <div className="flex items-center gap-3 text-[10px] leading-none font-mono min-w-max">
              <span className="text-gray-400">O <span className="text-white">{fmtPrice(hoverData.o)}</span></span>
              <span className="text-gray-400">H <span className="text-green-400">{fmtPrice(hoverData.h)}</span></span>
              <span className="text-gray-400">L <span className="text-red-400">{fmtPrice(hoverData.l)}</span></span>
              <span className="text-gray-400">C <span className={isPositive ? 'text-green-400' : 'text-red-400'}>{fmtPrice(hoverData.c)}</span></span>
              <span className="text-gray-400">Δ <span className={isPositive ? 'text-green-400' : 'text-red-400'}>{isPositive ? '+' : ''}{fmtPct(change)}</span></span>
              <span className="text-gray-400">RSI <span className="text-blue-400">{fmtPrice(hoverData.rsi)}</span></span>
              <span className="text-gray-400">MACD <span className="text-blue-400">{fmtPrice(hoverData.macd)}</span></span>
              <span className="text-gray-400">VWAP <span className="text-yellow-400">{fmtPrice(hoverData.vwap)}</span></span>
              <span className="text-gray-400">EMA9 <span className="text-green-400">{fmtPrice(hoverData.ema9)}</span></span>
              <span className="text-gray-400">EMA21 <span className="text-orange-400">{fmtPrice(hoverData.ema21)}</span></span>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}