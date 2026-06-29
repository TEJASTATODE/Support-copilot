import { useState, useEffect } from 'react'
import { RefreshCw, AlertTriangle, Clock, CheckCircle, Ticket } from 'lucide-react'
import axios from 'axios'
import { getToken } from '../api'

const api = axios.create({ baseURL: 'http://localhost:8000' })
api.interceptors.request.use(config => {
  const token = getToken()
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

const URGENCY_COLORS = {
  high:   'bg-red-100 text-red-800',
  medium: 'bg-amber-100 text-amber-800',
  low:    'bg-green-100 text-green-800',
}

const INTENT_ICONS = {
  refund:    '💰',
  shipping:  '🚚',
  product:   '📦',
  account:   '👤',
  billing:   '💳',
  complaint: '😤',
  inquiry:   '❓',
  other:     '📋',
}

const STATUS_COLORS = {
  new:    'bg-blue-100 text-blue-800',
  open:   'bg-indigo-100 text-indigo-800',
  closed: 'bg-gray-100 text-gray-700',
}

export default function TicketsPage() {
  const [tickets, setTickets] = useState([])
  const [loading, setLoading] = useState(true)

  async function load() {
    setLoading(true)
    try {
      const res = await api.get('/tickets')
      setTickets(res.data)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
    const t = setInterval(load, 10000)  // refresh every 10s
    return () => clearInterval(t)
  }, [])

  const breached  = tickets.filter(t => t.sla_breached)
  const high      = tickets.filter(t => !t.sla_breached && t.urgency === 'high')
  const rest      = tickets.filter(t => !t.sla_breached && t.urgency !== 'high')
  const unclassified = tickets.filter(t => !t.intent)

  return (
    <div className="p-6 max-w-5xl">
      {/* header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-2xl font-bold text-gray-900">Ticket Queue</h2>
          <p className="text-sm text-gray-500 mt-1">
            Auto-triaged every 5 minutes · SLA checked every 15 minutes
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

      {/* summary bar */}
      <div className="grid grid-cols-4 gap-4 mb-6">
        <div className="bg-white border rounded-xl p-4 text-center">
          <p className="text-2xl font-bold text-gray-900">{tickets.length}</p>
          <p className="text-xs text-gray-500 mt-1">Total tickets</p>
        </div>
        <div className="bg-white border border-red-200 rounded-xl p-4 text-center">
          <p className="text-2xl font-bold text-red-600">{breached.length}</p>
          <p className="text-xs text-gray-500 mt-1">SLA breached</p>
        </div>
        <div className="bg-white border rounded-xl p-4 text-center">
          <p className="text-2xl font-bold text-amber-600">{high.length}</p>
          <p className="text-xs text-gray-500 mt-1">High urgency</p>
        </div>
        <div className="bg-white border rounded-xl p-4 text-center">
          <p className="text-2xl font-bold text-blue-600">{unclassified.length}</p>
          <p className="text-xs text-gray-500 mt-1">Pending triage</p>
        </div>
      </div>

      {/* ticket list */}
      {loading && tickets.length === 0 ? (
        <p className="text-sm text-gray-400">Loading...</p>
      ) : tickets.length === 0 ? (
        <div className="bg-white border rounded-xl p-8 text-center text-gray-400">
          <Ticket size={32} className="mx-auto mb-2 opacity-30" />
          <p className="text-sm">No tickets yet</p>
          <p className="text-xs mt-1">
            Tickets are created when customers send messages or submit via the intake endpoint
          </p>
        </div>
      ) : (
        <div className="space-y-2">
          {/* SLA breached first */}
          {breached.length > 0 && (
            <div className="mb-4">
              <h3 className="text-xs font-semibold text-red-600 uppercase tracking-wide mb-2 flex items-center gap-1">
                <AlertTriangle size={12} />
                SLA Breached ({breached.length})
              </h3>
              {breached.map(t => <TicketRow key={t.id} ticket={t} />)}
            </div>
          )}

          {/* high urgency */}
          {high.length > 0 && (
            <div className="mb-4">
              <h3 className="text-xs font-semibold text-amber-600 uppercase tracking-wide mb-2">
                High Urgency ({high.length})
              </h3>
              {high.map(t => <TicketRow key={t.id} ticket={t} />)}
            </div>
          )}

          {/* rest */}
          {rest.length > 0 && (
            <div>
              <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">
                Other ({rest.length})
              </h3>
              {rest.map(t => <TicketRow key={t.id} ticket={t} />)}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

function TicketRow({ ticket }) {
  const URGENCY_COLORS = {
    high:   'bg-red-100 text-red-800',
    medium: 'bg-amber-100 text-amber-800',
    low:    'bg-green-100 text-green-800',
  }
  const INTENT_ICONS = {
    refund: '💰', shipping: '🚚', product: '📦',
    account: '👤', billing: '💳', complaint: '😤',
    inquiry: '❓', other: '📋',
  }
  const STATUS_COLORS = {
    new:  'bg-blue-100 text-blue-800',
    open: 'bg-indigo-100 text-indigo-800',
    closed: 'bg-gray-100 text-gray-700',
  }

  return (
    <div className={`bg-white border rounded-xl px-5 py-4 ${
      ticket.sla_breached ? 'border-red-300' : ''
    }`}>
      <div className="flex items-start justify-between gap-4">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <span className="text-base">
              {INTENT_ICONS[ticket.intent] || '📋'}
            </span>
            <p className="text-sm font-medium text-gray-900 truncate">
              {ticket.subject || `Ticket #${ticket.id}`}
            </p>
            {ticket.sla_breached && (
              <span className="text-xs bg-red-100 text-red-700 px-2 py-0.5 rounded-full font-medium flex items-center gap-1 flex-shrink-0">
                <AlertTriangle size={10} />
                SLA breached
              </span>
            )}
          </div>
          <div className="flex items-center gap-2 flex-wrap">
            {ticket.intent && (
              <span className="text-xs text-gray-500 capitalize">
                {ticket.intent}
              </span>
            )}
            {ticket.assigned_to && (
              <span className="text-xs text-gray-400">
                → {ticket.assigned_to}
              </span>
            )}
            <span className="text-xs text-gray-400">
              #{ticket.id} · customer {ticket.customer_id || '—'} ·{' '}
              {new Date(ticket.created_at).toLocaleString()}
            </span>
          </div>
        </div>
        <div className="flex items-center gap-2 flex-shrink-0">
          {ticket.urgency && (
            <span className={`text-xs px-2 py-0.5 rounded-full font-medium capitalize ${
              URGENCY_COLORS[ticket.urgency] || 'bg-gray-100 text-gray-600'
            }`}>
              {ticket.urgency}
            </span>
          )}
          <span className={`text-xs px-2 py-0.5 rounded-full font-medium capitalize ${
            STATUS_COLORS[ticket.status] || 'bg-gray-100 text-gray-600'
          }`}>
            {ticket.status}
          </span>
        </div>
      </div>
    </div>
  )
}