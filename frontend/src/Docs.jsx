// src/Docs.jsx — SecureDocs: the document vault UI.
//
// Upload (admin/editor) -> list -> download (15-min pre-signed S3 URL) -> delete (admin).
// A viewer downloading someone else's file gets a 403, which we surface as an
// "Access denied" toast — that's the broken-access-control demo, visible in the UI
// and recorded in the AuditStream feed on the Dashboard tab.

import { useEffect, useRef, useState } from 'react'
import {
  listDocuments,
  uploadDocument,
  downloadDocument,
  deleteDocument,
} from './api'
import { useToast } from './toast.jsx'

const canUpload = (role) => role === 'admin' || role === 'editor'
const canDelete = (role) => role === 'admin'

function formatBytes(n) {
  if (n == null) return '—'
  const units = ['B', 'KB', 'MB', 'GB']
  let v = Number(n)
  let i = 0
  while (v >= 1024 && i < units.length - 1) {
    v /= 1024
    i++
  }
  return `${v.toFixed(v < 10 && i > 0 ? 1 : 0)} ${units[i]}`
}

function formatDate(iso) {
  try {
    return new Date(iso).toLocaleDateString(undefined, {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
    })
  } catch {
    return ''
  }
}

function fileIcon(contentType = '') {
  if (contentType.startsWith('image/')) return 'ti-photo'
  if (contentType === 'application/pdf') return 'ti-file-type-pdf'
  if (contentType.includes('zip') || contentType.includes('compressed')) return 'ti-file-zip'
  return 'ti-file-text'
}

export default function Docs({ user }) {
  const { addToast } = useToast()
  const [docs, setDocs] = useState([])
  const [loading, setLoading] = useState(true)
  const [uploading, setUploading] = useState(false)
  const [description, setDescription] = useState('')
  const [busyId, setBusyId] = useState('')
  const fileRef = useRef(null)

  async function load() {
    setLoading(true)
    try {
      const list = await listDocuments()
      setDocs(Array.isArray(list) ? list : [])
    } catch (err) {
      addToast({ type: 'error', title: 'Could not load documents', lines: [err.message] })
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  async function onUpload(e) {
    e.preventDefault()
    const file = fileRef.current?.files?.[0]
    if (!file) {
      addToast({ type: 'info', title: 'Pick a file first' })
      return
    }
    setUploading(true)
    try {
      await uploadDocument(file, description)
      addToast({ type: 'success', title: 'Uploaded', lines: [file.name] })
      setDescription('')
      if (fileRef.current) fileRef.current.value = ''
      load()
    } catch (err) {
      addToast({ type: 'error', title: 'Upload failed', lines: [err.message] })
    } finally {
      setUploading(false)
    }
  }

  async function onDownload(doc) {
    setBusyId(doc.id)
    try {
      const { download_url } = await downloadDocument(doc.id)
      // User-initiated download via a temporary anchor (popup-blocker safe).
      const a = document.createElement('a')
      a.href = download_url
      a.target = '_blank'
      a.rel = 'noopener'
      document.body.appendChild(a)
      a.click()
      a.remove()
      addToast({ type: 'success', title: 'Download link opened', lines: ['Valid for 15 minutes'] })
    } catch (err) {
      const denied = err.status === 403
      addToast({
        type: 'error',
        title: denied ? 'Access denied' : 'Download failed',
        lines: [denied ? 'You can only download your own files.' : err.message],
      })
    } finally {
      setBusyId('')
    }
  }

  async function onDelete(doc) {
    if (!window.confirm(`Delete "${doc.filename}"? This is logged to the audit trail.`)) return
    setBusyId(doc.id)
    try {
      await deleteDocument(doc.id)
      addToast({ type: 'success', title: 'Deleted', lines: [doc.filename] })
      load()
    } catch (err) {
      addToast({ type: 'error', title: 'Delete failed', lines: [err.message] })
    } finally {
      setBusyId('')
    }
  }

  return (
    <div className="container">
      <div className="page-head">
        <div>
          <h1 className="page-title">SecureDocs</h1>
          <p className="page-sub">
            Encrypted file vault. Downloads use 15-minute pre-signed URLs and every action is
            audited.
          </p>
        </div>
      </div>

      {canUpload(user.role) ? (
        <form className="panel upload-card" onSubmit={onUpload}>
          <div className="upload-row">
            <input ref={fileRef} type="file" className="file-input" />
            <input
              type="text"
              className="desc-input"
              placeholder="Description (optional)"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
            />
            <button className="btn btn-primary" type="submit" disabled={uploading}>
              <i className="ti ti-upload" aria-hidden="true" />
              {uploading ? 'Uploading…' : 'Upload'}
            </button>
          </div>
        </form>
      ) : (
        <div className="notice subtle">
          <i className="ti ti-eye" aria-hidden="true" />
          <div>
            You're a <code>{user.role}</code> — you can view and download your own files. Uploading
            needs editor or admin.
          </div>
        </div>
      )}

      <section className="doc-list">
        <div className="doc-list-head">
          <span>Documents</span>
          <button className="btn btn-ghost btn-sm" onClick={load} disabled={loading}>
            <i className="ti ti-refresh" aria-hidden="true" /> Refresh
          </button>
        </div>

        {loading ? (
          <div className="doc-empty">Loading…</div>
        ) : docs.length === 0 ? (
          <div className="doc-empty">No documents yet. Upload one to get started.</div>
        ) : (
          docs.map((doc) => (
            <div className="doc-row" key={doc.id}>
              <div className="doc-icon">
                <i className={`ti ${fileIcon(doc.content_type)}`} aria-hidden="true" />
              </div>
              <div className="doc-meta">
                <div className="doc-name">{doc.filename}</div>
                <div className="doc-sub">
                  {formatBytes(doc.size_bytes)} · {doc.content_type || 'file'} ·{' '}
                  {formatDate(doc.created_at)}
                  {doc.version ? ` · v${doc.version}` : ''}
                </div>
              </div>
              <div className="doc-actions">
                <button
                  className="btn btn-ghost btn-sm"
                  onClick={() => onDownload(doc)}
                  disabled={busyId === doc.id}
                >
                  <i className="ti ti-download" aria-hidden="true" /> Download
                </button>
                {canDelete(user.role) && (
                  <button
                    className="btn btn-ghost btn-sm btn-icon-danger"
                    onClick={() => onDelete(doc)}
                    disabled={busyId === doc.id}
                    aria-label="Delete"
                  >
                    <i className="ti ti-trash" aria-hidden="true" />
                  </button>
                )}
              </div>
            </div>
          ))
        )}
      </section>
    </div>
  )
}
