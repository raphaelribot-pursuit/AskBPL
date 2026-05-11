import { useState } from 'react'
import './App.css'
import { AskPilotShell } from './AskPilotShell'

/**
 * Top-level chrome for the Ask BPL pilot demo. The chat surface, FAB, and
 * avatar all live inside `<AskPilotShell>`; this component only owns the
 * topbar, the build-team readout, and the segmented view toggle.
 */
export function App() {
  const apiBase = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'
  const docsBase = (import.meta.env.VITE_DOCUMENTS_PUBLIC_BASE ?? '').replace(/\/$/, '')

  const [view, setView] = useState<'demo' | 'build'>('demo')

  const [adminUser, setAdminUser] = useState('vizion_build')
  const [adminPass, setAdminPass] = useState('')
  const [adminSummaryJson, setAdminSummaryJson] = useState('')
  const [adminDocsJson, setAdminDocsJson] = useState('')
  const [adminError, setAdminError] = useState('')

  function loadAdminPanels() {
    setAdminSummaryJson('')
    setAdminDocsJson('')
    setAdminError('')
    if (!adminPass) {
      setAdminError('Set your admin_basic_password from .env.')
      return
    }
    const basic = typeof btoa === 'function' ? btoa(`${adminUser}:${adminPass}`) : ''

    fetch(`${apiBase}/admin/summary`, { headers: { Authorization: `Basic ${basic}` } })
      .then(async (response) => {
        const txt = await response.text()
        if (!response.ok) {
          throw new Error(txt || `${response.status}`)
        }
        return txt
      })
      .then((txt) => setAdminSummaryJson(txt))
      .catch((error: unknown) =>
        setAdminError(error instanceof Error ? error.message : 'summary failed'),
      )

    fetch(`${apiBase}/admin/documents`, { headers: { Authorization: `Basic ${basic}` } })
      .then(async (response) => {
        const txt = await response.text()
        if (!response.ok) {
          throw new Error(txt || `${response.status}`)
        }
        return txt
      })
      .then((txt) => setAdminDocsJson(txt))
      .catch((error: unknown) =>
        setAdminError((prior) =>
          `${prior}${prior ? '\n' : ''}${error instanceof Error ? error.message : 'documents failed'}`,
        ),
      )
  }

  return (
    <div className="ask-root">
      <header className="ask-topbar">
        <div className="brand-stack">
          <span className="brand-title">Ask BPL — pilot modal</span>
          <span className="brand-subtitle">June 2026 demo client</span>
        </div>
        <nav className="segmented">
          <button
            type="button"
            className={`seg ${view === 'demo' ? 'active' : ''}`}
            onClick={() => setView('demo')}
          >
            Demo modal
          </button>
          <button
            type="button"
            className={`seg ${view === 'build' ? 'active' : ''}`}
            onClick={() => setView('build')}
          >
            Build-team readout
          </button>
        </nav>
      </header>

      {view === 'build' && (
        <section className="build-panel brutal-card">
          <h2>Ingest + weekly aggregates</h2>
          <p className="muted">
            Basic-auth credentials mirror <code>admin_basic_*</code> on the orchestrator.
          </p>
          <div className="form-grid">
            <label htmlFor="admin-u">Admin user</label>
            <input
              id="admin-u"
              className="brutal-input"
              autoComplete="username"
              value={adminUser}
              onChange={(e) => setAdminUser(e.target.value)}
            />

            <label htmlFor="admin-p">Admin password</label>
            <input
              id="admin-p"
              className="brutal-input"
              type="password"
              autoComplete="current-password"
              value={adminPass}
              onChange={(e) => setAdminPass(e.target.value)}
            />
          </div>
          <div className="row-actions">
            <button type="button" className="primary" onClick={loadAdminPanels}>
              Refresh /admin payloads
            </button>
          </div>
          {adminError && <pre className="error-block">{adminError}</pre>}
          <div className="admin-columns">
            <div>
              <h3>/admin/summary</h3>
              <pre className="json-pane">{adminSummaryJson || '{}'}</pre>
            </div>
            <div>
              <h3>/admin/documents</h3>
              <pre className="json-pane">{adminDocsJson || '{}'}</pre>
            </div>
          </div>
        </section>
      )}

      {view === 'demo' && <AskPilotShell apiBase={apiBase} docsBase={docsBase} />}
    </div>
  )
}
