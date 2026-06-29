import { useState } from 'react'
import { getMemories } from '../api'
import { User, Brain, Search, Clock } from 'lucide-react'

const KIND_COLORS = {
  episodic: 'bg-blue-100 text-blue-800',
  semantic: 'bg-purple-100 text-purple-800',
}

const KIND_LABELS = {
  episodic: '📅 Episodic',
  semantic: '🧠 Semantic',
}

export default function CustomerPage() {
  const [customerId, setCustomerId] = useState('10')
  const [memories, setMemories]     = useState([])
  const [loading, setLoading]       = useState(false)
  const [searched, setSearched]     = useState(false)
  const [error, setError]           = useState(null)

  async function load() {
    if (!customerId.trim()) return
    setLoading(true)
    setError(null)
    try {
      const data = await getMemories(customerId)
      setMemories(data)
      setSearched(true)
    } catch (e) {
      setError('Could not load memories — is the API running?')
    } finally {
      setLoading(false)
    }
  }

  const episodic = memories.filter(m => m.kind === 'episodic')
  const semantic  = memories.filter(m => m.kind === 'semantic')

  return (
    <div className="p-6 max-w-4xl">
      {/* header */}
      <div className="mb-6">
        <h2 className="text-2xl font-bold text-gray-900">Customer 360</h2>
        <p className="text-sm text-gray-500 mt-1">
          What the agent remembers about each customer across all sessions
        </p>
      </div>

      {/* search */}
      <div className="bg-white border rounded-xl p-6 mb-6">
        <h3 className="font-semibold text-gray-900 mb-4 flex items-center gap-2">
          <Search size={16} />
          Look up customer
        </h3>
        <div className="flex gap-3">
          <input
            className="flex-1 border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
            placeholder="Customer ID (e.g. 10)"
            value={customerId}
            onChange={e => setCustomerId(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && load()}
          />
          <button
            onClick={load}
            disabled={loading}
            className="bg-indigo-600 text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-indigo-700 disabled:opacity-50 transition-colors"
          >
            {loading ? 'Loading...' : 'Load Memories'}
          </button>
        </div>
        {error && <p className="text-xs text-red-500 mt-2">{error}</p>}
      </div>

      {/* results */}
      {searched && (
        <>
          {/* summary card */}
          <div className="bg-white border rounded-xl p-6 mb-6">
            <div className="flex items-center gap-4">
              <div className="w-12 h-12 rounded-full bg-indigo-100 flex items-center justify-center">
                <User size={20} className="text-indigo-600" />
              </div>
              <div>
                <p className="font-semibold text-gray-900">Customer #{customerId}</p>
                <p className="text-sm text-gray-500">
                  {memories.length} memories · {episodic.length} episodic · {semantic.length} semantic
                </p>
              </div>
              <div className="ml-auto flex items-center gap-2">
                <Brain size={16} className="text-indigo-400" />
                <span className="text-sm text-gray-500">
                  {memories.length === 0 ? 'No memories yet' : 'Memory active'}
                </span>
              </div>
            </div>
          </div>

          {memories.length === 0 ? (
            <div className="bg-white border rounded-xl p-8 text-center text-gray-400">
              <Brain size={32} className="mx-auto mb-2 opacity-30" />
              <p className="text-sm">No memories found for customer #{customerId}</p>
              <p className="text-xs mt-1">Start a chat with this customer ID to create memories</p>
            </div>
          ) : (
            <div className="space-y-6">
              {/* episodic memories */}
              {episodic.length > 0 && (
                <section>
                  <h3 className="text-sm font-semibold text-gray-500 uppercase tracking-wide mb-3">
                    Episodic Memories — what happened ({episodic.length})
                  </h3>
                  <div className="space-y-2">
                    {episodic.map((m, i) => (
                      <div key={i} className="bg-white border rounded-xl px-5 py-4">
                        <div className="flex items-start justify-between gap-4">
                          <p className="text-sm text-gray-700 flex-1">{m.content}</p>
                          <div className="flex items-center gap-2 flex-shrink-0">
                            <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${KIND_COLORS[m.kind]}`}>
                              {KIND_LABELS[m.kind]}
                            </span>
                          </div>
                        </div>
                        <div className="flex items-center gap-1 mt-2 text-xs text-gray-400">
                          <Clock size={11} />
                          {new Date(m.created_at).toLocaleString()}
                        </div>
                      </div>
                    ))}
                  </div>
                </section>
              )}

              {/* semantic memories */}
              {semantic.length > 0 && (
                <section>
                  <h3 className="text-sm font-semibold text-gray-500 uppercase tracking-wide mb-3">
                    Semantic Memories — durable facts ({semantic.length})
                  </h3>
                  <div className="space-y-2">
                    {semantic.map((m, i) => (
                      <div key={i} className="bg-white border rounded-xl px-5 py-4">
                        <div className="flex items-start justify-between gap-4">
                          <p className="text-sm text-gray-700 flex-1">{m.content}</p>
                          <span className={`text-xs px-2 py-0.5 rounded-full font-medium flex-shrink-0 ${KIND_COLORS[m.kind]}`}>
                            {KIND_LABELS[m.kind]}
                          </span>
                        </div>
                        <div className="flex items-center gap-1 mt-2 text-xs text-gray-400">
                          <Clock size={11} />
                          {new Date(m.created_at).toLocaleString()}
                        </div>
                      </div>
                    ))}
                  </div>
                </section>
              )}
            </div>
          )}
        </>
      )}
    </div>
  )
}