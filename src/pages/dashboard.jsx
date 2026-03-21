import React from 'react'
import { Activity, BarChart3, Clock, DollarSign, TrendingUp, Zap } from 'lucide-react'
import { useApi } from '../hooks/useApi'
import ConnectionStatus from '../components/ConnectionStatus'
import DrawdownBar from '../components/DrawdownBar'
import StatCard from '../components/StatCard'
import TradingView from '../components/TradingView'

function safeNum(v, fallback = 0) {
  const n = parseFloat(v)
  return isNaN(n) ? fallback : n
}

export default function DashboardPage() {
  const { data: statusData, error: statusError, lastUpdated } = useApi('/status', 1000)
  const { data: portfolioData } = useApi('/portfolio', 1000)
  const { data: perfData } = useApi('/performance', 2000)
  const { data: configData } = useApi('/config', 5000)

  const bot = statusData?.bot || {}
  const portfolio = bot.portfolio || portfolioData?.portfolio || {}
  const metrics = statusData?.metrics || {}
  const stateInfo = statusData?.state || {}
  const perfSummary = perfData?.summary || {}
  const tradingPairs = configData?.trading_pairs || []

  const balance = safeNum(portfolio.total_balance)
  const available = safeNum(portfolio.available_balance)
  const unrealizedPnl = safeNum(portfolio.total_unrealized_pnl)
  const marginUsage = safeNum(portfolio.margin_usage)
  const positionCount = safeNum(portfolio.position_count)
  const maxDrawdown = parseFloat(configData?.max_drawdown_pct || '0.15')

  return (
    <div className="space-y-5">
      <ConnectionStatus isConnected={!statusError} lastUpdated={lastUpdated} />

      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
        <StatCard title="Balance" value={`$${balance.toFixed(2)}`} subtitle={`Avail: $${available.toFixed(2)}`} icon={DollarSign} color="green" />
        <StatCard title="Unrealized PnL" value={`$${unrealizedPnl.toFixed(4)}`} icon={TrendingUp} color={unrealizedPnl >= 0 ? 'green' : 'red'} />
        <StatCard title="Margin Usage" value={`${(marginUsage * 100).toFixed(1)}%`} subtitle={`${positionCount} positions`} icon={BarChart3} color={marginUsage > 0.8 ? 'red' : 'blue'} />
        <StatCard title="Trades" value={metrics.trades_executed_total || 0} subtitle={`${metrics.holds_total || 0} holds`} icon={Activity} color="purple" />
        <StatCard title="Win Rate" value={`${safeNum(perfSummary.win_rate).toFixed(1)}%`} subtitle={`${perfSummary.wins || 0}W / ${perfSummary.losses || 0}L`} icon={Zap} color={safeNum(perfSummary.win_rate) >= 50 ? 'green' : 'yellow'} />
        <StatCard title="Cycle" value={`#${bot.cycle_count || 0}`} subtitle={`${safeNum(bot.last_cycle_duration).toFixed(1)}s`} icon={Clock} color="cyan" />
      </div>

      <DrawdownBar peakValue={stateInfo.peak_portfolio_value} currentBalance={balance} maxDrawdownPct={maxDrawdown} />

      <TradingView tradingPairs={tradingPairs} />
    </div>
  )
}