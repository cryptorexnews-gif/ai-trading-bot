import React from 'react'

export default function ChartSkeleton({ height = 500 }) {
  return (
    <div className="flex items-center justify-center" style={{ height }}>
      <div className="w-full h-full flex flex-col gap-2 p-6 animate-pulse">
        <div className="flex items-end gap-1 flex-1">
          {[...Array(40)].map((_, i) => (
            <div
              key={i}
              className="flex-1 bg-gray-800 rounded-sm"
              style={{
                height: `${20 + Math.sin(i * 0.4) * 30 + Math.random() * 25}%`,
                minWidth: 4,
              }}
            />
          ))}
        </div>
        <div className="h-3 bg-gray-800 rounded w-full" />
      </div>
    </div>
  )
}