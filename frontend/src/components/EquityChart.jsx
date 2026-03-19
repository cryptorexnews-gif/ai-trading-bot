import React, { useMemo } from 'react'
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  LineChart, Line
} from 'recharts'

function EquityTooltip({ active, payload, label }) {
  if (!active || !payload || !payload.length) return null
  const data = payload[0].payload
  return (
    <div className="bg-gray-800 border border-gray-700 rounded-lg p-3 shadow-xl text-xs">
      <div className="text-gray-400 mb-1">{label}</div>
      <div className="text-white font-bold">${parseFloat(data.total_value || 0).toFixed(2)}</div>
      <div className="text-gray-400 mt-1">
        Balance: ${parseFloat(data.balance || 0).toFixed(2)}
      </div>
      <div className={`${parseFloat(data.unrealized_pnl || 0) >= 0 ? 'text-green-400' : 'text-red-400'}`}>
        PnL: ${parseFloat(data.unrealized_pnl || 0).toFixed(4)}
      </div>
      {data.position_count !== undefined && (
        <div className="text-gray-500">Positions: {data.position_count}</div>
      )}
    </div>
  )
}

function ActivityTooltip({ active, payload, label }) {
  if (!active || !payload || !payload.length) return null
  const data = payload[0].payload
  return (
    <div className="bg-gray-800 border border-gray-700 rounded-lg p-3 shadow-xl text-xs">
      <div className="text-gray-400 mb-1">{label}</div>
      <div className="text-white font-bold">${parseFloat(data.notional || 0).toFixed(2)} notional</div>
      {data.coin && (
        <div className="text-gray-300 mt-1">
          <span className={data.action === 'buy' ? 'text-green-400' : data.action === 'sell' ? 'text-red-400' : 'text-gray-400'}>
            {(data.action || '').toUpperCase()}
          </span>
          {' '}{data.coin}
        </div>
      )}
    </div>
  )
}

export default function EquityChart({ equityCurve, equitySnapshots }) {
  const hasSnapshots = equitySnapshots && equitySnapshots.length > 2

  const snapshotData = useMemo(() => {
    if (!hasSnapshots) return []
    return equitySnapshots.map((point) => ({
      time: point.timestamp
        ? new Date(point.timestamp * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
        : '',
      total_value: parseFloat(point.total_value || 0),
      balance: parseFloat(point.balance || 0),
      unrealized_pnl: parseFloat(point.unrealized_pnl || 0),
      position_count: point.position_count || 0,
    }))
  }, [equitySnapshots, hasSnapshots])

  const activityData = useMemo(() => {
    if (!equityCurve || equityCurve.length === 0) return []
    return equityCurve.map((point, idx) => ({
      index: idx,
      time: point.timestamp
        ? new Date(point.timestamp * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
        : '',
      notional: parseFloat(point.notional || 0),
      coin: point.coin,
      action: point.action,
    }))
  }, [equityCurve])

  const hasNoData = !hasSnapshots && (!equityCurve || equityCurve.length === 0)

  if (hasNoData) {
    return (
      <div className="bg-gray-900 rounded-xl p-6 border border-gray-800">
        <h3 className="text-lg font-semibold mb-4">Portfolio Equity</h3>
        <div className="flex flex-col items-center justify-center py-8 text-gray-500">
          <div className="text-4xl mb-2">📊</div>
          <p className="text-sm">No data yet — equity curve will appear after first cycle</p>
        </div>
      </div>
    )
  }

  // Show real equity curve if we have snapshots
  if (hasSnapshots) {
    const minValue = Math.min(...snapshotData.map(d => d.total_value)) * 0.999
    const maxValue = Math.max(...snapshotData.map(d => d.total_value)) * 1.001

    return (
      <div className="bg-gray-900 rounded-xl p-6 border border-gray-800">
        <h3 className="text-lg font-semibold mb-1">Portfolio Equity</h3>
        <p className="text-[10px] text-gray-500 mb-3">
          Real portfolio value over time ({snapshotData.length} snapshots)
        </p>
        <ResponsiveContainer width="100%" height={250}>
          <AreaChart data={snapshotData}>
            <defs>
              <linearGradient id="colorEquity" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#10b981" stopOpacity={0.4} />
                <stop offset="95%" stopColor="#10b981" stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
            <XAxis dataKey="time" stroke="#4b5563" fontSize={10} tickLine={false} />
            <YAxis
              stroke="#4b5563"
              fontSize={10}
              tickLine={false}
              tickFormatter={(v) => `$${v.toFixed(0)}`}
              domain={[minValue, maxValue]}
            />
            <Tooltip content={<EquityTooltip />} />
            <Area
              type="monotone"
              dataKey="total_value"
              stroke="#10b981"
              fillOpacity={1}
              fill="url(#colorEquity)"
              strokeWidth={2}
              dot={false}
              activeDot={{ r: 4, fill: '#10b981', stroke: '#fff', strokeWidth: 2 }}
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    )
  }

  // Fallback: show activity timeline
  return (
    <div className="bg-gray-900 rounded-xl p-6 border border-gray-800">
      <h3 className="text-lg font-semibold mb-1">Activity Timeline</h3>
      <p className="text-[10px] text-gray-500 mb-3">Trade notional values</p>
      <ResponsiveContainer width="100%" height={250}>
        <AreaChart data={activityData}>
          <defs>
            <linearGradient id="colorNotional" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.4} />
              <stop offset="95%" stopColor="#3b82f6" stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
          <XAxis dataKey="time" stroke="#4b5563" fontSize={10} tickLine={false} />
          <YAxis stroke="#4b5563" fontSize={10} tickLine={false} tickFormatter={(v) => `$${v}`} />
          <Tooltip content={<ActivityTooltip />} />
          <Area
            type="monotone"
            dataKey="notional"
            stroke="#3b82f6"
            fillOpacity={1}
            fill="url(#colorNotional)"
            strokeWidth={2}
            dot={false}
            activeDot={{ r: 4, fill: '#3b82f6', stroke: '#fff', strokeWidth: 2 }}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  )
}