import React from 'react'
import { TrendingUp, TrendingDown } from 'lucide-react'

export default function PositionsTable({ positions }) {
  if (!positions || Object.keys(positions).length === 0) {
    return (
      <div className="bg-gray-900 rounded-xl p-6 border border-gray-800">
        <h3 className="text-lg font-semibold mb-4">Open Positions</h3>
        <p className="text-gray-500 text-sm">No open positions</p>
      </div>
    )
  }

  return (
    <div className="bg-gray-900 rounded-xl p-6 border border-gray-800">
      <h3 className="text-lg font-semibold mb-4">Open Positions</h3>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-gray-400 border-b border-gray-800">
              <th className="text-left py-2 px-2">Asset</th>
              <th className="text-left py-2 px-2">Side</th>
              <th className="text-right py-2 px-2">Size</th>
              <th className="text-right py-2 px-2">Entry</th>
              <th className="text-right py-2 px-2">PnL</th>
              <th className="text-right py-2 px-2">Margin</th>
            </tr>
          </thead>
          <tbody>
            {Object.entries(positions).map(([coin, pos]) => {
              const size = parseFloat(pos.size || 0)
              const isLong = size > 0
              const pnl = parseFloat(pos.unrealized_pnl || 0)
              const isPnlPositive = pnl >= 0

              return (
                <tr key={coin} className="border-b border-gray-800/50 hover:bg-gray-800/30">
                  <td className="py-3 px-2 font-bold">{coin}</td>
                  <td className="py-3 px-2">
                    <span className={`flex items-center gap-1 ${isLong ? 'text-green-400' : 'text-red-400'}`}>
                      {isLong ? <TrendingUp size={14} /> : <TrendingDown size={14} />}
                      {isLong ? 'LONG' : 'SHORT'}
                    </span>
                  </td>
                  <td className="py-3 px-2 text-right font-mono">{Math.abs(size).toFixed(4)}</td>
                  <td className="py-3 px-2 text-right font-mono">${parseFloat(pos.entry_price || 0).toFixed(2)}</td>
                  <td className={`py-3 px-2 text-right font-mono font-bold ${isPnlPositive ? 'text-green-400' : 'text-red-400'}`}>
                    {isPnlPositive ? '+' : ''}{pnl.toFixed(4)}
                  </td>
                  <td className="py-3 px-2 text-right font-mono">${parseFloat(pos.margin_used || 0).toFixed(2)}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}