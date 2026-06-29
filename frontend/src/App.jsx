import { BrowserRouter, Routes, Route, NavLink, Navigate, useNavigate } from 'react-router-dom'
import {
  MessageSquare, CheckSquare, BookOpen,
  User, Users, Ticket, BarChart2, LogOut, Shield, UserCircle,
} from 'lucide-react'
import { isLoggedIn, isAdmin, clearAuth, getUsername, getRole } from './api'

import LoginPage      from './pages/LoginPage'
import ChatPage       from './pages/ChatPage'
import ApprovalsPage  from './pages/ApprovalsPage'
import KnowledgePage  from './pages/KnowledgePage'
import CustomerPage   from './pages/CustomerPage'
import MetricsPage    from './pages/MetricsPage'
import UsersPage from './pages/UsersPage'
import TicketsPage from './pages/TicketsPage'
// ── Route guards ──────────────────────────────────────────────

function RequireAuth({ children }) {
  if (!isLoggedIn()) return <Navigate to="/login" replace />
  return children
}

function RequireAdmin({ children }) {
  if (!isLoggedIn()) return <Navigate to="/login" replace />
  if (!isAdmin()) return <Navigate to="/" replace />
  return children
}

// ── Nav config ────────────────────────────────────────────────

const NAV = [
  { to: '/',          icon: MessageSquare, label: 'Chat',           adminOnly: false },
  { to: '/approvals', icon: CheckSquare,   label: 'Approvals',      adminOnly: true  },
  { to: '/kb',        icon: BookOpen,      label: 'Knowledge Base',  adminOnly: true  },
  { to: '/customer',  icon: User,          label: 'Customer 360',   adminOnly: true  },
  { to: '/metrics',   icon: BarChart2,     label: 'Metrics',        adminOnly: true  },
  { to: '/tickets', icon: Ticket, label: 'Tickets', adminOnly: true },
  { to: '/users', icon: Users, label: 'Users', adminOnly: true },
]

// ── Sidebar ───────────────────────────────────────────────────

function Sidebar() {
  const navigate = useNavigate()
  const username = getUsername()
  const role = getRole()
  const admin = isAdmin()

  function logout() {
    clearAuth()
    navigate('/login')
  }

  // filter nav based on role
  const visibleNav = NAV.filter(n => !n.adminOnly || admin)

  return (
    <aside className="w-56 min-h-screen bg-gray-900 text-white flex flex-col">
      <div className="px-6 py-5 border-b border-gray-700">
        <h1 className="text-lg font-bold">Support Copilot</h1>
        <p className="text-xs text-gray-400 mt-0.5">Agentic helpdesk</p>
      </div>

      <nav className="flex-1 px-3 py-4 space-y-1">
        {visibleNav.map(({ to, icon: Icon, label }) => (
          <NavLink
            key={to}
            to={to}
            end={to === '/'}
            className={({ isActive }) =>
              `flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-colors ${
                isActive
                  ? 'bg-indigo-600 text-white'
                  : 'text-gray-400 hover:bg-gray-800 hover:text-white'
              }`
            }
          >
            <Icon size={16} />
            {label}
          </NavLink>
        ))}
      </nav>

      {/* user info + logout */}
      <div className="px-4 py-4 border-t border-gray-700">
        <div className="flex items-center gap-2 mb-3">
          <div className="w-7 h-7 rounded-full bg-indigo-600 flex items-center justify-center">
            <UserCircle size={14} className="text-white" />
          </div>
          <div>
            <p className="text-xs font-medium text-white">{username}</p>
            <div className="flex items-center gap-1">
              <Shield size={10} className={role === 'admin' ? 'text-amber-400' : 'text-gray-500'} />
              <p className="text-xs text-gray-400 capitalize">{role}</p>
            </div>
          </div>
        </div>
        <button
          onClick={logout}
          className="w-full flex items-center gap-2 px-3 py-2 rounded-lg text-xs text-gray-400 hover:bg-gray-800 hover:text-white transition-colors"
        >
          <LogOut size={13} />
          Sign out
        </button>
      </div>
    </aside>
  )
}

// ── App layout ────────────────────────────────────────────────

function AppLayout() {
  return (
    <div className="flex min-h-screen bg-gray-50">
      <Sidebar />
      <main className="flex-1 overflow-auto">
        <Routes>
          <Route path="/" element={
            <RequireAuth><ChatPage /></RequireAuth>
          } />
          <Route path="/approvals" element={
            <RequireAdmin><ApprovalsPage /></RequireAdmin>
          } />
          <Route path="/kb" element={
            <RequireAdmin><KnowledgePage /></RequireAdmin>
          } />
          <Route path="/customer" element={
            <RequireAdmin><CustomerPage /></RequireAdmin>
          } />
          <Route path="/metrics" element={
            <RequireAdmin><MetricsPage /></RequireAdmin>
          } />
          <Route path="/users" element={
            <RequireAdmin><UsersPage /></RequireAdmin>
          } />
          <Route path="/tickets" element={
  <RequireAdmin><TicketsPage /></RequireAdmin>
} />
        </Routes>
      </main>
    </div>
  )
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/*" element={<AppLayout />} />
      </Routes>
    </BrowserRouter>
  )
}