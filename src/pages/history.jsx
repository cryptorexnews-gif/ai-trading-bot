60%.">
import React from 'react'
import { useApi } from '../hooks/useApi'
import EquityChart from '../components/EquityChart'
import ExportButton from '../components/ExportButton'
import TradeHistory from '../components/TradeHistory'

export default function HistoryPage() {
  const { data: tradesData } = useApi('/trades?limit=100', 2000)
  const { data: perfData } = useApi('/performance', 2000)

  const trades = tradesData?.trades || []
  const equityCurve = perfData?.equity_curve || []
  const equitySnapshots = perfData?.equity_snapshots || []

  return (
    <div className="space-y-5">
      <EquityChart equityCurve={equityCurve} equitySnapshots={equitySnapshots} />

      <div>
        <div className="flex items-center justify-end mb-2">
          <ExportButton />
        </div>
        <TradeHistory trades={trades} minConfidence={0.6} />
      </div>
    </div>
  )
}