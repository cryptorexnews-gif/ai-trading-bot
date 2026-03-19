import React from 'react'

const actionColors = {
  buy: 'bg-green-600',
  sell: 'bg-red-600',
  hold: 'bg-gray-600',
  close_position: 'bg-yellow-600',
  increase_position: 'bg-blue-600',
  reduce_position: 'bg-orange-600',
  change_leverage: 'bg-purple-600',
}

export default function TradeHistory({ trades }) {
  if (!trades || trades.length === 0) {
    return (
      <div className="bg-gray-900 rounded-xl p-6 border border-gray-800">
        <h3 className="text-lg font-semibold mb-4">Trade History</h3>
        <p className="text-gray-500 text-sm">No trades yet</p>
      </div>
    )
  }

  return (
    <div className="bg-gray-900 rounded-xl p-6 border border-gray-800">
      <h3 className="text-lg font-semibold mb-4">Trade History</h3>
      <div className="overflow-x-auto max-h-96 overflow-y-auto">
        <table className="w-full text-sm">
          <thead className="sticky top-0 bg-gray-900">
            <tr className="text-gray-400 border-b border-gray-800">
              <th className="text-left py-2 px-2">Time</th>
              <th className="text-left py-2 px-2">Asset</th>
              <th className="text-left py-2 px-2">Action</th>
              <th className="text-right py-2 px-2">Size</th>
              <th className="text-right py-2 px-2">Price</th>
              <th className="text-right py-2 px-2">Conf.</th>
              <th className="text-center py-2 px-2">Status</th>
              <th className="text-left py-2 px-2">Reasoning</th>
            </tr>
          </thead>
          <tbody>
            {trades.map((trade, idx) => {
              const time = trade.timestamp
                ? new Date(trade.timestamp * 1000).toLocaleTimeString()
                : '—'
              const bgColor = actionColors[trade.action] || 'bg-gray-600'

              return (
                <tr key={idx} className="border-b border-gray-800/50 hover:bg-gray-800/30">
                  <td className="py-2 px-2 text-gray-400 font-mono text-xs">{time}</td>
                  <td className="py-2 px-2 font-bold">{trade.coin}</td>
                  <td className="py-2 px-2">
                    <span className={`${bgColor} px-2 py-0.5 rounded text-xs font-bold uppercase`}>
                      {trade.action}
                    </span>
                  </td>
                  <td className="py-2 px-2 text-right font-mono">{trade.size}</td>
                  <td className="py-2 px-2 text-right font-mono">${parseFloat(trade.price || 0).toFixed(2)}</td>
                  <td className="py-2 px-2 text-right font-mono">
                    {(parseFloat(trade.confidence || 0) * 100).toFixed(0)}%
                  </td>
                  <td className="py-2 px-2 text-center">
                    {trade.success ? (
                      <span className="text-green-400">✓</span>
                    ) : (
                      <span className="text-red-400">✗</span>
                    )}
                  </td>
                  <td className="py-2 px-2 text-gray-400 text-xs max-w-xs truncate" title={trade.reasoning}>
                    {trade.reasoning || '—'}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}