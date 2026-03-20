/**
 * Shared formatting utilities for trading components.
 */

export function fmtPrice(p) {
  if (p == null || isNaN(p) || p === 0) return '—'
  const n = Number(p)
  if (n >= 10000) return n.toLocaleString(undefined, { minimumFractionDigits: 1, maximumFractionDigits: 1 })
  if (n >= 1000) return n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })
  if (n >= 100) return n.toFixed(2)
  if (n >= 10) return n.toFixed(3)
  if (n >= 1) return n.toFixed(4)
  if (n >= 0.01) return n.toFixed(5)
  if (n >= 0.0001) return n.toFixed(6)
  return n.toFixed(8)
}

export function fmtSize(s) {
  if (s == null || isNaN(s) || s === 0) return '—'
  const n = Number(s)
  if (n >= 1000000) return `${(n / 1000000).toFixed(2)}M`
  if (n >= 1000) return `${(n / 1000).toFixed(1)}k`
  if (n >= 1) return n.toFixed(3)
  if (n >= 0.001) return n.toFixed(4)
  return n.toFixed(6)
}

export function fmtVol(v) {
  if (v == null || isNaN(v) || v === 0) return '—'
  const n = Number(v)
  if (n >= 1e9) return `$${(n / 1e9).toFixed(2)}B`
  if (n >= 1e6) return `$${(n / 1e6).toFixed(2)}M`
  if (n >= 1e3) return `$${(n / 1e3).toFixed(1)}K`
  return `$${n.toFixed(0)}`
}

export function getApiKey() {
  if (typeof window !== 'undefined' && window.__DASHBOARD_API_KEY__) return window.__DASHBOARD_API_KEY__
  const meta = document.querySelector('meta[name="dashboard-api-key"]')
  return meta ? meta.getAttribute('content') : ''
}

export function getHeaders() {
  const headers = {}
  const key = getApiKey()
  if (key) headers['X-API-Key'] = key
  return headers
}