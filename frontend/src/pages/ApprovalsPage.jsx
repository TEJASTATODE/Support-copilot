import { useState, useEffect } from 'react'
import { getApprovals, approveAction } from '../api'
import { CheckCircle, XCircle, Clock, RefreshCw } from 'lucide-react'

const STATUS_COLORS = {
  pending:  'bg-amber-100 text-amber-800',
  approved: 'bg-green-100 text-green-800',
  rejected: 'bg-red-100 text-red-800',
}

const ACTION_LABELS = {
  issue_refund:        '💰 Refund',
  cancel_order:        '❌ Cancel Order',
  update_order_status: '📦 Update Status',
  apply_store_credit:  '🎁 Store Credit',
  send_email:          '📧 Send Email',
  escalate_ticket:     '🎫 Escalate',
  track_shipment:      '🚚 Track',
  add_internal_note:   '📝 Note',
}

export default function ApprovalsPage() {
  const [approvals, setApprovals] = useState([])
  const [loading, setLoading]     = useState(true)
  const [acting, setActing]       = useState(null)
  const [results, setResults]     = useState({})

  async function load() {
    setLoading(true)
    try {
      const data = await getApprovals()
      setApprovals(data)
    } catch (e) {
      console.error(e)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  async function decide(threadId, approved) {
    setActing(threadId)
    try {
      const result = await approveAction(threadId, approved)
      setResults(prev => ({ ...prev, [threadId]: result }))
      await load()
    } catch (e) {
      console.error(e)
    } finally {
      setActing(null)
    }
  }

  const pending  = approvals.filter(a => a.status === 'pending')
  const resolved = approvals.filter(a => a.status !== 'pending')

  return (
    <div className="p-6 max-w-4xl">
      {/* header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-2xl font-bold text-gray-900">Approval Queue</h2>
          <p className="text-sm text-gray-500 mt-1">
            Actions waiting for human approval before execution
          </p>
        </div>
        <button
          onClick={load}
          className="flex items-center gap-2 text-sm text-gray-600 hover:text-gray-900 border rounded-lg px-3 py-2"
        >
          <RefreshCw size={14} />
          Refresh
        </button>
      </div>

      {/* pending */}
      <section className="mb-8">
        <h3 className="text-sm font-semibold text-gray-500 uppercase tracking-wide mb-3">
          Pending ({pending.length})
        </h3>

        {loading ? (
          <div className="text-sm text-gray-400">Loading...</div>
        ) : pending.length === 0 ? (
          <div className="bg-white border rounded-xl p-8 text-center text-gray-400">
            <CheckCircle size={32} className="mx-auto mb-2 opacity-30" />
            <p className="text-sm">No pending approvals</p>
          </div>
        ) : (
          <div className="space-y-3">
            {pending.map(a => (
              <div key={a.id} className="bg-white border border-amber-200 rounded-xl p-5 shadow-sm">
                <div className="flex items-start justify-between gap-4">
                  <div className="flex-1">
                    <div className="flex items-center gap-2 mb-2">
                      <span className="font-semibold text-gray-900">
                        {ACTION_LABELS[a.action] || a.action}
                      </span>
                      <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${STATUS_COLORS[a.status]}`}>
                        {a.status}
                      </span>
                    </div>
                    <div className="text-sm text-gray-600 space-y-1">
                      <p><span className="font-medium">Thread:</span> <span className="font-mono text-xs">{a.thread_id}</span></p>
                      <p><span className="font-medium">Customer:</span> {a.customer_id || 'unknown'}</p>
                      <p><span className="font-medium">Payload:</span></p>
                      <pre className="bg-gray-50 rounded-lg p-3 text-xs overflow-x-auto">
                        {JSON.stringify(a.payload, null, 2)}
                      </pre>
                    </div>
                    <p className="text-xs text-gray-400 mt-2">
                      {new Date(a.created_at).toLocaleString()}
                    </p>
                  </div>

                  {/* action buttons */}
                  <div className="flex flex-col gap-2">
                    <button
                      onClick={() => decide(a.thread_id, true)}
                      disabled={acting === a.thread_id}
                      className="flex items-center gap-2 bg-green-600 text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-green-700 disabled:opacity-50 transition-colors"
                    >
                      <CheckCircle size={14} />
                      Approve
                    </button>
                    <button
                      onClick={() => decide(a.thread_id, false)}
                      disabled={acting === a.thread_id}
                      className="flex items-center gap-2 bg-red-50 text-red-600 border border-red-200 px-4 py-2 rounded-lg text-sm font-medium hover:bg-red-100 disabled:opacity-50 transition-colors"
                    >
                      <XCircle size={14} />
                      Reject
                    </button>
                  </div>
                </div>

                {/* result after decision */}
                {results[a.thread_id] && (
                  <div className="mt-3 bg-green-50 border border-green-200 rounded-lg p-3 text-sm text-green-800">
                    ✓ {results[a.thread_id]?.result?.message || results[a.thread_id]?.status}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </section>

      {/* resolved */}
      <section>
        <h3 className="text-sm font-semibold text-gray-500 uppercase tracking-wide mb-3">
          Recent ({resolved.length})
        </h3>
        <div className="space-y-2">
          {resolved.map(a => (
            <div key={a.id} className="bg-white border rounded-xl px-5 py-4 flex items-center justify-between">
              <div className="flex items-center gap-3">
                <span className="text-sm font-medium text-gray-700">
                  {ACTION_LABELS[a.action] || a.action}
                </span>
                <span className="font-mono text-xs text-gray-400">{a.thread_id}</span>
              </div>
              <div className="flex items-center gap-3">
                <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${STATUS_COLORS[a.status] || 'bg-gray-100 text-gray-600'}`}>
                  {a.status}
                </span>
                <span className="text-xs text-gray-400">
                  {new Date(a.created_at).toLocaleString()}
                </span>
              </div>
            </div>
          ))}
        </div>
      </section>
    </div>
  )
}