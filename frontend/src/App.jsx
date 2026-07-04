// src/App.jsx — top-level: login gate + page switching.
// Lightweight view state (no router yet) keeps things easy to follow while the
// product grows; we can swap in react-router once there are deep links to share.

import { useState } from 'react'
import { currentUser, logout } from './api'
import Login from './Login.jsx'
import Nav from './Nav.jsx'
import Console from './Console.jsx'
import Docs from './Docs.jsx'
import Meetings from './Meetings.jsx'

export default function App() {
  const [user, setUser] = useState(currentUser())
  const [view, setView] = useState('console')

  if (!user) {
    return <Login onLogin={() => setUser(currentUser())} />
  }

  const pages = {
    console: <Console user={user} />,
    docs: <Docs user={user} />,
    meetings: <Meetings user={user} />,
  }

  return (
    <>
      <Nav
        user={user}
        view={view}
        setView={setView}
        onLogout={() => {
          logout()
          setUser(null)
        }}
      />
      {pages[view] || pages.console}
    </>
  )
}
