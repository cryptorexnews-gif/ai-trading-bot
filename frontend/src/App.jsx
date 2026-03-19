import React from 'react'
import {
  Activity, DollarSign, TrendingUp, BarChart3,
  Zap, AlertTriangle, Clock
} from 'lucide-react'
import { useApi } from './hooks/useApi'
import StatusBadge from './components/StatusBadge'
import StatCard from './components/StatCard'
import PositionsTable from './components/PositionsTable'
import ManagedPositions from './components/ManagedPositions'
import TradeHistory from './components/TradeHistory'
import EquityChart from './components/EquityChart'
import PriceChart from './components/PriceChart'
import OrderBook from './components/OrderBook'
import CircuitBreakerStatus from './components/CircuitBreakerStatus'
import LogViewer from './components/LogViewer'
import DrawdownBar from './components/DrawdownBar'
import ConnectionStatus from './components/ConnectionStatus'
import ExportButton from './components/ExportButton'

export default function App() {
  const { data: statusData, error: statusError, lastUpdated: statusUpdated } = useApi('/status', 5000)
  const { data: portfolioData } = useApi('/portfolio', 5000)
  const { data: tradesData } = useApi('/trades?limit=50', 10000)
  const { data: perfData } = useApi('/performance', 10000)
  const { data: logsData } = useApi('/logs?limit=50', 8000)
  const { data: configData } = useApi('/config', 30000)
  const { data: managedData } = useApi('/managed-positions', 5000)

  const bot = statusData?.bot || {}
  const portfolio = bot.portfolio || portfolioData?.portfolio || {}
  const positions = portfolio.positions || {}
  const metrics = statusData?.metrics || {}
  const breakers = statusData?.circuit_breakers || {}
  const stateInfo = statusData?.state || {}
  const trades = tradesData?.trades || []
  const perfSummary = perfData?.summary || {}
  const equityCurve = perfData?.equity_curve || []
  const equitySnapshots = perfData?.equity_snapshots || []
  const logs = logsData?.logs || []
  const managedPositions = managedData?.managed_positions || []

  const isConnected = !statusError
  const isRunning = bot.is_running || false
  const mode = bot.execution_mode || configData?.execution_mode || 'paper'
  const maxDrawdown = parseFloat(configData?.max_drawdown_pct || '0.15')
  const tradingPairs = configData?.trading_pairs || []
  const tradingPairsCount = configData?.trading_pairs_count || tradingPairs.length

  return (
    <div className="min-h-screen bg-gray-950 text-white">
      {/* Header */}
      <header className="border-b border-gray-800 px-4 sm:px-6 py-4 bg-gray-950/80 backdrop-blur-sm sticky top-0 z-20">
        <div className="max-w-7xl mx-auto flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <span className="text-2xl">🤖</span>
            <div>
              <h1 className="text-xl font-bold">Hyperliquid Trading Bot</h1>
              <p className="text-[10px] text-gray-500">
                Claude Opus 4.6 • {tradingPairsCount} pairs • SL/TP/Trailing/BE • Multi-TF • Correlation
              </p>
            </div>
          </div>
          <div className="flex items-center gap-4">
            <StatusBadge isRunning={isRunning} mode={mode} lastUpdated={statusUpdated} />
            {bot.current_coin && bot.current_coin !== 'idle' && bot.current_coin !== 'stopped' && bot.current_coin !== 'starting...' && (
              <span className="text-xs text-cyan-400 animate-pulse flex items-center gap-1">
                <Activity size={12} />
                Analyzing {bot.current_coin}
              </span>
            )}
          </div>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-4 sm:px-6 py-6 space-y-5">
        <ConnectionStatus isConnected={isConnected} lastUpdated={statusUpdated} />

        {/* Stats Grid */}
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
          <StatCard
            title="Balance"
            value={`$${(portfolio.total_balance || 0).toFixed(2)}`}
            subtitle={`Avail: $${(portfolio.available_balance || 0).toFixed(2)}`}
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

        {/* Drawdown Bar */}
        <DrawdownBar
          peakValue={stateInfo.peak_portfolio_value}
          currentBalance={portfolio.total_balance}
          maxDrawdownPct={maxDrawdown}
        />

        {/* Risk Alerts */}
        {(stateInfo.consecutive_losses > 2 || stateInfo.consecutive_failed_cycles > 0) && (
          <div className="bg-yellow-900/20 border border-yellow-700/50 rounded-xl p-4 flex items-center gap-3">
            <AlertTriangle className="text-yellow-400 shrink-0" size={20} />
            <div className="text-sm space-x-2">
              {stateInfo.consecutive_losses > 2 && (
                <span className="text-yellow-300">
                  ⚠️ {stateInfo.consecutive_losses} consecutive losses — bot is being more conservative.
                </span>
              )}
              {stateInfo.consecutive_failed_cycles > 0 && (
                <span className="text-red-300">
                  🔴 {stateInfo.consecutive_failed_cycles} failed cycles.
                </span>
              )}
            </div>
          </div>
        )}

        {bot.error && (
          <div className="bg-red-900/20 border border-red-700/50 rounded-xl p-4 flex items-center gap-3">
            <AlertTriangle className="text-red-400 shrink-0" size={20} />
            <span className="text-sm text-red-300">{bot.error}</span>
          </div>
        )}

        {/* Price Chart & Order Book */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
          <div className="lg:col-span-2">
            <PriceChart tradingPairs={tradingPairs} />
          </div>
          <div>
            <OrderBook tradingPairs={tradingPairs} />
          </div>
        </div>

        {/* Equity & Positions */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
          <EquityChart equityCurve={equityCurve} equitySnapshots={equitySnapshots} />
          <PositionsTable positions={positions} />
        </div>

        {/* Managed Positions (SL/TP/Trailing/Break-Even) */}
        <ManagedPositions positions={managedPositions} />

        {/* Trade History with Export */}
        <div>
          <div className="flex items-center justify-between mb-2">
            <div />
            <ExportButton />
          </div>
          <TradeHistory trades={trades} />
        </div>

        {/* Bottom Row */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
          <CircuitBreakerStatus breakers={breakers} />
          <LogViewer logs={logs} />
        </div>

        {/* Footer */}
        <footer className="text-center text-[10px] text-gray-600 py-4 border-t border-gray-800/50">
          <div className="mb-1">
            Hyperliquid Trading Bot Dashboard • {configData?.llm_model || 'claude-opus-4.6'} •
            {' '}{tradingPairsCount} pairs •
            {' '}SL: {((parseFloat(configData?.default_sl_pct || '0.03')) * 100).toFixed(0)}% •
            {' '}TP: {((parseFloat(configData?.default_tp_pct || '0.05')) * 100).toFixed(0)}% •
            {' '}Trailing: {configData?.enable_trailing_stop === 'true' ? 'ON' : 'OFF'} •
            {' '}BE: @{((parseFloat(configData?.break_even_activation_pct || '0.015')) * 100).toFixed(1)}% •
            {' '}Adaptive: {configData?.enable_adaptive_cycle === 'true' ? 'ON' : 'OFF'}
          </div>
          <div className="text-gray-700">
            {tradingPairs.length > 0 && tradingPairs.join(' • ')}
          </div>
        </footer>
      </main>
    </div>
  )
}