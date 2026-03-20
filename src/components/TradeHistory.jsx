import React, { useState, useMemo } from 'react'

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
  const [filterCoin, setFilterCoin] = useState('all')
  const [expandedIdx, setExpandedIdx] = useState(null)

  const coins = useMemo(() => {
    if (!trades) return []
    const unique = [...new Set(trades.map(t => t.coin).filter(Boolean))]
    return unique.sort()
  }, [trades])

  const filteredTrades = useMemo(() => {
    if (!trades) return []
    if (filterCoin === 'all') return trades
    return trades.filter(t => t.coin === filterCoin)
  }, [trades, filterCoin])

  if (!trades || trades.length === 0) {
    return (
      <div className="bg-gray-900 rounded-xl p-6 border border-gray-800">
        <h3 className="text-lg font-semibold mb-4">Trade History</h3>
        <div className="flex flex-col items-center justify-center py-8 text-gray-500">
          <div className="text-4xl mb-2">📋</div>
          <p className="text-sm">No trades yet</p>
        </div>
      </div>
    )
  }

  return (
    <div className="bg-gray-900 rounded-xl p-6 border border-gray-800">
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between mb-4 gap-2">
        <h3 className="text-lg font-semibold">
          Trade History
          <span className="text-sm font-normal text-gray-500 ml-2">({filteredTrades.length})</span>
        </h3>
        <div className="flex items-center gap-2">
          <span className="text-xs text-gray-500">Filter:</span>
          <select
            value={filterCoin}
            onChange={(e) => setFilterCoin(e.target.value)}
            className="bg-gray-800 border border-gray-700 rounded px-2 py-1 text-xs text-white focus:outline-none focus:border-blue-500"
          >
            <option value="all">All Coins</option>
            {coins.map(coin => (
              <option key={coin} value={coin}>{coin}</option>
            ))}
          </select>
        </div>
      </div>
      <div className="overflow-x-auto max-h-[400px] overflow-y-auto">
        <table className="w-full text-sm">
          <thead className="sticky top-0 bg-gray-900 z-10">
            <tr className="text-gray-400 border-b border-gray-800">
              <th className="text-left py-2 px-2">Time</th>
              <th className="text-left py-2 px-2">Asset</th>
              <th className="text-left py-2 px-2">Action</th>
              <th className="text-right py-2 px-2">Size</th>
              <th className="text-right py-2 px-2">Price</th>
              <th className="text-right py-2 px-2">Conf.</th>
              <th className="text-center py-2 px-2">Mode</th>
              <th className="text-center py-2 px-2">Status</th>
            </tr>
          </thead>
          <tbody>
            {filteredTrades.map((trade, idx) => {
              const tradeTime = trade.timestamp
                ? new Date(trade.timestamp * 1000).toLocaleTimeString()
                : '—'
              const tradeDate = trade.timestamp
                ? new Date(trade.timestamp * 1000).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
                : ''
              const bgColor = actionColors[trade.action] || 'bg-gray-600'
              const isExpanded = expandedIdx === idx

              return (
                <React.Fragment key={idx}>
                  <tr
                    className="border-b border-gray-800/50 hover:bg-gray-800/30 transition-colors cursor-pointer"
                    onClick={() => setExpandedIdx(isExpanded ? null : idx)}
                  >
                    <td className="py-2 px-2 text-gray-400 font-mono text-xs">
                      <div>{tradeTime}</div>
                      <div className="text-[10px] text-gray-600">{tradeDate}</div>
                    </td>
                    <td className="py-2 px-2 font-bold">{trade.coin}</td>
                    <td className="py-2 px-2">
                      <span className={`${bgColor} px-2 py-0.5 rounded text-[10px] font-bold uppercase`}>
                        {(trade.action || '').replace('_', ' ')}
                      </span>
                    </td>
                    <td className="py-2 px-2 text-right font-mono text-xs">{trade.size}</td>
                    <td className="py-2 px-2 text-right font-mono text-xs">
                      ${parseFloat(trade.price || 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                    </td>
                    <td className="py-2 px-2 text-right font-mono text-xs">
                      {(parseFloat(trade.confidence || 0) * 100).toFixed(0)}%
                    </td>
                    <td className="py-2 px-2 text-center">
                      <span className={`text-[10px] px-1.5 py-0.5 rounded ${
                        trade.mode === 'live' ? 'bg-red-900/50 text-red-300' : 'bg-gray-700 text-gray-400'
                      }`}>
                        {trade.mode || 'paper'}
                      </span>
                    </td>
                    <td className="py-2 px-2 text-center">
                      {trade.success ? (
                        <span className="text-green-400 text-lg">✓</span>
                      ) : (
                        <span className="text-red-400 text-lg">✗</span>
                      )}
                    </td>
                  </tr>
                  {isExpanded && trade.reasoning && (
                    <tr className="bg-gray-800/40">
                      <td colSpan={8} className="px-4 py-3">
                        <div className="text-xs text-gray-300">
                          <span className="text-gray-500 font-semibold">AI Reasoning: </span>
                          {trade.reasoning}
                        </div>
                      </td>
                    </tr>
                  )}
                </React.Fragment>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}