import React from 'react'
import { useApi } from '../hooks/useApi'
import EquityChart from '../components/EquityChart'
import ExportButton from '../components/ExportButton'
import TradeHistory from '../components/TradeHistory'

function safeNum(v, fallback = 0) {
  const n = parseFloat(v)
  return Number.isNaN(n) ? fallback : n
}

export default function HistoryPage() {
  const { data: tradesData } = useApi('/trades?limit=100', 2000)
  const { data: perfData } = useApi('/performance', 2000)
  const { data: configData } = useApi('/config', 5000)

  const trades = tradesData?.trades || []
  const equityCurve = perfData?.equity_curve || []
  const equitySnapshots = perfData?.equity_snapshots || []
  const minConfidenceOpen = safeNum(configData?.min_confidence_open, 0.72)
  const minConfidenceManage = safeNum(configData?.min_confidence_manage, 0.5)

  return (
    <div className="space-y-5">
      <EquityChart equityCurve={equityCurve} equitySnapshots={equitySnapshots} />

      <div>
        <div className="flex items-center justify-end mb-2">
          <ExportButton />
        </div>
        <TradeHistory
          trades={trades}
          minConfidenceOpen={minConfidenceOpen}
          minConfidenceManage={minConfidenceManage}
        />
      </div>
    </div>
  )
}