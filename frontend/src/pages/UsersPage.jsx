import { useState, useEffect } from 'react'
import { Users, Plus, Trash2, Shield, UserCircle, RefreshCw } from 'lucide-react'
import axios from 'axios'
import { getToken } from '../api'

const api = axios.create({ baseURL: 'http://localhost:8000' })
api.interceptors.request.use(config => {
  const token = getToken()
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

export default function UsersPage() {
  const [users, setUsers]       = useState([])
  const [loading, setLoading]   = useState(true)
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [role, setRole]         = useState('user')
  const [adding, setAdding]     = useState(false)
  const [error, setError]       = useState('')
  const [success, setSuccess]   = useState('')

  async function load() {
    setLoading(true)
    try {
      const res = await api.get('/admin/users')
      setUsers(res.data)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  async function createUser(e) {
    e.preventDefault()
    if (!username.trim() || !password.trim()) return
    setAdding(true)
    setError('')
    setSuccess('')
    try {
      await api.post('/admin/users', { username, password, role })
      setSuccess(`User '${username}' created successfully`)
      setUsername('')
      setPassword('')
      setRole('user')
      await load()
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to create user')
    } finally {
      setAdding(false)
    }
  }

  async function deactivate(username) {
    if (!confirm(`Deactivate user '${username}'?`)) return
    try {
      await api.delete(`/admin/users/${username}`)
      await load()
    } catch (err) {
      alert(err.response?.data?.detail || 'Failed to deactivate')
    }
  }

  return (
    <div className="p-6 max-w-4xl">
      {/* header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-2xl font-bold text-gray-900">User Management</h2>
          <p className="text-sm text-gray-500 mt-1">
            Create and manage operator and customer accounts
          </p>
        </div>
        <button
          onClick={load}
          className="flex items-center gap-2 text-sm text-gray-600 border rounded-lg px-3 py-2 hover:text-gray-900"
        >
          <RefreshCw size={14} />
          Refresh
        </button>
      </div>

      {/* create user form */}
      <div className="bg-white border rounded-xl p-6 mb-6">
        <h3 className="font-semibold text-gray-900 mb-4 flex items-center gap-2">
          <Plus size={16} />
          Create New User
        </h3>
        <form onSubmit={createUser} className="space-y-3">
          <div className="grid grid-cols-3 gap-3">
            <div>
              <label className="text-xs font-medium text-gray-600 mb-1 block">Username</label>
              <input
                className="w-full border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                placeholder="e.g. john"
                value={username}
                onChange={e => setUsername(e.target.value)}
              />
            </div>
            <div>
              <label className="text-xs font-medium text-gray-600 mb-1 block">Password</label>
              <input
                type="password"
                className="w-full border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                placeholder="••••••••"
                value={password}
                onChange={e => setPassword(e.target.value)}
              />
            </div>
            <div>
              <label className="text-xs font-medium text-gray-600 mb-1 block">Role</label>
              <select
                className="w-full border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                value={role}
                onChange={e => setRole(e.target.value)}
              >
                <option value="user">user — chat only</option>
                <option value="admin">admin — full access</option>
              </select>
            </div>
          </div>

          {error && (
            <p className="text-xs text-red-500 bg-red-50 border border-red-200 rounded-lg px-3 py-2">
              {error}
            </p>
          )}
          {success && (
            <p className="text-xs text-green-600 bg-green-50 border border-green-200 rounded-lg px-3 py-2">
              ✓ {success}
            </p>
          )}

          <button
            type="submit"
            disabled={adding || !username.trim() || !password.trim()}
            className="bg-indigo-600 text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-indigo-700 disabled:opacity-50 transition-colors"
          >
            {adding ? 'Creating...' : 'Create User'}
          </button>
        </form>
      </div>

      {/* user list */}
      <section>
        <h3 className="text-sm font-semibold text-gray-500 uppercase tracking-wide mb-3">
          All Users ({users.length})
        </h3>
        {loading ? (
          <p className="text-sm text-gray-400">Loading...</p>
        ) : (
          <div className="space-y-2">
            {users.map(u => (
              <div
                key={u.id}
                className={`bg-white border rounded-xl px-5 py-4 flex items-center justify-between ${
                  !u.is_active ? 'opacity-50' : ''
                }`}
              >
                <div className="flex items-center gap-3">
                  <div className="w-8 h-8 rounded-full bg-indigo-100 flex items-center justify-center">
                    <UserCircle size={16} className="text-indigo-600" />
                  </div>
                  <div>
                    <div className="flex items-center gap-2">
                      <p className="text-sm font-medium text-gray-900">{u.username}</p>
                      {!u.is_active && (
                        <span className="text-xs bg-gray-100 text-gray-500 px-2 py-0.5 rounded-full">
                          inactive
                        </span>
                      )}
                    </div>
                    <p className="text-xs text-gray-400">
                      customer_id: {u.customer_id || '—'} · joined {new Date(u.created_at).toLocaleDateString()}
                    </p>
                  </div>
                </div>
                <div className="flex items-center gap-3">
                  <div className={`flex items-center gap-1 text-xs px-2 py-1 rounded-full font-medium ${
                    u.role === 'admin'
                      ? 'bg-amber-100 text-amber-800'
                      : 'bg-blue-100 text-blue-800'
                  }`}>
                    <Shield size={10} />
                    {u.role}
                  </div>
                  {u.username !== 'admin' && u.is_active && (
                    <button
                      onClick={() => deactivate(u.username)}
                      className="text-red-400 hover:text-red-600 transition-colors"
                      title="Deactivate user"
                    >
                      <Trash2 size={15} />
                    </button>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  )
}