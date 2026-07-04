// src/Console.jsx — the admin/demo console.
//
// Four jobs on one screen:
//   1. Infrastructure health strip (Grafana-style UP/DOWN indicators)
//   2. Live security numbers + a chart (the "Grafana-like" view, our own UI)
//   3. One-click demo buttons for all 5 demo acts
//   4. The AuditStream live feed, polled every few seconds
//
// The top nav now lives in App, so this component renders content only.

import { useCallback, useEffect, useRef, useState } from 'react'
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Tooltip,
  Legend,
  Filler,
} from 'chart.js'
import { Line } from 'react-chartjs-2'
import {
  getSummary,
  getTimeseries,
  getInfra,
  getFeed,
  testNotification,
  runCredentialStuffing,
  runAccessControlAttack,
  runExfiltrationAttack,
  runDdosAttack,
} from './api'
import { useToast } from './toast.jsx'

ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, Tooltip, Legend, Filler)

const POLL_MS = 4000

const SEVERITY_DOT = {
  critical: 'dot-red',
  warning: 'dot-amber',
  info: 'dot-green',
}

function humanize(eventType) {
  if (!eventType) return 'event'
  return eventType.replace(/_/g, ' ')
}

function clockTime(iso) {
  try {
    return new Date(iso).toLocaleTimeString()
  } catch {
    return ''
  }
}

