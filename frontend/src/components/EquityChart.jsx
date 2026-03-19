import React from 'react'
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer
} from 'recharts'

function CustomTooltip({ active, payload, label }) {
  if (!active || !payload || !payload.length) return null
  const data = payload[0].payload
  return (
    <div className="bg-gray-800 border border-gray-700 rounded-lg p-3 shadow-xl text-xs">
      <div className="text-gray-400 mb-1">{label}</div>
      <div className="text-white font-bold">${data.notional.toFixed(2)} notional</div>
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

export default function EquityChart({ equityCurve }) {
  if (!equityCurve || equityCurve.length === 0) {
    return (
      <div className="bg-gray-900 rounded-xl p-6 border border-gray-800">
        <h3 className="text-lg font-semibold mb-4">Activity Timeline</h3>
        <div className="flex flex-col items-center justify-center py-8 text-gray-500">
          <div className="text-4xl mb-2">📊</div>
          <p className="text-sm">No activity data yet</p>
        </div>
      </div>
    )
  }

  const chartData = equityCurve.map((point, idx) => ({
    index: idx,
    time: point.timestamp
      ? new Date(point.timestamp * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
      : '',
    notional: parseFloat(point.notional || 0),
    coin: point.coin,
    action: point.action,
  }))

  return (
    <div className="bg-gray-900 rounded-xl p-6 border border-gray-800">
      <h3 className="text-lg font-semibold mb-4">Activity Timeline</h3>
      <ResponsiveContainer width="100%" height={250}>
        <AreaChart data={chartData}>
          <defs>
            <linearGradient id="colorNotional" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.4} />
              <stop offset="95%" stopColor="#3b82f6" stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
          <XAxis dataKey="time" stroke="#4b5563" fontSize={10} tickLine={false} />
          <YAxis stroke="#4b5563" fontSize={10} tickLine={false} tickFormatter={(v) => `$${v}`} />
          <Tooltip content={<CustomTooltip />} />
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