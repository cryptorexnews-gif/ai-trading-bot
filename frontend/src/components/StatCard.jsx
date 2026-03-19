import React from 'react'

export default function StatCard({ title, value, subtitle, icon: Icon, color = 'blue' }) {
  const colorMap = {
    blue: 'from-blue-600 to-blue-800',
    green: 'from-green-600 to-green-800',
    red: 'from-red-600 to-red-800',
    yellow: 'from-yellow-600 to-yellow-800',
    purple: 'from-purple-600 to-purple-800',
    cyan: 'from-cyan-600 to-cyan-800',
  }

  return (
    <div className={`bg-gradient-to-br ${colorMap[color] || colorMap.blue} rounded-xl p-4 shadow-lg`}>
      <div className="flex items-center justify-between mb-2">
        <span className="text-xs font-medium text-white/70 uppercase tracking-wide">{title}</span>
        {Icon && <Icon size={18} className="text-white/50" />}
      </div>
      <div className="text-2xl font-bold text-white">{value}</div>
      {subtitle && <div className="text-xs text-white/60 mt-1">{subtitle}</div>}
    </div>
  )
}