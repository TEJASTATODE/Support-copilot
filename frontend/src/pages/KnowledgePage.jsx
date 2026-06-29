import { useState, useEffect, useRef } from 'react'
import { getDocuments } from '../api'
import { BookOpen, Upload, CheckCircle, Clock, XCircle, RefreshCw, FileText, File } from 'lucide-react'
import axios from 'axios'
import { getToken } from '../api'

const api = axios.create({ baseURL: 'http://localhost:8000' })
api.interceptors.request.use(config => {
  const token = getToken()
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

const STATUS_ICONS = {
  ready:   <CheckCircle size={14} className="text-green-500" />,
  pending: <Clock size={14} className="text-amber-500" />,
  failed:  <XCircle size={14} className="text-red-500" />,
}

const STATUS_COLORS = {
  ready:   'bg-green-100 text-green-800',
  pending: 'bg-amber-100 text-amber-800',
  failed:  'bg-red-100 text-red-800',
}

export default function KnowledgePage() {
  const [docs, setDocs]         = useState([])
  const [loading, setLoading]   = useState(true)
  const [tab, setTab]           = useState('file')

  // file upload state
  const [files, setFiles]             = useState(null)
  const [fileTitle, setFileTitle]     = useState('')
  const [uploading, setUploading]     = useState(false)
  const [uploadResult, setUploadResult] = useState(null)
  const [uploadError, setUploadError]   = useState('')
  const fileRef = useRef()

  // manual text state
  const [title, setTitle]     = useState('')
  const [content, setContent] = useState('')
  const [source, setSource]   = useState('')
  const [adding, setAdding]   = useState(false)
  const [added, setAdded]     = useState(null)

  async function load() {
    setLoading(true)
    try {
      const data = await getDocuments()
      setDocs(data)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
    const t = setInterval(load, 2000)
    return () => clearInterval(t)
  }, [])

  async function uploadFile() {
    if (!files || files.length === 0) return
    setUploading(true)
    setUploadError('')
    setUploadResult(null)
    try {
      const form = new FormData()
      files.forEach(f => form.append('files', f))
      if (fileTitle.trim() && files.length === 1) {
        form.append('title', fileTitle.trim())
      }
      const res = await api.post('/documents/upload', form, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      setUploadResult(res.data)
      setFiles(null)
      setFileTitle('')
      if (fileRef.current) fileRef.current.value = ''
      await load()
    } catch (err) {
      setUploadError(err.response?.data?.detail || 'Upload failed')
    } finally {
      setUploading(false)
    }
  }

  async function submitText() {
    if (!title.trim() || !content.trim()) return
    setAdding(true)
    try {
      await api.post('/documents', { title, content, source })
      setAdded(true)
      setTitle('')
      setContent('')
      setSource('')
      await load()
    } finally {
      setAdding(false)
      setTimeout(() => setAdded(null), 3000)
    }
  }

  function getFileIcon(source) {
    if (!source) return <BookOpen size={16} className="text-gray-400" />
    if (source.endsWith('.pdf')) return <FileText size={16} className="text-red-400" />
    if (source.endsWith('.docx') || source.endsWith('.doc'))
      return <File size={16} className="text-blue-400" />
    return <BookOpen size={16} className="text-gray-400" />
  }

  return (
    <div className="p-6 max-w-4xl">
      {/* header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-2xl font-bold text-gray-900">Knowledge Base</h2>
          <p className="text-sm text-gray-500 mt-1">
            Documents the agent retrieves from during conversations
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

      {/* add document — tabbed */}
      <div className="bg-white border rounded-xl p-6 mb-6">
        <div className="flex gap-1 mb-5 bg-gray-100 p-1 rounded-lg w-fit">
          <button
            onClick={() => setTab('file')}
            className={`px-4 py-1.5 rounded-md text-sm font-medium transition-colors ${
              tab === 'file'
                ? 'bg-white shadow-sm text-gray-900'
                : 'text-gray-500 hover:text-gray-700'
            }`}
          >
            Upload File
          </button>
          <button
            onClick={() => setTab('text')}
            className={`px-4 py-1.5 rounded-md text-sm font-medium transition-colors ${
              tab === 'text'
                ? 'bg-white shadow-sm text-gray-900'
                : 'text-gray-500 hover:text-gray-700'
            }`}
          >
            Paste Text
          </button>
        </div>

        {/* file upload tab */}
        {tab === 'file' && (
          <div className="space-y-3">
            <div>
              <label className="text-xs font-medium text-gray-600 mb-1 block">
                Files{' '}
                <span className="text-gray-400">
                  (PDF, DOCX, TXT — max 20MB each — hold Ctrl to select multiple)
                </span>
              </label>
              <input
                ref={fileRef}
                type="file"
                accept=".pdf,.docx,.doc,.txt"
                multiple
                onChange={e => setFiles(Array.from(e.target.files))}
                className="w-full border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 file:mr-3 file:py-1 file:px-3 file:rounded file:border-0 file:text-xs file:bg-indigo-50 file:text-indigo-700 cursor-pointer"
              />
            </div>

            <div>
              <label className="text-xs font-medium text-gray-600 mb-1 block">
                Title{' '}
                <span className="text-gray-400">
                  (optional — only used when uploading a single file)
                </span>
              </label>
              <input
                className="w-full border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                placeholder="e.g. Q4 2025 Returns Policy"
                value={fileTitle}
                onChange={e => setFileTitle(e.target.value)}
              />
            </div>

            {/* selected files preview */}
            {files && files.length > 0 && (
              <div className="space-y-1">
                {files.map((f, i) => (
                  <div
                    key={i}
                    className="flex items-center gap-2 bg-gray-50 rounded-lg px-3 py-2 text-sm text-gray-600"
                  >
                    <FileText size={14} className="text-gray-400 flex-shrink-0" />
                    <span className="flex-1 truncate">{f.name}</span>
                    <span className="text-xs text-gray-400 flex-shrink-0">
                      {(f.size / 1024).toFixed(0)} KB
                    </span>
                  </div>
                ))}
                <p className="text-xs text-gray-400">
                  {files.length} file{files.length > 1 ? 's' : ''} selected
                </p>
              </div>
            )}

            {uploadError && (
              <p className="text-xs text-red-500 bg-red-50 border border-red-200 rounded-lg px-3 py-2">
                {uploadError}
              </p>
            )}

            {uploadResult && (
              <div className="text-xs bg-green-50 border border-green-200 rounded-lg px-3 py-2 space-y-1">
                <p className="text-green-700 font-medium">
                  ✓ {uploadResult.uploaded} file
                  {uploadResult.uploaded > 1 ? 's' : ''} uploaded successfully
                </p>
                {uploadResult.results.map((r, i) => (
                  <p key={i} className="text-green-600">
                    · "{r.title}" — {r.characters.toLocaleString()} characters extracted
                  </p>
                ))}
                {uploadResult.errors?.map((e, i) => (
                  <p key={i} className="text-red-500">
                    · {e.filename}: {e.error}
                  </p>
                ))}
                {uploadResult.failed > 0 && (
                  <p className="text-amber-600">
                    {uploadResult.failed} file{uploadResult.failed > 1 ? 's' : ''} failed
                  </p>
                )}
              </div>
            )}

            <button
              onClick={uploadFile}
              disabled={uploading || !files || files.length === 0}
              className="bg-indigo-600 text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors flex items-center gap-2"
            >
              <Upload size={14} />
              {uploading
                ? `Uploading ${files?.length || ''} file${files?.length > 1 ? 's' : ''}...`
                : 'Upload & Ingest'}
            </button>
          </div>
        )}

        {/* paste text tab */}
        {tab === 'text' && (
          <div className="space-y-3">
            <div>
              <label className="text-xs font-medium text-gray-600 mb-1 block">
                Title *
              </label>
              <input
                className="w-full border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                placeholder="e.g. Returns Policy"
                value={title}
                onChange={e => setTitle(e.target.value)}
              />
            </div>
            <div>
              <label className="text-xs font-medium text-gray-600 mb-1 block">
                Source URL (optional)
              </label>
              <input
                className="w-full border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                placeholder="e.g. https://yoursite.com/returns"
                value={source}
                onChange={e => setSource(e.target.value)}
              />
            </div>
            <div>
              <label className="text-xs font-medium text-gray-600 mb-1 block">
                Content *
              </label>
              <textarea
                className="w-full border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 resize-none"
                rows={6}
                placeholder="Paste document text here..."
                value={content}
                onChange={e => setContent(e.target.value)}
              />
            </div>
            <button
              onClick={submitText}
              disabled={adding || !title.trim() || !content.trim()}
              className="bg-indigo-600 text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              {adding ? 'Ingesting...' : 'Ingest Text'}
            </button>
            {added && (
              <p className="text-xs text-green-600">
                ✓ Document queued — status will flip to ready in a few seconds
              </p>
            )}
          </div>
        )}
      </div>

      {/* document list */}
      <section>
        <h3 className="text-sm font-semibold text-gray-500 uppercase tracking-wide mb-3">
          Ingested Documents ({docs.length})
        </h3>
        {loading && docs.length === 0 ? (
          <div className="text-sm text-gray-400">Loading...</div>
        ) : docs.length === 0 ? (
          <div className="bg-white border rounded-xl p-8 text-center text-gray-400">
            <BookOpen size={32} className="mx-auto mb-2 opacity-30" />
            <p className="text-sm">No documents yet — upload a file or paste text above</p>
          </div>
        ) : (
          <div className="space-y-2">
            {docs.map(doc => (
              <div
                key={doc.id}
                className="bg-white border rounded-xl px-5 py-4 flex items-center justify-between"
              >
                <div className="flex items-center gap-3">
                  {getFileIcon(doc.source)}
                  <div>
                    <p className="text-sm font-medium text-gray-900">{doc.title}</p>
                    <p className="text-xs text-gray-400">
                      {doc.chunk_count} chunk{doc.chunk_count !== 1 ? 's' : ''} ·{' '}
                      {doc.source && (
                        <span className="font-mono">{doc.source} · </span>
                      )}
                      {new Date(doc.created_at).toLocaleString()}
                    </p>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  {STATUS_ICONS[doc.status]}
                  <span
                    className={`text-xs px-2 py-0.5 rounded-full font-medium ${
                      STATUS_COLORS[doc.status] || 'bg-gray-100 text-gray-600'
                    }`}
                  >
                    {doc.status}
                  </span>
                </div>
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  )
}