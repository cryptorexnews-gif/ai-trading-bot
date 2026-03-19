import React from 'react'
import { TrendingUp, TrendingDown } from 'lucide-react'

export default function PositionsTable({ positions }) {
  if (!positions || Object.keys(positions).length === 0) {
    return (
      <div className="bg-gray-900 rounded-xl p-6 border border-gray-800">
        <h3 className="text-lg font-semibold mb-4">Open Positions</h3>
        <div className="flex flex-col items-center justify-center py-8 text-gray-500">
          <div className="text-4xl mb-2">📭</div>
          <p className="text-sm">No open positions</p>
        </div>
      </div>
    )
  }

  return (
    <div className="bg-gray-900 rounded-xl p-6 border border-gray-800">
      <h3 className="text-lg font-semibold mb-4">
        Open Positions
        <span className="text-sm font-normal text-gray-500 ml-2">
          ({Object.keys(positions).length})
        </span>
      </h3>
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
              const entryPrice = parseFloat(pos.entry_price || 0)
              const marginUsed = parseFloat(pos.margin_used || 0)
              const posValue = Math.abs(size) * entryPrice
              const leverage = marginUsed > 0 ? (posValue / marginUsed).toFixed(1) : '—'

              return (
                <tr key={coin} className="border-b border-gray-800/50 hover:bg-gray-800/30 transition-colors">
                  <td className="py-3 px-2">
                    <div className="font-bold">{coin}</div>
                    <div className="text-[10px] text-gray-500">{leverage}x</div>
                  </td>
                  <td className="py-3 px-2">
                    <span className={`flex items-center gap-1 text-xs font-bold ${isLong ? 'text-green-400' : 'text-red-400'}`}>
                      {isLong ? <TrendingUp size={12} /> : <TrendingDown size={12} />}
                      {isLong ? 'LONG' : 'SHORT'}
                    </span>
                  </td>
                  <td className="py-3 px-2 text-right font-mono text-xs">{Math.abs(size).toFixed(4)}</td>
                  <td className="py-3 px-2 text-right font-mono text-xs">${entryPrice.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</td>
                  <td className={`py-3 px-2 text-right font-mono text-xs font-bold ${isPnlPositive ? 'text-green-400' : 'text-red-400'}`}>
                    {isPnlPositive ? '+' : ''}{pnl.toFixed(4)}
                  </td>
                  <td className="py-3 px-2 text-right font-mono text-xs">${marginUsed.toFixed(2)}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}