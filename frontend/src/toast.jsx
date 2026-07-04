// src/toast.jsx — in-app notifications.
//
// useToast().addToast({ type, title, lines }) pops a card in the top-right.
// The demo buttons use this to report real Slack/Telegram delivery status.

import { createContext, useContext, useState, useCallback } from 'react'

const ToastContext = createContext(null)
let _id = 0

const ICONS = {
  success: 'ti-circle-check',
  error: 'ti-alert-triangle',
  info: 'ti-info-circle',
}

export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([])

  const remove = useCallback((id) => {
    setToasts((list) => list.filter((t) => t.id !== id))
  }, [])

  const addToast = useCallback(
    ({ type = 'info', title, lines = [], timeout = 6000 }) => {
      const id = ++_id
      setToasts((list) => [...list, { id, type, title, lines }])
      if (timeout) setTimeout(() => remove(id), timeout)
      return id
    },
    [remove]
  )

  return (
    <ToastContext.Provider value={{ addToast }}>
      {children}
      <div className="toast-wrap">
        {toasts.map((t) => (
          <div key={t.id} className={`toast toast-${t.type}`}>
            <i className={`ti ${ICONS[t.type] || ICONS.info} toast-icon`} aria-hidden="true" />
            <div className="toast-body">
              <div className="toast-title">{t.title}</div>
              {t.lines.map((line, i) => (
                <div key={i} className="toast-line">
                  {line}
                </div>
              ))}
            </div>
            <button className="toast-close" onClick={() => remove(t.id)} aria-label="Dismiss">
              <i className="ti ti-x" aria-hidden="true" />
            </button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  )
}

export function useToast() {
  return useContext(ToastContext)
}
