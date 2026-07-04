// src/api.js — the single place the console talks to FastAPI.
//
// Base URL comes from VITE_API_BASE. Empty string = same origin (production,
// served by FastAPI). The JWT is kept in localStorage so a page refresh stays
// logged in. Note: localStorage tokens are readable by any script on the page,
// so this is fine for a demo/portfolio app but not how you'd store a banking
// session — worth saying out loud in your presentation.

const BASE = import.meta.env.VITE_API_BASE || ''

function getToken() {
  return localStorage.getItem('sv_token')
}

async function request(path, options = {}) {
  const headers = { ...(options.headers || {}) }
  const token = getToken()
  if (token) headers['Authorization'] = `Bearer ${token}`

  const res = await fetch(`${BASE}${path}`, { ...options, headers })

  let data = null
  try {
    data = await res.json()
  } catch {
    data = null
  }

  if (!res.ok) {
    const detail =
      (data && (data.detail || data.message)) || `Request failed (${res.status})`
    const err = new Error(typeof detail === 'string' ? detail : JSON.stringify(detail))
    err.status = res.status
    throw err
  }
  return data
}

// ── Auth ──────────────────────────────────────────────────────────────────────
export async function login(email, password) {
  const data = await request('/auth/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password }),
  })
  localStorage.setItem('sv_token', data.access_token)
  localStorage.setItem('sv_role', data.role)
  localStorage.setItem('sv_user', data.username)
  return data
}

export function logout() {
  localStorage.removeItem('sv_token')
  localStorage.removeItem('sv_role')
  localStorage.removeItem('sv_user')
}

export function currentUser() {
  const token = getToken()
  if (!token) return null
  return {
    token,
    role: localStorage.getItem('sv_role'),
    username: localStorage.getItem('sv_user'),
  }
}

// ── Admin dashboard data ──────────────────────────────────────────────────────
export const getSummary = () => request('/admin/metrics/summary')
export const getTimeseries = (minutes = 15) =>
  request(`/admin/metrics/timeseries?minutes=${minutes}`)
export const getInfra = () => request('/admin/metrics/infra')
export const getFeed = () => request('/audit/feed')

// ── Demo triggers ─────────────────────────────────────────────────────────────
export const testNotification = () => request('/demo/test-notification', { method: 'POST' })
export const runCredentialStuffing = () =>
  request('/demo/credential-stuffing', { method: 'POST' })
export const runAccessControlAttack = () =>
  request('/demo/access-control', { method: 'POST' })
export const runExfiltrationAttack = () =>
  request('/demo/exfiltration', { method: 'POST' })
export const runDdosAttack = () =>
  request('/demo/ddos', { method: 'POST' })

// ── SecureDocs ────────────────────────────────────────────────────────────────
export const listDocuments = () => request('/docs/list')

export function uploadDocument(file, description = '') {
  // multipart/form-data — do NOT set Content-Type; the browser adds the
  // boundary automatically. The backend reads `file` and `description`.
  const form = new FormData()
  form.append('file', file)
  if (description) form.append('description', description)
  return request('/docs/upload', { method: 'POST', body: form })
}

// Returns { download_url, expires_in_seconds } — a 15-minute pre-signed S3 URL.
export const downloadDocument = (id) => request(`/docs/download/${id}`)

export const deleteDocument = (id) => request(`/docs/${id}`, { method: 'DELETE' })

export const getVersions = (id) => request(`/docs/${id}/versions`)

// ── ShimonMeet ────────────────────────────────────────────────────────────────
export const listMeetings = () => request('/meetings/list')

export function createMeeting({ title, description, scheduled_at, ends_at, participant_ids = [] }) {
  return request('/meetings/create', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ title, description, scheduled_at, ends_at, participant_ids }),
  })
}

// join takes the token as a query parameter (matches meetings_router).
export const joinMeeting = (id, token) =>
  request(`/meetings/${id}/join?token=${encodeURIComponent(token)}`, { method: 'POST' })

export const cancelMeeting = (id) => request(`/meetings/${id}`, { method: 'DELETE' })

export const getMeetingArchive = (id) => request(`/meetings/${id}/archive`)
