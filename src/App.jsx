import React from 'react'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import AppShell from './components/AppShell'
import DashboardPage from './pages/dashboard'
import TradingPage from './pages/trading'
import PositionsPage from './pages/positions'
import HistoryPage from './pages/history'
import SystemPage from './pages/system'

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<AppShell />}>
          <Route index element={<DashboardPage />} />
          <Route path="trading" element={<TradingPage />} />
          <Route path="positions" element={<PositionsPage />} />
          <Route path="history" element={<HistoryPage />} />
          <Route path="system" element={<SystemPage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}