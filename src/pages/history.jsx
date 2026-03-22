import React from 'react'
import { useApi } from '../hooks/useApi'
import EquityChart from '../components/EquityChart'
import ExportButton from '../components/ExportButton'
import TradeHistory from '../components/TradeHistory'

function safeNum(v, fallback = 0) {
  const n = parseFloat(v)
  return Number.isNaN(n) ? fallback : n
}

function getEffectiveThresholds(configData, runtimeData) {
  const strategyMode = String(runtimeData?.runtime_config?.strategy_mode || 'trend').toLowerCase()

  if (strategyMode === 'scalping') {
    return {
      minOpen: 0.66,
      minManage: 0.45,
    }
  }

  return {
    minOpen: safeNum(configData?.min_confidence_open, 0.72),
    minManage: safeNum(configData?.min_confidence_manage, 0.5),
  }
}

export default function HistoryPage() {
  const { data: tradesData } = useApi('/trades?limit=100', 2000)
  const { data: perfData } = useApi('/performance', 2000)
  const { data: configData } = useApi('/config', 5000)
  const { data: runtimeData } = useApi('/runtime-config', 5000)

  const trades = tradesData?.trades || []
  const equityCurve = perfData?.equity_curve || []
  const equitySnapshots = perfData?.equity_snapshots || []

  const { minOpen, minManage } = getEffectiveThresholds(configData, runtimeData)

  return (
    <div className="space-y-5">
      <EquityChart equityCurve={equityCurve} equitySnapshots={equitySnapshots} />

      <div>
        <div className="flex items-center justify-end mb-2">
          <ExportButton />
        </div>
        <TradeHistory
          trades={trades}
          minConfidenceOpen={minOpen}
          minConfidenceManage={minManage}
        />
      </div>
    </div>
  )
}