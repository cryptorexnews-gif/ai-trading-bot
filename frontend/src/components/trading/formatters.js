/**
 * Shared formatting utilities for trading components.
 */

export function fmtPrice(p) {
  if (p == null || isNaN(p)) return '—'
  if (p >= 10000) return p.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })
  if (p >= 100) return p.toFixed(2)
  if (p >= 1) return p.toFixed(4)
  if (p >= 0.01) return p.toFixed(5)
  return p.toFixed(8)
}

export function fmtSize(s) {
  if (s == null || isNaN(s)) return '—'
  if (s >= 1000000) return `${(s / 1000000).toFixed(2)}M`
  if (s >= 1000) return `${(s / 1000).toFixed(1)}k`
  if (s >= 1) return s.toFixed(3)
  return s.toFixed(6)
}

export function fmtVol(v) {
  if (v == null || isNaN(v)) return '—'
  if (v >= 1e9) return `$${(v / 1e9).toFixed(2)}B`
  if (v >= 1e6) return `$${(v / 1e6).toFixed(2)}M`
  if (v >= 1e3) return `$${(v / 1e3).toFixed(1)}K`
  return `$${v.toFixed(0)}`
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