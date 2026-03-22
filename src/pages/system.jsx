import React from 'react'
import { useApi } from '../hooks/useApi'
import CircuitBreakerStatus from '../components/CircuitBreakerStatus'
import LogViewer from '../components/LogViewer'

export default function SystemPage() {
  const { data: statusData } = useApi('/status', 3000)
  const { data: logsData } = useApi('/logs?limit=100', 3000)

  const breakers = statusData?.circuit_breakers || {}
  const logs = logsData?.logs || []

  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
      <CircuitBreakerStatus breakers={breakers} />
      <LogViewer logs={logs} />
    </div>
  )
}