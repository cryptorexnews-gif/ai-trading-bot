{/* Footer */}
        <footer className="text-center text-[10px] text-gray-600 py-4 border-t border-gray-800/50">
          <div className="mb-1">
            Hyperliquid Trading Bot • {configData?.llm_model || 'claude-opus-4.6'} •
            {' '}{tradingPairsCount} pairs •
            {' '}SL: {((parseFloat(configData?.trend_sl_pct || '0.05')) * 100).toFixed(0)}% •
            {' '}TP: {((parseFloat(configData?.trend_tp_pct || '0.10')) * 100).toFixed(0)}% •
            {' '}Trailing: {configData?.enable_trailing_stop === 'true' ? 'ON' : 'OFF'} •
            {' '}BE: @{((parseFloat(configData?.trend_break_even_activation_pct || '0.03')) * 100).toFixed(1)}%
          </div>
          <div className="text-gray-700">
            Trend Strategy: 4H Primary + 1D Main + 1H Entry Timing • Max {configData?.max_trend_positions || 2} positions
          </div>
        </footer>