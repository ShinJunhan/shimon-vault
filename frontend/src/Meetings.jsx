// src/Meetings.jsx — ShimonMeet: schedule and join meetings.
//
// Create (admin/editor) -> list -> join with token -> cancel (organizer/admin).
// Join tokens expire at meeting end, so joining a finished meeting returns 401 —
// the expired-token-replay path your meetings_router logs to the audit trail.

import { useEffect, useRef, useState } from 'react'
import {
  listMeetings,
  createMeeting,
  joinMeeting,
  cancelMeeting,
} from './api'
import { useToast } from './toast.jsx'

const canCreate = (role) => role === 'admin' || role === 'editor'
const canCancel = (role) => role === 'admin' || role === 'editor'

// datetime-local input value -> "YYYY-MM-DDTHH:MM" for a given Date.
function toLocalInput(d) {
  const pad = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(
    d.getHours()
  )}:${pad(d.getMinutes())}`
}

function defaultStart() {
  const d = new Date()
  d.setMinutes(d.getMinutes() + 60)
  return toLocalInput(d)
}
function defaultEnd() {
  const d = new Date()
  d.setMinutes(d.getMinutes() + 120)
  return toLocalInput(d)
}

function formatWhen(iso) {
  try {
    return new Date(iso).toLocaleString(undefined, {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    })
  } catch {
    return ''
  }
}

function statusClass(status = '') {
  const s = status.toLowerCase()
  if (s === 'active') return 'badge-active'
  if (s === 'scheduled') return 'badge-scheduled'
  return 'badge-default'
}

export default function Meetings({ user }) {
  const { addToast } = useToast()
  const [meetings, setMeetings] = useState([])
  const [loading, setLoading] = useState(true)
  const [creating, setCreating] = useState(false)
  const [busyId, setBusyId] = useState('')

  const titleRef = useRef(null)
  const [form, setForm] = useState({
    title: '',
    description: '',
    scheduled_at: defaultStart(),
    ends_at: defaultEnd(),
    participants: '',
  })

  async function load() {
    setLoading(true)
    try {
      const list = await listMeetings()
      setMeetings(Array.isArray(list) ? list : [])
    } catch (err) {
      addToast({ type: 'error', title: 'Could not load meetings', lines: [err.message] })
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  function setField(key, value) {
    setForm((f) => ({ ...f, [key]: value }))
  }

  async function onCreate(e) {
    e.preventDefault()
    if (!form.title.trim()) {
      addToast({ type: 'info', title: 'Add a title first' })
      titleRef.current?.focus()
      return
    }
    setCreating(true)
    try {
      const participant_ids = form.participants
        .split(',')
        .map((s) => s.trim())
        .filter(Boolean)
      await createMeeting({
        title: form.title.trim(),
        description: form.description.trim() || null,
        // toISOString() gives a timezone-aware UTC value the backend can compare.
        scheduled_at: new Date(form.scheduled_at).toISOString(),
        ends_at: new Date(form.ends_at).toISOString(),
        participant_ids,
      })
      addToast({ type: 'success', title: 'Meeting created', lines: [form.title.trim()] })
      setForm({
        title: '',
        description: '',
        scheduled_at: defaultStart(),
        ends_at: defaultEnd(),
        participants: '',
      })
      load()
    } catch (err) {
      addToast({ type: 'error', title: 'Could not create meeting', lines: [err.message] })
    } finally {
      setCreating(false)
    }
  }

  async function onJoin(meeting) {
    setBusyId(meeting.id)
    try {
      const r = await joinMeeting(meeting.id, meeting.join_token)
      addToast({
        type: 'success',
        title: 'Joined',
        lines: [r.meeting_title || meeting.title],
      })
    } catch (err) {
      const expired = err.status === 401
      addToast({
        type: 'error',
        title: expired ? 'Join rejected' : 'Could not join',
        lines: [expired ? 'Token is invalid or the meeting has ended.' : err.message],
      })
    } finally {
      setBusyId('')
    }
  }

  async function onCopyToken(meeting) {
    try {
      await navigator.clipboard.writeText(meeting.join_token)
      addToast({ type: 'info', title: 'Join token copied' })
    } catch {
      addToast({ type: 'error', title: 'Could not copy token' })
    }
  }

  async function onCancel(meeting) {
    if (!window.confirm(`Cancel "${meeting.title}"? This is logged to the audit trail.`)) return
    setBusyId(meeting.id)
    try {
      await cancelMeeting(meeting.id)
      addToast({ type: 'success', title: 'Meeting cancelled', lines: [meeting.title] })
      load()
    } catch (err) {
      const denied = err.status === 403
      addToast({
        type: 'error',
        title: denied ? 'Not allowed' : 'Could not cancel',
        lines: [denied ? 'Only the organizer or an admin can cancel.' : err.message],
      })
    } finally {
      setBusyId('')
    }
  }

  return (
    <div className="container">
      <div className="page-head">
        <div>
          <h1 className="page-title">ShimonMeet</h1>
          <p className="page-sub">
            Schedule meetings with expiring join tokens. EventBridge sends reminders; tokens stop
            working when the meeting ends.
          </p>
        </div>
      </div>

      {canCreate(user.role) ? (
        <form className="panel meet-form" onSubmit={onCreate}>
          <div className="panel-head">
            <span>New meeting</span>
          </div>
          <div className="meet-grid">
            <label className="field">
              <span className="field-label">Title</span>
              <input
                ref={titleRef}
                type="text"
                value={form.title}
                onChange={(e) => setField('title', e.target.value)}
                placeholder="Weekly sync"
              />
            </label>
            <label className="field">
              <span className="field-label">Description (optional)</span>
              <input
                type="text"
                value={form.description}
                onChange={(e) => setField('description', e.target.value)}
                placeholder="Sprint review + planning"
              />
            </label>
            <label className="field">
              <span className="field-label">Starts</span>
              <input
                type="datetime-local"
                value={form.scheduled_at}
                onChange={(e) => setField('scheduled_at', e.target.value)}
              />
            </label>
            <label className="field">
              <span className="field-label">Ends</span>
              <input
                type="datetime-local"
                value={form.ends_at}
                onChange={(e) => setField('ends_at', e.target.value)}
              />
            </label>
            <label className="field field-wide">
              <span className="field-label">Participant IDs (optional, comma-separated)</span>
              <input
                type="text"
                value={form.participants}
                onChange={(e) => setField('participants', e.target.value)}
                placeholder="user-uuid-1, user-uuid-2"
              />
            </label>
          </div>
          <button className="btn btn-primary" type="submit" disabled={creating}>
            <i className="ti ti-calendar-plus" aria-hidden="true" />
            {creating ? 'Creating…' : 'Create meeting'}
          </button>
        </form>
      ) : (
        <div className="notice subtle">
          <i className="ti ti-eye" aria-hidden="true" />
          <div>
            You're a <code>{user.role}</code> — you can join meetings you're invited to. Creating
            needs editor or admin.
          </div>
        </div>
      )}

      <section className="doc-list">
        <div className="doc-list-head">
          <span>Upcoming meetings</span>
          <button className="btn btn-ghost btn-sm" onClick={load} disabled={loading}>
            <i className="ti ti-refresh" aria-hidden="true" /> Refresh
          </button>
        </div>

        {loading ? (
          <div className="doc-empty">Loading…</div>
        ) : meetings.length === 0 ? (
          <div className="doc-empty">No upcoming meetings. Create one to get started.</div>
        ) : (
          meetings.map((m) => (
            <div className="meet-row" key={m.id}>
              <div className="doc-icon">
                <i className="ti ti-calendar-event" aria-hidden="true" />
              </div>
              <div className="meet-main">
                <div className="meet-title-row">
                  <span className="doc-name">{m.title}</span>
                  <span className={`badge ${statusClass(m.status)}`}>{m.status}</span>
                </div>
                <div className="doc-sub">
                  {formatWhen(m.scheduled_at)} → {formatWhen(m.ends_at)}
                </div>
                {m.description ? <div className="meet-desc">{m.description}</div> : null}
              </div>
              <div className="meet-actions">
                <button
                  className="btn btn-primary btn-sm"
                  onClick={() => onJoin(m)}
                  disabled={busyId === m.id}
                >
                  <i className="ti ti-login" aria-hidden="true" /> Join
                </button>
                <button
                  className="btn btn-ghost btn-sm"
                  onClick={() => onCopyToken(m)}
                  aria-label="Copy join token"
                >
                  <i className="ti ti-copy" aria-hidden="true" /> Token
                </button>
                {canCancel(user.role) && (
                  <button
                    className="btn btn-ghost btn-sm btn-icon-danger"
                    onClick={() => onCancel(m)}
                    disabled={busyId === m.id}
                    aria-label="Cancel meeting"
                  >
                    <i className="ti ti-x" aria-hidden="true" />
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
