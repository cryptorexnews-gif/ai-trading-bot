import React from 'react'
import { WifiOff } from 'lucide-react'

export default function ConnectionStatus({ isConnected, lastUpdated }) {
  if (isConnected) return null

  return (
    <div className="bg-red-900/30 border border-red-700/50 rounded-xl p-4 flex items-center gap-3">
      <WifiOff className="text-red-400 shrink-0" size={20} />
      <div>
        <span className="text-sm text-red-300 font-medium">API Server Not Running</span>
        <p className="text-xs text-red-400/70 mt-0.5">
          Start the Python API server with <code className="bg-gray-800 px-1.5 py-0.5 rounded text-red-300">python api_server.py</code> on port 5000.
          {lastUpdated && (
            <span> Last data received: {lastUpdated.toLocaleTimeString()}</span>
          )}
        </p>
      </div>
    </div>
  )
}