import React, { useRef, useEffect, useState } from 'react'

const levelColors = {
  INFO: 'text-blue-400',
  WARNING: 'text-yellow-400',
  ERROR: 'text-red-400',
  DEBUG: 'text-gray-500',
  CRITICAL: 'text-red-500 font-bold',
}

const levelBg = {
  ERROR: 'bg-red-900/10',
  CRITICAL: 'bg-red-900/20',
  WARNING: 'bg-yellow-900/10',
}

export default function LogViewer({ logs }) {
  const scrollRef = useRef(null)
  const [autoScroll, setAutoScroll] = useState(true)
  const [levelFilter, setLevelFilter] = useState('ALL')

  useEffect(() => {
    if (autoScroll && scrollRef.current) {
      scrollRef.current.scrollTop = 0
    }
  }, [logs, autoScroll])

  const filteredLogs = levelFilter === 'ALL'
    ? logs
    : (logs || []).filter(log => (log.level || 'INFO') === levelFilter)

  if (!logs || logs.length === 0) {
    return (
      <div className="bg-gray-900 rounded-xl p-6 border border-gray-800">
        <h3 className="text-lg font-semibold mb-4">Recent Logs</h3>
        <div className="flex flex-col items-center justify-center py-6 text-gray-500">
          <div className="text-4xl mb-2">📝</div>
          <p className="text-sm">No logs available</p>
        </div>
      </div>
    )
  }

  return (
    <div className="bg-gray-900 rounded-xl p-6 border border-gray-800">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-lg font-semibold">Recent Logs</h3>
        <div className="flex items-center gap-2">
          <select
            value={levelFilter}
            onChange={(e) => setLevelFilter(e.target.value)}
            className="bg-gray-800 border border-gray-700 rounded px-2 py-1 text-xs text-white focus:outline-none focus:border-blue-500"
          >
            <option value="ALL">All Levels</option>
            <option value="ERROR">Errors</option>
            <option value="WARNING">Warnings</option>
            <option value="INFO">Info</option>
          </select>
          <button
            onClick={() => setAutoScroll(!autoScroll)}
            className={`text-xs px-2 py-1 rounded border ${
              autoScroll
                ? 'border-blue-500 text-blue-400 bg-blue-900/20'
                : 'border-gray-700 text-gray-500 bg-gray-800'
            }`}
          >
            Auto-scroll {autoScroll ? 'ON' : 'OFF'}
          </button>
        </div>
      </div>
      <div ref={scrollRef} className="max-h-80 overflow-y-auto space-y-0.5 font-mono text-[11px]">
        {(filteredLogs || []).slice(0, 100).map((log, idx) => {
          const level = log.level || 'INFO'
          const color = levelColors[level] || 'text-gray-400'
          const bg = levelBg[level] || ''
          const timestamp = log.timestamp
            ? new Date(log.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
            : ''
          const message = log.message || JSON.stringify(log)

          return (
            <div key={idx} className={`flex gap-2 px-2 py-0.5 rounded ${bg} hover:bg-gray-800/40`}>
              <span className="text-gray-600 shrink-0 w-16">{timestamp}</span>
              <span className={`shrink-0 w-14 text-right ${color}`}>{level}</span>
              <span className="text-gray-300 break-all">{message}</span>
            </div>
          )
        })}
      </div>
    </div>
  )
}