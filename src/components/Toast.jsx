import React, { useEffect } from 'react'

export default function Toast({ type = 'success', message, onClose, duration = 2800 }) {
  useEffect(() => {
    if (!message) return
    const timer = setTimeout(() => {
      if (onClose) onClose()
    }, duration)
    return () => clearTimeout(timer)
  }, [message, onClose, duration])

  if (!message) return null

  const styles = {
    success: 'bg-green-900/90 border-green-600 text-green-200',
    error: 'bg-red-900/90 border-red-600 text-red-200',
    info: 'bg-blue-900/90 border-blue-600 text-blue-200',
  }

  return (
    <div className="fixed bottom-5 right-5 z-50">
      <div className={`border rounded-lg px-4 py-3 shadow-2xl text-sm max-w-sm ${styles[type] || styles.info}`}>
        {message}
      </div>
    </div>
  )
}