import React from 'react'
import { Shield, ShieldAlert, ShieldCheck } from 'lucide-react'

const stateConfig = {
  closed: { icon: ShieldCheck, color: 'text-green-400', bg: 'bg-green-900/20 border-green-800/30', label: 'Healthy' },
  open: { icon: ShieldAlert, color: 'text-red-400', bg: 'bg-red-900/20 border-red-800/30', label: 'Open (Blocked)' },
  half_open: { icon: Shield, color: 'text-yellow-400', bg: 'bg-yellow-900/20 border-yellow-800/30', label: 'Recovering' },
}

export default function CircuitBreakerStatus({ breakers }) {
  if (!breakers || Object.keys(breakers).length === 0) {
    return (
      <div className="bg-gray-900 rounded-xl p-6 border border-gray-800">
        <h3 className="text-lg font-semibold mb-4">Circuit Breakers</h3>
        <div className="flex flex-col items-center justify-center py-6 text-gray-500">
          <ShieldCheck size={24} className="mb-2 text-green-500/50" />
          <p className="text-sm">All systems nominal</p>
        </div>
      </div>
    )
  }

  return (
    <div className="bg-gray-900 rounded-xl p-6 border border-gray-800">
      <h3 className="text-lg font-semibold mb-4">Circuit Breakers</h3>
      <div className="space-y-2">
        {Object.entries(breakers).map(([name, state]) => {
          const config = stateConfig[state.state] || stateConfig.closed
          const Icon = config.icon
          const friendlyName = name.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())

          return (
            <div key={name} className={`flex items-center justify-between p-3 rounded-lg border ${config.bg} transition-colors`}>
              <div className="flex items-center gap-3">
                <Icon size={16} className={config.color} />
                <span className="text-sm font-medium">{friendlyName}</span>
              </div>
              <div className="flex items-center gap-3">
                <span className={`text-xs font-bold ${config.color}`}>{config.label}</span>
                {state.failure_count > 0 && (
                  <span className="text-[10px] text-gray-500 bg-gray-800 px-1.5 py-0.5 rounded">
                    {state.failure_count}/{state.failure_threshold} failures
                  </span>
                )}
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}