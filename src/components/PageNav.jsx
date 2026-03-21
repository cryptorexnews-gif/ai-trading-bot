import React from 'react'
import { NavLink } from 'react-router-dom'

const items = [
  { to: '/', label: 'Overview' },
  { to: '/trading', label: 'Trading' },
  { to: '/positions', label: 'Positions' },
  { to: '/history', label: 'History' },
  { to: '/system', label: 'System' },
]

export default function PageNav() {
  return (
    <nav className="overflow-x-auto">
      <div className="flex items-center gap-2 min-w-max">
        {items.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.to === '/'}
            className={({ isActive }) =>
              `px-3 py-1.5 rounded-lg text-xs sm:text-sm border transition-colors ${
                isActive
                  ? 'bg-cyan-600/20 border-cyan-500 text-cyan-300'
                  : 'bg-gray-900 border-gray-800 text-gray-400 hover:text-white'
              }`
            }
          >
            {item.label}
          </NavLink>
        ))}
      </div>
    </nav>
  )
}