import React from 'react'

export default function StatCard({ title, value, subtitle, icon: Icon, color = 'blue' }) {
  const colorMap = {
    blue: 'from-blue-600/90 to-blue-900',
    green: 'from-green-600/90 to-green-900',
    red: 'from-red-600/90 to-red-900',
    yellow: 'from-yellow-600/90 to-yellow-900',
    purple: 'from-purple-600/90 to-purple-900',
    cyan: 'from-cyan-600/90 to-cyan-900',
  }

  const safeValue = value != null && value !== undefined && value !== 'undefined'
    ? value
    : '—'

  const safeSubtitle = subtitle != null && subtitle !== undefined && !String(subtitle).includes('undefined')
    ? subtitle
    : null

  return (
    <div className={`bg-gradient-to-br ${colorMap[color] || colorMap.blue} rounded-xl p-4 shadow-lg border border-white/5`}>
      <div className="flex items-center justify-between mb-2">
        <span className="text-[10px] sm:text-xs font-medium text-white/70 uppercase tracking-wide">{title}</span>
        {Icon && <Icon size={16} className="text-white/40" />}
      </div>
      <div className="text-lg sm:text-2xl font-bold text-white truncate">{safeValue}</div>
      {safeSubtitle && <div className="text-[10px] sm:text-xs text-white/50 mt-1 truncate">{safeSubtitle}</div>}
    </div>
  )
}