import { useState, useRef, useEffect } from 'react'
import { sendMessage } from '../api'
import { Send, Bot, User } from 'lucide-react'

export default function ChatPage() {
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [customerId, setCustomerId] = useState('10')
  const [threadId, setThreadId] = useState(`thread-${Date.now()}`)
  const [loading, setLoading] = useState(false)
  const [pendingApproval, setPendingApproval] = useState(null)
  const bottomRef = useRef(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  async function send() {
    if (!input.trim() || loading) return
    const userMsg = input.trim()
    setInput('')
    setLoading(true)
    setPendingApproval(null)

    // add user message
    setMessages(prev => [...prev, { role: 'user', text: userMsg }])

    // add empty assistant message to stream into
    setMessages(prev => [...prev, { role: 'assistant', text: '' }])

    const result = await sendMessage(
      { message: userMsg, customerId, threadId },
      (chunk) => {
        setMessages(prev => {
          const updated = [...prev]
          updated[updated.length - 1] = {
            ...updated[updated.length - 1],
            text: updated[updated.length - 1].text + chunk,
          }
          return updated
        })
      }
    )

    // pending approval — agent paused for human
    if (result && result.status === 'pending_approval') {
      setPendingApproval(result)
      setMessages(prev => {
        const updated = [...prev]
        updated[updated.length - 1] = {
          ...updated[updated.length - 1],
          text: `⏸ Action paused for approval: **${result.action}**\n\n${result.draft}`,
          isPending: true,
        }
        return updated
      })
    }

    setLoading(false)
  }

  return (
    <div className="flex flex-col h-screen">
      {/* header */}
      <div className="px-6 py-4 border-b bg-white flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold">Chat</h2>
          <p className="text-xs text-gray-500">Live agent conversation</p>
        </div>
        <div className="flex gap-3 items-center">
          <div className="flex flex-col items-end">
            <label className="text-xs text-gray-500 mb-1">Customer ID</label>
            <input
              className="border rounded px-2 py-1 text-sm w-24 text-right"
              value={customerId}
              onChange={e => setCustomerId(e.target.value)}
            />
          </div>
          <div className="flex flex-col items-end">
            <label className="text-xs text-gray-500 mb-1">Thread ID</label>
            <input
              className="border rounded px-2 py-1 text-sm w-36 text-right font-mono"
              value={threadId}
              onChange={e => setThreadId(e.target.value)}
            />
          </div>
          <button
            onClick={() => {
              setThreadId(`thread-${Date.now()}`)
              setMessages([])
              setPendingApproval(null)
            }}
            className="text-xs text-indigo-600 hover:underline mt-4"
          >
            New thread
          </button>
        </div>
      </div>

      {/* messages */}
      <div className="flex-1 overflow-y-auto px-6 py-4 space-y-4">
        {messages.length === 0 && (
          <div className="flex flex-col items-center justify-center h-full text-gray-400">
            <Bot size={40} className="mb-3 opacity-30" />
            <p className="text-sm">Send a message to start</p>
          </div>
        )}
        {messages.map((msg, i) => (
          <div
            key={i}
            className={`flex gap-3 ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
          >
            {msg.role === 'assistant' && (
              <div className="w-8 h-8 rounded-full bg-indigo-100 flex items-center justify-center flex-shrink-0">
                <Bot size={14} className="text-indigo-600" />
              </div>
            )}
            <div
              className={`max-w-xl px-4 py-3 rounded-2xl text-sm whitespace-pre-wrap ${
                msg.role === 'user'
                  ? 'bg-indigo-600 text-white rounded-tr-sm'
                  : msg.isPending
                  ? 'bg-amber-50 border border-amber-200 text-amber-900 rounded-tl-sm'
                  : 'bg-white border text-gray-800 rounded-tl-sm'
              }`}
            >
              {msg.text}
              {msg.isPending && (
                <div className="mt-2 text-xs text-amber-600 font-medium">
                  → Go to Approvals to action this
                </div>
              )}
            </div>
            {msg.role === 'user' && (
              <div className="w-8 h-8 rounded-full bg-indigo-600 flex items-center justify-center flex-shrink-0">
                <User size={14} className="text-white" />
              </div>
            )}
          </div>
        ))}
        {loading && (
          <div className="flex gap-3">
            <div className="w-8 h-8 rounded-full bg-indigo-100 flex items-center justify-center">
              <Bot size={14} className="text-indigo-600" />
            </div>
            <div className="bg-white border px-4 py-3 rounded-2xl rounded-tl-sm">
              <div className="flex gap-1">
                <span className="w-2 h-2 bg-gray-300 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
                <span className="w-2 h-2 bg-gray-300 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
                <span className="w-2 h-2 bg-gray-300 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
              </div>
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {/* input */}
      <div className="px-6 py-4 border-t bg-white">
        <div className="flex gap-3">
          <input
            className="flex-1 border rounded-xl px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
            placeholder="Type a customer message..."
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && !e.shiftKey && send()}
            disabled={loading}
          />
          <button
            onClick={send}
            disabled={loading || !input.trim()}
            className="bg-indigo-600 text-white px-4 py-2.5 rounded-xl hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            <Send size={16} />
          </button>
        </div>
        <p className="text-xs text-gray-400 mt-2">
          Thread: <span className="font-mono">{threadId}</span> · Customer: {customerId}
        </p>
      </div>
    </div>
  )
}