import React from 'react'

export default function StatusBadge({ isRunning, mode, lastUpdated }) {
  const getTimeSince = () => {
    if (!lastUpdated) return ''
    const seconds = Math.floor((Date.now() - lastUpdated.getTime()) / 1000)
    if (seconds < 10) return 'just now'
    if (seconds < 60) return `${seconds}s ago`
    return `${Math.floor(seconds / 60)}m ago`
  }

  return (
    <div className="flex items-center gap-3">
      <div className={`w-3 h-3 rounded-full ${isRunning ? 'bg-green-500 animate-pulse' : 'bg-red-500'}`} />
      <span className="text-sm font-medium">
        {isRunning ? 'Running' : 'Stopped'}
      </span>
      <span className={`px-2 py-0.5 rounded text-xs font-bold uppercase ${
        mode === 'live' ? 'bg-red-600 text-white' : 'bg-yellow-600 text-black'
      }`}>
        {mode || 'paper'}
      </span>
      {lastUpdated && (
        <span className="text-xs text-gray-500">
          Updated {getTimeSince()}
        </span>
      )}
    </div>
  )
}