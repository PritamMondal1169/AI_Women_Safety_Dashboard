/**
 * api.js — Coordinator API client
 */
const BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

async function request(path, options = {}) {
  const url = `${BASE_URL}${path}`
  const res = await fetch(url, {
    headers: { 'Content-Type': 'application/json', ...options.headers },
    ...options,
  })
  if (!res.ok) {
    const errBody = await res.text().catch(() => '')
    throw new Error(`API ${res.status}: ${errBody}`)
  }
  return res.status === 204 ? null : res.json()
}

export const api = {
  // Health
  health: () => request('/health'),

  // Alerts
  getAlerts: (params = {}) => {
    const qs = new URLSearchParams(params).toString()
    return request(`/api/v1/alerts${qs ? `?${qs}` : ''}`)
  },
  getAlert: (id) => request(`/api/v1/alerts/${id}`),

  // Cameras
  getCameras: () => request('/api/v1/cameras'),
  getCamera: (id) => request(`/api/v1/cameras/${id}`),

  // Journeys
  getActiveJourneys: () => request('/api/v1/journey/active'),
  getJourney: (id) => request(`/api/v1/journey/${id}`),

  // Transit (Blind Spot)
  getActiveTransits: () => request('/api/v1/transit/active'),
}

export const WS_URL = BASE_URL.replace('http', 'ws')
