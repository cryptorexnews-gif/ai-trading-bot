<span className={`flex items-center gap-1 text-xs font-bold px-2 py-0.5 rounded ${
                    isLong ? 'bg-green-900/50 text-green-400' : 'bg-red-900/50 text-red-400'
                  }`}>
                    {isLong ? <TrendingUp size={10} /> : <TrendingDown size={10} />}
                    {pos.side}
                  </span>
                  {beActivated && (
                    <span className="flex items-center gap-1 text-[10px] font-bold px-1.5 py-0.5 rounded bg-cyan-900/50 text-cyan-400">
                      <CheckCircle size={10} />
                      BE
                    </span>
                  )}
                </div>
                <span className="text-xs text-gray-500">
                  Size: {pos.size}
                </span>
              </div>

              <div className="grid grid-cols-3 gap-3 text-xs">
                {/* Stop Loss */}
                <div className={`rounded-lg p-2 border ${
                  beActivated
                    ? 'bg-cyan-900/20 border-cyan-800/30'
                    : 'bg-red-900/20 border-red-800/30'
                }`}>
                  <div className={`font-semibold mb-1 flex items-center gap-1 ${
                    beActivated ? 'text-cyan-400' : 'text-red-400'
                  }`}>
                    {beActivated ? '🔒 Break-Even' : '🛑 Stop Loss'}
                  </div>
                  <div className="text-white font-mono">${sl.toFixed(2)}</div>
                  <div className={`text-[10px] ${beActivated ? 'text-cyan-400/60' : 'text-red-400/60'}`}>
                    {beActivated ? 'protected' : `-${slPct}%`}
                  </div>
                </div>

                {/* Entry */}
                <div className="bg-gray-700/30 rounded-lg p-2 border border-gray-600/30 text-center">
                  <div className="text-gray-400 font-semibold mb-1">Entry</div>
                  <div className="text-white font-mono">${entry.toFixed(2)}</div>
                  <div className="text-gray-500 text-[10px]">
                    {!beActivated && `BE@+${beActivationPct}%`}
                    {beActivated && '✓ secured'}
                  </div>
                </div>

                {/* Take Profit */}
                <div className="bg-green-900/20 rounded-lg p-2 border border-green-800/30">
                  <div className="text-green-400 font-semibold mb-1 flex items-center gap-1">
                    🎯 Take Profit
                  </div>
                  <div className="text-white font-mono">${tp.toFixed(2)}</div>
                  <div className="text-green-400/60 text-[10px]">+{tpPct}%</div>
                </div>
              </div>

              {/* Trailing Stop */}
              {pos.trailing_enabled && (
                <div className="mt-2 bg-blue-900/20 rounded-lg p-2 border border-blue-800/30 flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span className="text-blue-400 text-xs font-semibold">📈 Trailing Stop</span>
                    <span className="text-[10px] text-blue-300/60">
                      callback: {(parseFloat(pos.trailing_callback || 0) * 100).toFixed(1)}%
                    </span>
                  </div>
                  <div className="text-xs text-gray-400">
                    {pos.highest_tracked && (
                      <span>High: ${parseFloat(pos.highest_tracked).toFixed(2)}</span>
                    )}
                    {pos.lowest_tracked && (
                      <span>Low: ${parseFloat(pos.lowest_tracked).toFixed(2)}</span>
                    )}
                  </div>
                </div>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}