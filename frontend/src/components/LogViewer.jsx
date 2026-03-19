import React from 'react'

const levelColors = {
  INFO: 'text-blue-400',
  WARNING: 'text-yellow-400',
  ERROR: 'text-red-400',
  DEBUG: 'text-gray-500',
  CRITICAL: 'text-red-600 font-bold',
}

export default function LogViewer({ logs }) {
  if (!logs || logs.length === 0) {
    return (
      <div className="bg-gray-900 rounded-xl p-6 border border-gray-800">
        <h3 className="text-lg font-semibold mb-4">Recent Logs</h3>
        <p className="text-gray-500 text-sm">No logs available</p>
      </div>
    )
  }

  return (
    <div className="bg-gray-900 rounded-xl p-6 border border-gray-800">
      <h3 className="text-lg font-semibold mb-4">Recent Logs</h3>
      <div className="max-h-80 overflow-y-auto space-y-1 font-mono text-xs">
        {logs.slice(0, 50).map((log, idx) => {
          const level = log.level || 'INFO'
          const color = levelColors[level] || 'text-gray-400'
          const timestamp = log.timestamp
            ? new Date(log.timestamp).toLocaleTimeString()
            : ''
          const message = log.message || JSON.stringify(log)

          return (
            <div key={idx} className="flex gap-2 hover:bg-gray-800/30 px-2 py-0.5 rounded">
              <span className="text-gray-600 shrink-0">{timestamp}</span>
              <span className={`shrink-0 w-16 ${color}`}>[{level}]</span>
              <span className="text-gray-300 break-all">{message}</span>
            </div>
          )
        })}
      </div>
    </div>
  )
}