export default function Console({ user }) {
  const isAdmin = user.role === 'admin'
  const { addToast } = useToast()

  const [summary, setSummary] = useState(null)
  const [series, setSeries] = useState(null)
  const [infra, setInfra] = useState(null)
  const [feed, setFeed] = useState([])
  const [connected, setConnected] = useState(true)
  const [busy, setBusy] = useState('') // which demo button is running
  const activeRef = useRef(true)

  const refresh = useCallback(async () => {
    try {
      const [s, ts, i, f] = await Promise.all([
        getSummary(),
        getTimeseries(15),
        getInfra(),
        getFeed(),
      ])
      if (!activeRef.current) return
      setSummary(s)
      setSeries(ts)
      setInfra(i)
      setFeed(f.events || [])
      setConnected(true)
    } catch {
      if (activeRef.current) setConnected(false)
    }
  }, [])

  useEffect(() => {
    if (!isAdmin) return
    activeRef.current = true
    refresh()
    const id = setInterval(refresh, POLL_MS)
    return () => {
      activeRef.current = false
      clearInterval(id)
    }
  }, [isAdmin, refresh])

  async function runDemo(kind, fn, messages) {
    setBusy(kind)
    try {
      const r = await fn()
      addToast({ type: 'info', title: messages.started, lines: messages.lines(r) })
      setTimeout(refresh, 1500)
    } catch (err) {
      addToast({ type: 'error', title: messages.failed, lines: [err.message] })
    } finally {
      setBusy('')
    }
  }

  async function onTestNotification() {
    setBusy('notify')
    try {
      const r = await testNotification()
      const slack = r.channels.slack
      const telegram = r.channels.telegram
      addToast({
        type: r.all_ok ? 'success' : 'error',
        title: r.all_ok ? 'Notification delivered' : 'Notification partly failed',
        lines: [
          `Slack: ${slack.ok ? 'delivered' : 'failed — ' + (slack.error || 'unknown')}`,
          `Telegram: ${telegram.ok ? 'delivered' : 'failed — ' + (telegram.error || 'unknown')}`,
        ],
      })
    } catch (err) {
      addToast({ type: 'error', title: 'Could not send notification', lines: [err.message] })
    } finally {
      setBusy('')
    }
  }

  const onCredentialStuffing = () =>
    runDemo('attack-creds', runCredentialStuffing, {
      started: 'Credential-stuffing attack started',
      failed: 'Could not start simulation',
      lines: (r) => [`${r.attempts} login attempts from ${r.attacker_ip}`, 'Watch the live feed below.'],
    })

  const onAccessControl = () =>
    runDemo('attack-access', runAccessControlAttack, {
      started: 'Broken access control attack started',
      failed: 'Could not start simulation',
      lines: (r) => [`${r.attempts} attempts against document ${r.target_document}`, 'Watch the live feed below.'],
    })

  const onExfiltration = () =>
    runDemo('attack-exfil', runExfiltrationAttack, {
      started: 'Bulk exfiltration attack started',
      failed: 'Could not start simulation',
      lines: (r) => [`${r.attempts} rapid downloads — rate limiter should trip`, 'Watch the live feed below.'],
    })

  const onDdos = () =>
    runDemo('attack-ddos', runDdosAttack, {
      started: 'Traffic flood started',
      failed: 'Could not start simulation',
      lines: (r) => [`${r.total_requests} requests, concurrency ${r.concurrency}`, 'Watch request rate below.'],
    })

  const chartData = {
    labels: series?.labels || [],
    datasets: [
      {
        label: 'Login failures',
        data: series?.failures || [],
        borderColor: '#E24B4A',
        backgroundColor: 'rgba(226,75,74,0.12)',
        fill: true,
        tension: 0.3,
        pointRadius: 0,
        borderWidth: 2,
      },
      {
        label: 'Alerts',
        data: series?.alerts || [],
        borderColor: '#EF9F27',
        backgroundColor: 'rgba(239,159,39,0.10)',
        fill: true,
        tension: 0.3,
        pointRadius: 0,
        borderWidth: 2,
      },
      {
        label: 'Total events',
        data: series?.total || [],
        borderColor: '#1D9E75',
        backgroundColor: 'rgba(29,158,117,0.08)',
        fill: true,
        tension: 0.3,
        pointRadius: 0,
        borderWidth: 2,
      },
    ],
  }

  const chartOptions = {
    responsive: true,
    maintainAspectRatio: false,
    interaction: { intersect: false, mode: 'index' },
    plugins: {
      legend: { labels: { boxWidth: 10, font: { size: 11 }, color: '#6b6b67' } },
    },
    scales: {
      x: { ticks: { font: { size: 10 }, color: '#9b9b97', maxRotation: 0, autoSkip: true } },
      y: { beginAtZero: true, ticks: { font: { size: 10 }, color: '#9b9b97', precision: 0 } },
    },
  }

  if (!isAdmin) {
    return (
      <div className="container">
        <div className="notice">
          <i className="ti ti-lock" aria-hidden="true" />
          <div>
            <strong>Admin access required.</strong> The security dashboard and demo controls
            are admin-only. You're signed in as <code>{user.role}</code> — try the Documents tab.
          </div>
        </div>
      </div>
    )
  }

  const anyBusy = busy !== ''

  return (
    <div className="container">
      {!connected && (
        <div className="reconnect">
          <span className="pulse" /> Reconnecting to the API…
        </div>
      )}

      {/* ── Health strip (Grafana-style UP/DOWN) ── */}
      <section className="health-strip">
        <HealthPill
          label="App"
          up={true /* if this rendered at all, the app answered the request */}
        />
        <HealthPill label="Prometheus" up={infra?.prometheus_up} />
        <HealthPill
          label="CPU"
          up={infra?.cpu_percent != null}
          value={infra?.cpu_percent != null ? `${infra.cpu_percent}%` : 'n/a'}
          warn={infra?.cpu_percent != null && infra.cpu_percent > 80}
        />
        <HealthPill
          label="Memory"
          up={infra?.memory_percent != null}
          value={infra?.memory_percent != null ? `${infra.memory_percent}%` : 'n/a'}
          warn={infra?.memory_percent != null && infra.memory_percent > 85}
        />
        <HealthPill
          label="Req/sec"
          up={infra?.request_rate != null}
          value={infra?.request_rate != null ? infra.request_rate : 'n/a'}
        />
      </section>

      {/* ── Summary cards ── */}
      <section className="cards">
        <Stat label="Alerts" value={summary?.alerts} icon="ti-alert-triangle" tone="amber" />
        <Stat label="Blocked IPs" value={summary?.blocked_ips} icon="ti-ban" tone="red" />
        <Stat label="Open incidents" value={summary?.open_incidents} icon="ti-flame" tone="red" />
        <Stat label="Login failures" value={summary?.login_failures} icon="ti-key" tone="amber" />
        <Stat label="Downloads" value={summary?.downloads} icon="ti-download" tone="teal" />
        <Stat label="Total events" value={summary?.total_events} icon="ti-activity" tone="teal" />
      </section>

      <div className="grid-2">
        {/* ── Demo controls ── */}
        <section className="panel">
          <div className="panel-head">
            <span>Demo controls</span>
          </div>
          <p className="panel-sub">
            Trigger a scenario and watch the response land in the feed and on your phone.
          </p>
          <div className="demo-actions">
            <button className="btn btn-primary" onClick={onTestNotification} disabled={anyBusy}>
              <i className="ti ti-bell" aria-hidden="true" />
              {busy === 'notify' ? 'Sending…' : 'Send test notification'}
            </button>
            <button className="btn btn-danger" onClick={onCredentialStuffing} disabled={anyBusy}>
              <i className="ti ti-shield-bolt" aria-hidden="true" />
              {busy === 'attack-creds' ? 'Launching…' : 'Act 2 · Credential stuffing'}
            </button>
            <button className="btn btn-danger" onClick={onAccessControl} disabled={anyBusy}>
              <i className="ti ti-lock-access" aria-hidden="true" />
              {busy === 'attack-access' ? 'Launching…' : 'Act 3 · Broken access control'}
            </button>
            <button className="btn btn-danger" onClick={onExfiltration} disabled={anyBusy}>
              <i className="ti ti-download" aria-hidden="true" />
              {busy === 'attack-exfil' ? 'Launching…' : 'Act 4 · Bulk exfiltration'}
            </button>
            <button className="btn btn-danger" onClick={onDdos} disabled={anyBusy}>
              <i className="ti ti-wave-square" aria-hidden="true" />
              {busy === 'attack-ddos' ? 'Launching…' : 'Act 5 · Traffic flood'}
            </button>
          </div>
          <div className="prom-line">
            Prometheus:{' '}
            <span className={summary?.prometheus_up ? 'ok' : 'down'}>
              {summary?.prometheus_up ? 'connected' : 'unreachable'}
            </span>
          </div>
        </section>

        {/* ── Chart ── */}
        <section className="panel">
          <div className="panel-head">
            <span>Activity · last 15 min</span>
          </div>
          <div className="chart-box">
            <Line data={chartData} options={chartOptions} />
          </div>
        </section>
      </div>

      {/* ── Live feed ── */}
      <section className="feed">
        <div className="feed-header">
          <span>AuditStream · recent activity</span>
          <span className="feed-live">
            <span className="pulse" /> Live
          </span>
        </div>
        {feed.length === 0 ? (
          <div className="feed-empty">No events yet. Run a demo to see the stream react.</div>
        ) : (
          feed.slice(0, 25).map((e, i) => (
            <div className="feed-row" key={e.event_id || e.id || i}>
              <span className={`feed-dot ${SEVERITY_DOT[e.severity] || 'dot-green'}`} />
              <span className="feed-text">
                <strong>{e.user_id ? 'user' : e.ip_address || 'system'}</strong>{' '}
                {humanize(e.event_type)}
                {e.resource ? <span className="feed-res"> · {e.resource}</span> : null}
              </span>
              <span className="feed-time">{clockTime(e.created_at)}</span>
            </div>
          ))
        )}
      </section>
    </div>
  )
}

function Stat({ label, value, icon, tone }) {
  return (
    <div className="card">
      <div className={`card-icon icon-${tone}`}>
        <i className={`ti ${icon}`} aria-hidden="true" />
      </div>
      <div className="card-num">{value ?? '—'}</div>
      <div className="card-label">{label}</div>
    </div>
  )
}

function HealthPill({ label, up, value, warn }) {
  const status = up === null || up === undefined ? 'unknown' : up ? (warn ? 'warn' : 'ok') : 'down'
  const statusText = status === 'ok' ? 'HEALTHY' : status === 'warn' ? 'HIGH' : status === 'down' ? 'DOWN' : '—'
  return (
    <div className={`health-pill health-${status}`}>
      <span className="health-dot" />
      <span className="health-label">{label}</span>
      <span className="health-value">{value !== undefined ? value : statusText}</span>
    </div>
  )
}