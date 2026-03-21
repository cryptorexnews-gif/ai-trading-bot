import React, { useState } from 'react'
import { Power, Play, Square } from 'lucide-react'
import useBotControl from '../hooks/useBotControl'
import Toast from './Toast'

export default function BotControlPanel() {
  const { controller, loading, actionLoading, startBot, stopBot } = useBotControl()
  const [toast, setToast] = useState({ type: 'info', message: '' })

  const isRunning = controller?.is_running || false

  const onStart = async () => {
    try {
      await startBot()
      setToast({ type: 'success', message: 'Bot avviato con successo.' })
    } catch (err) {
      setToast({ type: 'error', message: `Avvio fallito: ${err.message}` })
    }
  }

  const onStop = async () => {
    try {
      await stopBot()
      setToast({ type: 'success', message: 'Bot fermato con successo.' })
    } catch (err) {
      setToast({ type: 'error', message: `Stop fallito: ${err.message}` })
    }
  }

  if (loading) {
    return (
      <div className="bg-gray-900 rounded-xl p-4 border border-gray-800 animate-pulse">
        <div className="h-4 w-32 bg-gray-800 rounded mb-3" />
        <div className="h-9 w-56 bg-gray-800 rounded" />
      </div>
    )
  }

  return (
    <>
      <div className="bg-gray-900 rounded-xl p-4 border border-gray-800">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
          <div>
            <h3 className="text-sm font-semibold flex items-center gap-2">
              <Power size={14} className="text-cyan-400" />
              Bot Process Control
            </h3>
            <p className="text-xs text-gray-500 mt-1">
              Stato processo: {isRunning ? 'Running' : 'Stopped'}
              {isRunning && controller?.pid ? ` • PID ${controller.pid}` : ''}
            </p>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={onStart}
              disabled={isRunning || actionLoading}
              className="inline-flex items-center gap-1 px-3 py-2 rounded-lg text-xs font-medium bg-green-600 hover:bg-green-700 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              <Play size={12} />
              Start Bot
            </button>
            <button
              onClick={onStop}
              disabled={!isRunning || actionLoading}
              className="inline-flex items-center gap-1 px-3 py-2 rounded-lg text-xs font-medium bg-red-600 hover:bg-red-700 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              <Square size={12} />
              Stop Bot
            </button>
          </div>
        </div>
      </div>

      <Toast
        type={toast.type}
        message={toast.message}
        onClose={() => setToast({ type: 'info', message: '' })}
      />
    </>
  )
}