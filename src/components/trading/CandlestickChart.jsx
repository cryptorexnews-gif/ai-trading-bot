import React, { useEffect, useMemo, useRef, useState } from 'react'
import { createChart, ColorType, CrosshairMode, LineStyle, CandlestickSeries, HistogramSeries } from 'lightweight-charts'

function fmtPrice(value) {
  const n = Number(value || 0)
  if (!isFinite(n)) return '—'
  if (n >= 1000) return n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })
  if (n >= 1) return n.toFixed(4)
  if (n >= 0.01) return n.toFixed(5)
  return n.toFixed(8)
}

export default function CandlestickChart({ candles, height = 500, selectedCoin = '—', interval = '4h' }) {
  const chartContainerRef = useRef(null)
  const chartRef = useRef(null)
  const candleSeriesRef = useRef(null)
  const volumeSeriesRef = useRef(null)

  const [hoverCandle, setHoverCandle] = useState(null)
  const [isHovering, setIsHovering] = useState(false)

  const lastCandle = useMemo(() => {
    if (!candles || candles.length === 0) return null
    return candles[candles.length - 1]
  }, [candles])

  const activeCandle = isHovering && hoverCandle ? hoverCandle : lastCandle
  const activeChange = activeCandle ? (Number(activeCandle.close) - Number(activeCandle.open)) : 0
  const activeChangePct = activeCandle && Number(activeCandle.open) > 0
    ? (activeChange / Number(activeCandle.open)) * 100
    : 0
  const isPositive = activeChange >= 0

  useEffect(() => {
    if (!chartContainerRef.current) return

    const chart = createChart(chartContainerRef.current, {
      width: chartContainerRef.current.clientWidth,
      height,
      layout: {
        background: { type: ColorType.Solid, color: 'transparent' },
        textColor: '#9ca3af',
        fontSize: 11,
      },
      grid: {
        vertLines: { color: '#1f293740' },
        horzLines: { color: '#1f293760' },
      },
      crosshair: {
        mode: CrosshairMode.Normal,
        vertLine: { color: '#6b728080', width: 1, style: LineStyle.Dashed, labelBackgroundColor: '#374151' },
        horzLine: { color: '#6b728080', width: 1, style: LineStyle.Dashed, labelBackgroundColor: '#374151' },
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

    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor: '#10b981',
      downColor: '#ef4444',
      borderUpColor: '#10b981',
      borderDownColor: '#ef4444',
      wickUpColor: '#10b98190',
      wickDownColor: '#ef444490',
      lastValueVisible: true,
      priceLineVisible: true,
      priceLineWidth: 1,
      priceLineStyle: LineStyle.Solid,
    })

    const volumeSeries = chart.addSeries(HistogramSeries, {
      priceFormat: { type: 'volume' },
      priceScaleId: 'volume',
    })

    chart.priceScale('volume').applyOptions({
      scaleMargins: { top: 0.8, bottom: 0 },
    })

    chart.subscribeCrosshairMove((param) => {
      if (!param || !param.point || !param.time) {
        setIsHovering(false)
        return
      }
      const seriesData = param.seriesData.get(candleSeries)
      if (!seriesData) {
        setIsHovering(false)
        return
      }

      setHoverCandle({
        open: Number(seriesData.open || 0),
        high: Number(seriesData.high || 0),
        low: Number(seriesData.low || 0),
        close: Number(seriesData.close || 0),
      })
      setIsHovering(true)
    })

    chartRef.current = chart
    candleSeriesRef.current = candleSeries
    volumeSeriesRef.current = volumeSeries

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
      setHoverCandle(null)
      setIsHovering(false)
    }
  }, [height])

  useEffect(() => {
    if (!candleSeriesRef.current || !volumeSeriesRef.current || !candles || candles.length === 0) return

    const candleData = candles.map(c => ({
      time: Math.floor(c.time / 1000),
      open: Number(c.open || 0),
      high: Number(c.high || 0),
      low: Number(c.low || 0),
      close: Number(c.close || 0),
    }))

    const volumeData = candles.map(c => ({
      time: Math.floor(c.time / 1000),
      value: Number(c.volume || 0),
      color: Number(c.close || 0) >= Number(c.open || 0) ? '#10b98135' : '#ef444435',
    }))

    candleSeriesRef.current.setData(candleData)
    volumeSeriesRef.current.setData(volumeData)

    if (chartRef.current) {
      chartRef.current.timeScale().fitContent()
    }
  }, [candles])

  return (
    <div className="relative w-full">
      <div ref={chartContainerRef} className="w-full" />

      {activeCandle && (
        <div className="absolute top-3 left-3 right-3 pointer-events-none">
          <div className="bg-gray-900/85 border border-gray-700/70 backdrop-blur-sm rounded-lg px-3 py-2 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2">
            <div className="flex items-center gap-2 text-xs">
              <span className="font-bold text-white">{selectedCoin}/USDC</span>
              <span className="text-gray-500">•</span>
              <span className="text-gray-400 uppercase">{interval}</span>
              <span className={`font-bold ${isPositive ? 'text-green-400' : 'text-red-400'}`}>
                ${fmtPrice(activeCandle.close)}
              </span>
              <span className={`font-medium ${isPositive ? 'text-green-400' : 'text-red-400'}`}>
                {isPositive ? '+' : ''}{activeChangePct.toFixed(2)}%
              </span>
            </div>

            <div className="grid grid-cols-2 sm:grid-cols-4 gap-x-3 gap-y-1 text-[11px] font-mono">
              <span className="text-gray-400">O <span className="text-gray-200">{fmtPrice(activeCandle.open)}</span></span>
              <span className="text-gray-400">H <span className="text-green-400">{fmtPrice(activeCandle.high)}</span></span>
              <span className="text-gray-400">L <span className="text-red-400">{fmtPrice(activeCandle.low)}</span></span>
              <span className="text-gray-400">C <span className="text-white">{fmtPrice(activeCandle.close)}</span></span>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}