// src/Nav.jsx — shared top bar with page tabs. Lives in App so every
// authenticated page sits under the same navigation.

export default function Nav({ user, view, setView, onLogout }) {
  const tabs = [
    { id: 'console', label: 'Dashboard', icon: 'ti-shield-check' },
    { id: 'docs', label: 'Documents', icon: 'ti-file-lock' },
    { id: 'meetings', label: 'Meetings', icon: 'ti-calendar-event' },
  ]

  return (
    <nav className="nav">
      <div className="nav-brand">
        <span className="brand-dot" />
        ShimonVault <span className="nav-sub">Console</span>
      </div>

      <div className="nav-tabs">
        {tabs.map((t) => (
          <button
            key={t.id}
            className={`nav-tab ${view === t.id ? 'active' : ''}`}
            onClick={() => setView(t.id)}
          >
            <i className={`ti ${t.icon}`} aria-hidden="true" /> {t.label}
          </button>
        ))}
      </div>

      <div className="nav-right">
        <span className="nav-user">
          {user.username} · {user.role}
        </span>
        <button className="btn btn-ghost" onClick={onLogout}>
          <i className="ti ti-logout" aria-hidden="true" /> Sign out
        </button>
      </div>
    </nav>
  )
}
