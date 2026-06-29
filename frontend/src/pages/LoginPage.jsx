import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { login, saveAuth } from '../api'
import { Bot, Lock } from 'lucide-react'

export default function LoginPage() {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError]       = useState('')
  const [loading, setLoading]   = useState(false)
  const navigate = useNavigate()

  async function handleLogin(e) {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      const data = await login(username, password)
saveAuth(data.access_token, data.refresh_token, data.role, data.username, data.customer_id)
      navigate('/')
    } catch (err) {
      setError(err.response?.data?.detail || 'Login failed')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-gray-50 flex items-center justify-center">
      <div className="bg-white border rounded-2xl shadow-sm p-8 w-full max-w-sm">
        {/* logo */}
        <div className="flex flex-col items-center mb-8">
          <div className="w-12 h-12 bg-indigo-600 rounded-xl flex items-center justify-center mb-3">
            <Bot size={24} className="text-white" />
          </div>
          <h1 className="text-xl font-bold text-gray-900">Support Copilot</h1>
          <p className="text-sm text-gray-500 mt-1">Sign in to continue</p>
        </div>

        {/* form */}
        <form onSubmit={handleLogin} className="space-y-4">
          <div>
            <label className="text-xs font-medium text-gray-600 mb-1 block">
              Username
            </label>
            <input
              className="w-full border rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
              placeholder="admin or user"
              value={username}
              onChange={e => setUsername(e.target.value)}
              autoFocus
            />
          </div>
          <div>
            <label className="text-xs font-medium text-gray-600 mb-1 block">
              Password
            </label>
            <input
              type="password"
              className="w-full border rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
              placeholder="••••••••"
              value={password}
              onChange={e => setPassword(e.target.value)}
            />
          </div>

          {error && (
            <p className="text-xs text-red-500 bg-red-50 border border-red-200 rounded-lg px-3 py-2">
              {error}
            </p>
          )}

          <button
            type="submit"
            disabled={loading || !username || !password}
            className="w-full bg-indigo-600 text-white py-2.5 rounded-lg text-sm font-medium hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors flex items-center justify-center gap-2"
          >
            <Lock size={14} />
            {loading ? 'Signing in...' : 'Sign in'}
          </button>
        </form>

        {/* dev hint */}
        <div className="mt-6 bg-gray-50 rounded-lg p-3 text-xs text-gray-500 space-y-1">
          <p className="font-medium text-gray-700">Dev credentials:</p>
          <p><span className="font-mono bg-gray-200 px-1 rounded">admin</span> / <span className="font-mono bg-gray-200 px-1 rounded">admin123</span> — full access</p>
          <p><span className="font-mono bg-gray-200 px-1 rounded">user</span> / <span className="font-mono bg-gray-200 px-1 rounded">user123</span> — chat only</p>
        </div>
      </div>
    </div>
  )
}