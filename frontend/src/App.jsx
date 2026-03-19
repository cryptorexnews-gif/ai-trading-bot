import React from 'react'
import {
  Activity, DollarSign, TrendingUp, BarChart3,
  Zap, AlertTriangle, Clock, Layers
} from 'lucide-react'
import { useApi } from './hooks/useApi'
import StatusBadge from './components/StatusBadge'
import StatCard from './components/StatCard'
import PositionsTable from './components/PositionsTable'
import TradeHistory from './components/TradeHistory'
import EquityChart from './components/EquityChart'
import CircuitBreakerStatus from './components/CircuitBreakerStatus'
import LogViewer from './components/LogViewer'

export default function App() {
  const { data: statusData, loading: statusLoading, error: statusError } = useApi('/status', 5000)
  const { data: portfolioData } = useApi('/portfolio', 5000)
  const { data: tradesData } = useApi('/trades?limit=50', 10000)
  const { data: perfData } = useApi('/performance', 10000)
  const { data: logsData } = useApi('/logs?limit=50', 8000)
  const { data: configData } = useApi('/config', 30000)

  const bot = statusData?.bot || {}
  const portfolio = bot.portfolio || portfolioData?.portfolio || {}
  const positions = portfolio.positions || {}
  const metrics = statusData?.metrics || {}
  const breakers = statusData?.circuit_breakers || {}
  const stateInfo = statusData?.state || {}
  const trades = tradesData?.trades || []
  const perfSummary = perfData?.summary || {}
  const equityCurve = perfData?.equity_curve || []
  const logs = logsData?.logs || []

  const isConnected = !statusError
  const isRunning = bot.is_running || false
  const mode = bot.execution_mode || configData?.execution_mode || 'paper'

  return (
    <div className="min-h-screen bg-gray-950 text-white">
      {/* Header */}
      <header className="border-b border-gray-800 px-4 sm:px-6 py-4">
        <div className="max-w-7xl mx-auto flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <span className="text-2xl">🤖</span>
            <div>
              <h1 className="text-xl font-bold">Hyperliquid Trading Bot</h1>
              <p className="text-xs text-gray-500">
                Powered by Claude Opus 4.6 • Hyperliquid-only data
              </p>
            </div>
          </div>
          <div className="flex items-center gap-4">
            {!isConnected && (
              <span className="text-red-400 text-sm flex items-center gap-1">
                <AlertTriangle size={14} /> API Disconnected
              </span>
            )}
            <StatusBadge isRunning={isRunning} mode={mode} />
            {bot.current_coin && bot.current_coin !== 'idle' && bot.current_coin !== 'stopped' && (
              <span className="text-xs text-cyan-400 animate-pulse">
                Analyzing {bot.current_coin}...
              </span>
            )}
          </div>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-4 sm:px-6 py-6 space-y-6">
        {/* Stats Grid */}
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
          <StatCard
            title="Balance"
            value={`$${(portfolio.total_balance || 0).toFixed(2)}`}
            subtitle={`Available: $${(portfolio.available_balance || 0).toFixed(2)}`}
            icon={DollarSign}
            color="green"
          />
          <StatCard
            title="Unrealized PnL"
            value={`$${(portfolio.total_unrealized_pnl || 0).toFixed(4)}`}
            icon={TrendingUp}
            color={(portfolio.total_unrealized_pnl || 0) >= 0 ? 'green' : 'red'}
          />
          <StatCard
            title="Margin Usage"
            value={`${((portfolio.margin_usage || 0) * 100).toFixed(1)}%`}
            subtitle={`${portfolio.position_count || 0} positions`}
            icon={BarChart3}
            color={(portfolio.margin_usage || 0) > 0.8 ? 'red' : 'blue'}
          />
          <StatCard
            title="Trades"
            value={metrics.trades_executed_total || 0}
            subtitle={`${metrics.holds_total || 0} holds`}
            icon={Activity}
            color="purple"
          />
          <StatCard
            title="Win Rate"
            value={`${(perfSummary.win_rate || 0).toFixed(1)}%`}
            subtitle={`${perfSummary.wins || 0}W / ${perfSummary.losses || 0}L`}
            icon={Zap}
            color={(perfSummary.win_rate || 0) >= 50 ? 'green' : 'yellow'}
          />
          <StatCard
            title="Cycle"
            value={`#${bot.cycle_count || 0}`}
            subtitle={`${(bot.last_cycle_duration || 0).toFixed(1)}s`}
            icon={Clock}
            color="cyan"
          />
        </div>

        {/* Risk Alerts */}
        {(stateInfo.consecutive_losses > 2 || stateInfo.consecutive_failed_cycles > 0) && (
          <div className="bg-yellow-900/20 border border-yellow-700 rounded-xl p-4 flex items-center gap-3">
            <AlertTriangle className="text-yellow-400 shrink-0" size={20} />
            <div className="text-sm">
              {stateInfo.consecutive_losses > 2 && (
                <span className="text-yellow-300">
                  ⚠️ {stateInfo.consecutive_losses} consecutive losses — bot is being more conservative.
                </span>
              )}
              {stateInfo.consecutive_failed_cycles > 0 && (
                <span className="text-red-300 ml-2">
                  🔴 {stateInfo.consecutive_failed_cycles} failed cycles.
                </span>
              )}
            </div>
          </div>
        )}

        {bot.error && (
          <div className="bg-red-900/20 border border-red-700 rounded-xl p-4 flex items-center gap-3">
            <AlertTriangle className="text-red-400 shrink-0" size={20} />
            <span className="text-sm text-red-300">{bot.error}</span>
          </div>
        )}

        {/* Charts & Positions */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <EquityChart equityCurve={equityCurve} />
          <PositionsTable positions={positions} />
        </div>

        {/* Trade History */}
        <TradeHistory trades={trades} />

        {/* Bottom Row */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <CircuitBreakerStatus breakers={breakers} />
          <LogViewer logs={logs} />
        </div>

        {/* Footer */}
        <footer className="text-center text-xs text-gray-600 py-4 border-t border-gray-800">
          Hyperliquid Trading Bot Dashboard • Model: {configData?.llm_model || 'anthropic/claude-opus-4.6'} •
          Pairs: {(configData?.trading_pairs || []).join(', ')} •
          Max Leverage: {configData?.max_leverage || '10'}x
        </footer>
      </main>
    </div>
  )
}