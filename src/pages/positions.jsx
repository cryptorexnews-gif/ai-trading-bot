import React from 'react'
import { useApi } from '../hooks/useApi'
import PositionsTable from '../components/PositionsTable'
import ManagedPositions from '../components/ManagedPositions'

export default function PositionsPage() {
  const { data: portfolioData } = useApi('/portfolio', 2000)
  const { data: managedData } = useApi('/managed-positions', 2000)

  const portfolio = portfolioData?.portfolio || {}
  const positions = portfolio.positions || {}
  const managedPositions = managedData?.managed_positions || []

  return (
    <div className="space-y-5">
      <PositionsTable positions={positions} />
      <ManagedPositions positions={managedPositions} />
    </div>
  )
}