import React, { useEffect, useRef } from 'react'
import { createChart, ColorType, CrosshairMode, LineStyle, CandlestickSeries, HistogramSeries } from 'lightweight-charts'

export default function CandlestickChart({ candles, height = 500 }) {
  const chartContainerRef = useRef(null)
  const chartRef = useRef(null)
  const candleSeriesRef = useRef(null)
  const volumeSeriesRef = useRef(null)

  // Create chart once, recreate if height changes
  useEffect(() => {
    if (!chartContainerRef.current) return

    const chart = createChart(chartContainerRef.current, {
      width: chartContainerRef.current.clientWidth,
      height,
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
        vertLine: { color: '#6b728050', width: 1, style: LineStyle.Dashed, labelBackgroundColor: '#374151' },
        horzLine: { color: '#6b728050', width: 1, style: LineStyle.Dashed, labelBackgroundColor: '#374151' },
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
      wickUpColor: '#10b98180',
      wickDownColor: '#ef444480',
    })

    const volumeSeries = chart.addSeries(HistogramSeries, {
      priceFormat: { type: 'volume' },
      priceScaleId: 'volume',
    })

    chart.priceScale('volume').applyOptions({
      scaleMargins: { top: 0.8, bottom: 0 },
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
    }
  }, [height])

  // Update data when candles change
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

    if (chartRef.current) {
      chartRef.current.timeScale().fitContent()
    }
  }, [candles])

  return <div ref={chartContainerRef} className="w-full" />
}