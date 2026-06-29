import axios from 'axios'

const api = axios.create({
  baseURL: 'http://localhost:8000',
  timeout: 30000,
})

// ── Token management ──────────────────────────────────────────
// sessionStorage: survives page refresh, gone when tab closes
// Production upgrade: httpOnly cookies set by server (immune to XSS)
export function getToken() {
  return sessionStorage.getItem('token')
}

export function getRole() {
  return sessionStorage.getItem('role')
}

export function getUsername() {
  return sessionStorage.getItem('username')
}

export function saveAuth(token, refreshToken, role, username, customerId) {
  sessionStorage.setItem('token', token)
  sessionStorage.setItem('refresh_token', refreshToken)
  sessionStorage.setItem('role', role)
  sessionStorage.setItem('username', username)
  if (customerId) sessionStorage.setItem('customer_id', String(customerId))
}

export function clearAuth() {
  sessionStorage.removeItem('token')
  sessionStorage.removeItem('refresh_token')
  sessionStorage.removeItem('role')
  sessionStorage.removeItem('username')
  sessionStorage.removeItem('customer_id')
}

export function getRefreshToken() {
  return sessionStorage.getItem('refresh_token')
}

export function isLoggedIn() {
  return !!getToken()
}

export function isAdmin() {
  return getRole() === 'admin'
}

// attach token to every request automatically
api.interceptors.request.use(config => {
  const token = getToken()
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

// track if we're already refreshing to prevent loops
let isRefreshing = false
let refreshQueue = []

api.interceptors.response.use(
  res => res,
  async err => {
    const original = err.config

    if (err.response?.status === 401 && !original._retry) {
      original._retry = true

      if (isRefreshing) {
        // queue this request until refresh completes
        return new Promise((resolve, reject) => {
          refreshQueue.push({ resolve, reject })
        }).then(token => {
          original.headers.Authorization = `Bearer ${token}`
          return api(original)
        })
      }

      isRefreshing = true
      const refreshToken = getRefreshToken()

      if (!refreshToken) {
        clearAuth()
        window.location.href = '/login'
        return Promise.reject(err)
      }

      try {
        const res = await axios.post('http://localhost:8000/auth/refresh', {
          refresh_token: refreshToken,
        })
        const { access_token, refresh_token: newRefresh, role, username, customer_id } = res.data
        saveAuth(access_token, newRefresh, role, username, customer_id)

        // retry queued requests with new token
        refreshQueue.forEach(({ resolve }) => resolve(access_token))
        refreshQueue = []

        original.headers.Authorization = `Bearer ${access_token}`
        return api(original)
      } catch (refreshErr) {
        refreshQueue.forEach(({ reject }) => reject(refreshErr))
        refreshQueue = []
        clearAuth()
        window.location.href = '/login'
        return Promise.reject(refreshErr)
      } finally {
        isRefreshing = false
      }
    }

    return Promise.reject(err)
  }
)

// ── Auth ──────────────────────────────────────────────────────
export async function login(username, password) {
  const form = new URLSearchParams()
  form.append('username', username)
  form.append('password', password)
  const res = await api.post('/auth/login', form, {
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
  })
  return res.data
}

export async function getMe() {
  return api.get('/auth/me').then(r => r.data)
}

// ── Chat (streaming) ──────────────────────────────────────────
export async function sendMessage({ message, customerId, threadId }, onChunk) {
  const token = getToken()
  const res = await fetch('http://localhost:8000/chat', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify({
      message,
      customer_id: customerId ? Number(customerId) : null,
      thread_id: threadId || 'default',
    }),
  })

  const contentType = res.headers.get('content-type')
  if (contentType && contentType.includes('application/json')) {
    return await res.json()
  }

  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  while (true) {
    const { value, done } = await reader.read()
    if (done) break
    onChunk(decoder.decode(value))
  }
  return null
}

// ── Admin endpoints ───────────────────────────────────────────
export const getApprovals = () =>
  api.get('/approvals').then(r => r.data)

export const approveAction = (threadId, approved) =>
  api.post('/approve', { thread_id: threadId, approved }).then(r => r.data)

export const getDocuments = () =>
  api.get('/documents').then(r => r.data)

export const addDocument = (title, content, source) =>
  api.post('/documents', { title, content, source }).then(r => r.data)

export const getMemories = (customerId) =>
  api.get(`/memories/${customerId}`).then(r => r.data)