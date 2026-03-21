import React from 'react'
import BotControlPanel from '../components/BotControlPanel'
import RuntimeControls from '../components/RuntimeControls'

export default function TradingPage() {
  return (
    <div className="space-y-5">
      <BotControlPanel />
      <RuntimeControls />
    </div>
  )
}