import React from 'react'
import { Outlet } from 'react-router-dom'
import { Activity } from 'lucide-react'
import { useApi } from '../hooks/useApi'
import useRealtimeStatus from '../hooks/useRealtimeStatus'
import StatusBadge from './StatusBadge'
import PageNav from './PageNav'

export default function AppShell() {
  const { data: wsStatusData, lastUpdated } = useRealtimeStatus()
  const { data: configData } = useApi('/config', 15000)

  const bot = wsStatusData?.bot || {}
  const mode = bot.execution_mode || configData?.execution_mode || 'live'
  const isRunning = bot.is_running || false
  const tradingPairsCount = configData?.trading_pairs_count || (configData?.trading_pairs || []).length || 0

  return (
    <div className="min-h-screen bg-gray-950 text-white">
      <header className="border-b border-gray-800 px-4 sm:px-6 py-4 bg-gray-950/80 backdrop-blur-sm sticky top-0 z-20">
        <div className="max-w-[1400px] mx-auto flex flex-col gap-3">
          <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
            <div className="flex items-center gap-3">
              <span className="text-2xl">🤖</span>
              <div>
                <h1 className="text-xl font-bold">Hyperliquid Trading Bot</h1>
                <p className="text-[10px] text-gray-500">Dashboard organizzata per sezioni • {tradingPairsCount} pairs</p>
              </div>
            </div>

            <div className="flex items-center gap-4">
              <StatusBadge isRunning={isRunning} mode={mode} lastUpdated={lastUpdated} />
              {bot.current_coin && !['idle', 'stopped', 'starting...'].includes(bot.current_coin) && (
                <span className="text-xs text-cyan-400 animate-pulse flex items-center gap-1">
                  <Activity size={12} />
                  {bot.current_coin}
                </span>
              )}
            </div>
          </div>

          <PageNav />
        </div>
      </header>

      <main className="max-w-[1400px] mx-auto px-4 sm:px-6 py-6">
        <Outlet />
      </main>
    </div>
  )
}