import React from 'react'
import { useApi } from '../hooks/useApi'
import BotControlPanel from '../components/BotControlPanel'
import RuntimeControls from '../components/RuntimeControls'
import TradingView from '../components/TradingView'

export default function TradingPage() {
  const { data: configData } = useApi('/config', 30000)
  const tradingPairs = configData?.trading_pairs || []

  return (
    <div className="space-y-5">
      <BotControlPanel />
      <RuntimeControls />
      <TradingView tradingPairs={tradingPairs} />
    </div>
  )
}