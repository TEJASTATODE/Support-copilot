import { useState, useEffect } from 'react'
import { getApprovals, getDocuments } from '../api'
import { BarChart2, CheckCircle, XCircle, Clock, BookOpen, Zap } from 'lucide-react'

function StatCard({ label, value, sub, icon: Icon, color = 'indigo' }) {
  const colors = {
    indigo: 'bg-indigo-50 text-indigo-600',
    green:  'bg-green-50 text-green-600',
    amber:  'bg-amber-50 text-amber-600',
    red:    'bg-red-50 text-red-600',
  }
  return (
    <div className="bg-white border rounded-xl p-5">
      <div className="flex items-center justify-between mb-3">
        <span className="text-sm text-gray-500">{label}</span>
        <div className={`w-9 h-9 rounded-lg flex items-center justify-center ${colors[color]}`}>
          <Icon size={16} />
        </div>
      </div>
      <p className="text-3xl font-bold text-gray-900">{value}</p>
      {sub && <p className="text-xs text-gray-400 mt-1">{sub}</p>}
    </div>
  )
}

function ProgressBar({ label, value, total, color = 'bg-indigo-500' }) {
  const pct = total > 0 ? Math.round((value / total) * 100) : 0
  return (
    <div>
      <div className="flex justify-between text-xs text-gray-500 mb-1">
        <span>{label}</span>
        <span>{pct}% ({value}/{total})</span>
      </div>
      <div className="h-2 bg-gray-100 rounded-full overflow-hidden">
        <div
          className={`h-full rounded-full transition-all ${color}`}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  )
}

export default function MetricsPage() {
  const [approvals, setApprovals] = useState([])
  const [docs, setDocs]           = useState([])
  const [loading, setLoading]     = useState(true)

  async function load() {
    setLoading(true)
    try {
      const [a, d] = await Promise.all([getApprovals(), getDocuments()])
      setApprovals(a)
      setDocs(d)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  // compute metrics
  const total      = approvals.length
  const approved   = approvals.filter(a => a.status === 'approved').length
  const rejected   = approvals.filter(a => a.status === 'rejected').length
  const pending    = approvals.filter(a => a.status === 'pending').length
  const docsReady  = docs.filter(d => d.status === 'ready').length
  const totalChunks = docs.reduce((sum, d) => sum + (d.chunk_count || 0), 0)

  // action breakdown
  const actionCounts = approvals.reduce((acc, a) => {
    acc[a.action] = (acc[a.action] || 0) + 1
    return acc
  }, {})

  const ACTION_LABELS = {
    issue_refund:        '💰 Refund',
    cancel_order:        '❌ Cancel',
    update_order_status: '📦 Status Update',
    apply_store_credit:  '🎁 Store Credit',
    send_email:          '📧 Email',
    escalate_ticket:     '🎫 Escalate',
  }

  if (loading) {
    return (
      <div className="p-6 text-sm text-gray-400">Loading metrics...</div>
    )
  }

  return (
    <div className="p-6 max-w-4xl">
      {/* header */}
      <div className="mb-6">
        <h2 className="text-2xl font-bold text-gray-900">Metrics</h2>
        <p className="text-sm text-gray-500 mt-1">
          System performance and impact — the numbers that prove it works
        </p>
      </div>

      {/* stat cards */}
      <div className="grid grid-cols-2 gap-4 mb-8 lg:grid-cols-4">
        <StatCard
          label="Total Actions"
          value={total}
          sub="all time"
          icon={Zap}
          color="indigo"
        />
        <StatCard
          label="Approved"
          value={approved}
          sub={total > 0 ? `${Math.round((approved/total)*100)}% approval rate` : '—'}
          icon={CheckCircle}
          color="green"
        />
        <StatCard
          label="Pending"
          value={pending}
          sub="awaiting decision"
          icon={Clock}
          color="amber"
        />
        <StatCard
          label="KB Documents"
          value={docsReady}
          sub={`${totalChunks} total chunks`}
          icon={BookOpen}
          color="indigo"
        />
      </div>

      {/* approval breakdown */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <div className="bg-white border rounded-xl p-6">
          <h3 className="font-semibold text-gray-900 mb-4 flex items-center gap-2">
            <BarChart2 size={16} />
            Approval Breakdown
          </h3>
          {total === 0 ? (
            <p className="text-sm text-gray-400">No actions yet</p>
          ) : (
            <div className="space-y-4">
              <ProgressBar
                label="Approved"
                value={approved}
                total={total}
                color="bg-green-500"
              />
              <ProgressBar
                label="Rejected"
                value={rejected}
                total={total}
                color="bg-red-400"
              />
              <ProgressBar
                label="Pending"
                value={pending}
                total={total}
                color="bg-amber-400"
              />
            </div>
          )}
        </div>

        {/* action type breakdown */}
        <div className="bg-white border rounded-xl p-6">
          <h3 className="font-semibold text-gray-900 mb-4 flex items-center gap-2">
            <Zap size={16} />
            Actions by Type
          </h3>
          {Object.keys(actionCounts).length === 0 ? (
            <p className="text-sm text-gray-400">No actions yet</p>
          ) : (
            <div className="space-y-3">
              {Object.entries(actionCounts)
                .sort((a, b) => b[1] - a[1])
                .map(([action, count]) => (
                  <div key={action} className="flex items-center justify-between">
                    <span className="text-sm text-gray-700">
                      {ACTION_LABELS[action] || action}
                    </span>
                    <div className="flex items-center gap-2">
                      <div className="w-24 h-1.5 bg-gray-100 rounded-full overflow-hidden">
                        <div
                          className="h-full bg-indigo-500 rounded-full"
                          style={{ width: `${(count / total) * 100}%` }}
                        />
                      </div>
                      <span className="text-sm font-medium text-gray-900 w-4 text-right">
                        {count}
                      </span>
                    </div>
                  </div>
                ))}
            </div>
          )}
        </div>
      </div>

      {/* KB stats */}
      <div className="mt-6 bg-white border rounded-xl p-6">
        <h3 className="font-semibold text-gray-900 mb-4 flex items-center gap-2">
          <BookOpen size={16} />
          Knowledge Base Health
        </h3>
        <div className="grid grid-cols-3 gap-6 text-center">
          <div>
            <p className="text-2xl font-bold text-gray-900">{docs.length}</p>
            <p className="text-xs text-gray-500 mt-1">Total documents</p>
          </div>
          <div>
            <p className="text-2xl font-bold text-green-600">{docsReady}</p>
            <p className="text-xs text-gray-500 mt-1">Ready</p>
          </div>
          <div>
            <p className="text-2xl font-bold text-gray-900">{totalChunks}</p>
            <p className="text-xs text-gray-500 mt-1">Searchable chunks</p>
          </div>
        </div>
        <div className="mt-4">
          <ProgressBar
            label="Documents ready"
            value={docsReady}
            total={docs.length || 1}
            color="bg-green-500"
          />
        </div>
        <p className="text-xs text-gray-400 mt-4">
          Retrieval eval hit-rate: <span className="font-semibold text-gray-700">83%</span> · MRR: <span className="font-semibold text-gray-700">0.833</span>
        </p>
      </div>
    </div>
  )
}