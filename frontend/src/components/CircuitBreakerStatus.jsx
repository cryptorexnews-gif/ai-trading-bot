import React from 'react'
import { Shield, ShieldAlert, ShieldCheck } from 'lucide-react'

const stateConfig = {
  closed: { icon: ShieldCheck, color: 'text-green-400', bg: 'bg-green-900/30', label: 'Healthy' },
  open: { icon: ShieldAlert, color: 'text-red-400', bg: 'bg-red-900/30', label: 'Open (Blocked)' },
  half_open: { icon: Shield, color: 'text-yellow-400', bg: 'bg-yellow-900/30', label: 'Recovering' },
}

export default function CircuitBreakerStatus({ breakers }) {
  if (!breakers || Object.keys(breakers).length === 0) {
    return null
  }

  return (
    <div className="bg-gray-900 rounded-xl p-6 border border-gray-800">
      <h3 className="text-lg font-semibold mb-4">Circuit Breakers</h3>
      <div className="space-y-3">
        {Object.entries(breakers).map(([name, state]) => {
          const config = stateConfig[state.state] || stateConfig.closed
          const Icon = config.icon

          return (
            <div key={name} className={`flex items-center justify-between p-3 rounded-lg ${config.bg}`}>
              <div className="flex items-center gap-3">
                <Icon size={18} className={config.color} />
                <span className="text-sm font-medium">{name}</span>
              </div>
              <div className="flex items-center gap-3">
                <span className={`text-xs font-bold ${config.color}`}>{config.label}</span>
                {state.failure_count > 0 && (
                  <span className="text-xs text-gray-500">
                    ({state.failure_count} failures)
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