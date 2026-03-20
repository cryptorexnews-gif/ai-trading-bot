import React, { useEffect, useMemo, useRef, useState, useCallback } from 'react'
import { 
  createChart, ColorType, CrosshairMode, LineStyle, CandlestickSeries, 
  HistogramSeries, LineSeries 
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
  return (Number(value) * 100).toFixed(1) + '%'
}

function computeEMA(prices, period) {
  if (prices.length < period) return []
  const k = 2 / (period + 1)
  const ema = [prices.slice(0, period).reduce((a, b) => a + b, 0) / period]
  for (let i = period; i < prices.length; i++) {
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
  
  for (let i = period; i < changes.length; i++) {
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

export default function CandlestickChart({ candles, height = 500, selectedCoin = '—', interval = '4h' }) {
  const chartContainerRef = useRef(null)
  const chartRef = useRef(null)
  const candleSeriesRef = useRef(null)
  const volumeSeriesRef = useRef(null)
  const ema9SeriesRef = useRef(null)
  const ema21SeriesRef = useRef(null)
  const vwapSeriesRef = useRef(null)
  const rsiSeriesRef = useRef(null)
  const macdSeriesRef = useRef(null)

  const [hoverData, setHoverData] = useState(null)
  const retryCountRef = useRef(0)
  const maxRetries = 3

  const candleData = useMemo(() => {
    if (!candles?.length) return []
    return candles.slice(-1000).map(c => ({
      time: Math.floor(c.time / 1000),
      open: Number(c.open),
      high: Number(c.high),
      low: Number(c.low),
      close: Number(c.close),
    }))
  }, [candles])

  const indicatorData = useMemo(() => {
    if (candleData.length < 50) return { ema9: [], ema21: [], vwap: [], rsi: [], macd: { macd: [], signal: [], histogram: [] } }
    
    const closes = candleData.map(c => c.close)
    const highs = candleData.map(c => c.high)
    const lows = candleData.map(c => c.low)
    const volumes = candleData.map(c => c.volume || 0)
    
    const ema9 = computeEMA(closes, 9).map((v, i) => ({ time: candleData[i]?.time, value: v }))
    const ema21 = computeEMA(closes, 21).map((v, i) => ({ time: candleData[i]?.time, value: v }))
    const vwap = computeVWAP(highs, lows, closes, volumes).map((v, i) => ({ time: candleData[i]?.time, value: v }))
    const rsi = computeRSI(closes).map((v, i) => ({ time: candleData[i + 1]?.time, value: v }))
    const macd = computeMACD(closes)
    
    return { 
      ema9: ema9.slice(-candleData.length), 
      ema21: ema21.slice(-candleData.length), 
      vwap: vwap.slice(-candleData.length),
      rsi,
      macd: {
        macd: macd.macd.slice(-candleData.length).map((v, i) => ({ time: candleData[i + 1]?.time, value: v })),
        signal: macd.signal.slice(-candleData.length).map((v, i) => ({ time: candleData[i + 1]?.time, value: v })),
        histogram: macd.histogram.slice(-candleData.length).map((v, i) => ({ time: candleData[i + 1]?.time, value: v, color: v >= 0 ? '#10b981' : '#ef4444' }))
      }
    }
  }, [candleData])

  const volumeData = useMemo(() => {
    if (!candleData.length) return []
    return candleData.map(c => ({
      time: c.time,
      value: Number(c.volume || 0) * c.close,
      color: c.close >= c.open ? '#10b98135' : '#ef444435',
    }))
  }, [candleData])

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
        vertLine: {
          color: '#6b7280',
          width: 1,
          style: LineStyle.Solid,
          labelBackgroundColor: '#374151',
        },
        horzLine: {
          color: '#6b7280',
          width: 1,
          style: LineStyle.Solid,
          labelBackgroundColor: '#374151',
        },
      },
      rightPriceScale: {
        borderColor: '#374151',
      },
      timeScale: {
        borderColor: '#374151',
        rightBarStaysOnScroll: true,
        barSpacing: 3,
        fixLeftEdge: false,
        lockVisibleTimeRangeOnResize: true,
      },
      handleScroll: true,
      handleScale: true,
    })

    const candleSeries = chart.addCandlestickSeries({
      upColor: '#10b98166',
      downColor: '#ef444466',
      borderDownColor: '#ef4444',
      borderUpColor: '#10b981',
      wickUpColor: '#10b981',
      wickDownColor: '#ef4444',
    })

    const volumeSeries = chart.addHistogramSeries({
      priceFormat: { type: 'volume' },
      priceScaleId: '',
      color: '#10b98120',
    })

    const ema9Series = chart.addLineSeries({
      color: '#10b981',
      lineWidth: 2,
      lineStyle: LineStyle.Solid,
    })
    const ema21Series = chart.addLineSeries({
      color: '#f59e0b',
      lineWidth: 2,
      lineStyle: LineStyle.Solid,
    })
    const vwapSeries = chart.addLineSeries({
      color: '#facc15',
      lineWidth: 2,
      lineStyle: LineStyle.Dashed,
    })

    const rsiPriceScale = chart.priceScale('right', {
      scaleMargins: { top: 0.8, bottom: 0 },
      borderColor: '#374151',
    })
    const rsiSeries = chart.addLineSeries({
      color: '#3b82f6',
      lineWidth: 2,
      priceScaleId: rsiPriceScale.id(),
    })
    const rsiOverbought = chart.addLineSeries({
      color: '#ef4444',
      lineWidth: 1,
      lineStyle: LineStyle.Dashed,
      priceScaleId: rsiPriceScale.id(),
    })
    const rsiOversold = chart.addLineSeries({
      color: '#10b981',
      lineWidth: 1,
      lineStyle: LineStyle.Dashed,
      priceScaleId: rsiPriceScale.id(),
    })

    rsiOverbought.setData([{ time: candleData[0]?.time || 0, value: 70 }, { time: candleData[candleData.length - 1]?.time || 0, value: 70 }])
    rsiOversold.setData([{ time: candleData[0]?.time || 0, value: 30 }, { time: candleData[candleData.length - 1]?.time || 0, value: 30 }])

    const macdPriceScale = chart.priceScale('right', {
      scaleMargins: { top: 0.8, bottom: 0 },
      borderColor: '#374151',
    })
    const macdSeries = chart.addLineSeries({
      color: '#3b82f6',
      lineWidth: 2,
      priceScaleId: macdPriceScale.id(),
    })
    const macdSignalSeries = chart.addLineSeries({
      color: '#f59e0b',
      lineWidth: 2,
      lineStyle: LineStyle.Dashed,
      priceScaleId: macdPriceScale.id(),
    })
    const macdHistogramSeries = chart.addHistogramSeries({
      color: '#10b981',
      priceFormat: { type: 'price' },
      priceScaleId: macdPriceScale.id(),
    })

    chartRef.current = chart
    candleSeriesRef.current = candleSeries
    volumeSeriesRef.current = volumeSeries
    ema9SeriesRef.current = ema9Series
    ema21SeriesRef.current = ema21Series
    vwapSeriesRef.current = vwapSeries
    rsiSeriesRef.current = rsiSeries
    macdSeriesRef.current = macdSeries

    const handleResize = () => {
      chart.applyOptions({ width: chartContainerRef.current.clientWidth })
    }
    window.addEventListener('resize', handleResize)

    return () => {
      window.removeEventListener('resize', handleResize)
      chart.remove()
    }
  }, [height, candleData.length])

  useEffect(() => {
    if (!candleSeriesRef.current || !volumeSeriesRef.current || !ema9SeriesRef.current || 
        !ema21SeriesRef.current || !vwapSeriesRef.current || !rsiSeriesRef.current || 
        !macdSeriesRef.current || !candleData.length) return

    candleSeriesRef.current.setData(candleData)
    volumeSeriesRef.current.setData(volumeData)
    ema9SeriesRef.current.setData(indicatorData.ema9)
    ema21SeriesRef.current.setData(indicatorData.ema21)
    vwapSeriesRef.current.setData(indicatorData.vwap)
    rsiSeriesRef.current.setData(indicatorData.rsi)
    macdSeriesRef.current.setData(indicatorData.macd.macd)
    macdSeriesRef.current.setData(indicatorData.macd.signal)
    macdSeriesRef.current.setData(indicatorData.macd.histogram)

    if (chartRef.current) {
      const timeScale = chartRef.current.timeScale()
      timeScale.scrollToRealTime()
    }
  }, [candleData, volumeData, indicatorData])

  const handleCrosshairMove = useCallback((param) => {
    if (!param || !param.seriesData.size) {
      setHoverData(null)
      return
    }

    const candleData = param.seriesData.get(candleSeriesRef.current)
    if (!candleData) {
      setHoverData(null)
      return
    }

    const ema9Data = param.seriesData.get(ema9SeriesRef.current)
    const ema21Data = param.seriesData.get(ema21SeriesRef.current)
    const vwapData = param.seriesData.get(vwapSeriesRef.current)
    const rsiData = param.seriesData.get(rsiSeriesRef.current)
    const macdData = param.seriesData.get(macdSeriesRef.current)

    setHoverData({
      o: candleData.openValue,
      h: candleData.highValue,
      l: candleData.lowValue,
      c: candleData.value,
      v: volumeData.find(d => d.time === candleData.time)?.value || 0,
      ema9: ema9Data?.value || 0,
      ema21: ema21Data?.value || 0,
      vwap: vwapData?.value || 0,
      rsi: rsiData?.value || 50,
      macd: macdData?.value || 0,
      time: candleData.time,
    })
  }, [volumeData])

  useEffect(() => {
    if (chartRef.current) {
      chartRef.current.subscribeCrosshairMove(handleCrosshairMove)
    }
    return () => {
      if (chartRef.current) {
        chartRef.current.unsubscribeCrosshairMove(handleCrosshairMove)
      }
    }
  }, [handleCrosshairMove])

  if (!candleData.length) {
    return <ChartSkeleton height={height} />
  }

  const change = (hoverData?.c - hoverData?.o) / hoverData?.o || 0
  const isPositive = change >= 0

  return (
    <div className="w-full h-[500px] md:h-[550px] relative">
      <div ref={chartContainerRef} className="w-full h-full" />
      
      {hoverData && (
        <div className="absolute top-2 left-2 right-2 pointer-events-none z-20">
          <div className="bg-gray-900/95 border border-gray-700/80 backdrop-blur-md rounded-xl p-3 shadow-2xl max-w-md mx-auto">
            <div className="grid grid-cols-2 gap-3 text-xs font-mono">
              <div>
                <div className="text-gray-400 mb-1">Open</div>
                <div className="font-bold text-white">{fmtPrice(hoverData.o)}</div>
              </div>
              <div>
                <div className="text-gray-400 mb-1">High</div>
                <div className="font-bold text-green-400">{fmtPrice(hoverData.h)}</div>
              </div>
              <div>
                <div className="text-gray-400 mb-1">Low</div>
                <div className="font-bold text-red-400">{fmtPrice(hoverData.l)}</div>
              </div>
              <div>
                <div className="text-gray-400 mb-1">Close</div>
                <div className={`font-bold ${isPositive ? 'text-green-400' : 'text-red-400'}`}>
                  {fmtPrice(hoverData.c)}
                </div>
              </div>
              <div className="col-span-2">
                <div className="text-gray-400 mb-1">Change</div>
                <div className={`font-bold text-sm ${isPositive ? 'text-green-400' : 'text-red-400'}`}>
                  {isPositive ? '+' : ''}{fmtPct(change)}
                </div>
              </div>
              <div>
                <div className="text-gray-400 mb-1">RSI</div>
                <div className="font-bold text-blue-400">{fmtPrice(hoverData.rsi)}</div>
              </div>
              <div>
                <div className="text-gray-400 mb-1">MACD</div>
                <div className="font-bold text-blue-400">{fmtPrice(hoverData.macd)}</div>
              </div>
              <div>
                <div className="text-gray-400 mb-1">Vol</div>
                <div className="font-bold">${(hoverData.v / 1e6).toFixed(1)}M</div>
              </div>
              <div>
                <div className="text-gray-400 mb-1">EMA9</div>
                <div className="font-bold text-green-400">{fmtPrice(hoverData.ema9)}</div>
              </div>
              <div>
                <div className="text-gray-400 mb-1">EMA21</div>
                <div className="font-bold text-orange-400">{fmtPrice(hoverData.ema21)}</div>
              </div>
              <div>
                <div className="text-gray-400 mb-1">VWAP</div>
                <div className="font-bold text-yellow-400">{fmtPrice(hoverData.vwap)}</div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}