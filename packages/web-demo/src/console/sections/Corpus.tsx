import { useState } from 'react'

/**
 * Wireframe §6.4 — Corpus is the default panel. It shows a stat grid,
 * documents table, and an action row ("Re-ingest all", "Edit routing").
 *
 * The pilot orchestrator exposes `/admin/summary` and `/admin/documents`
 * over basic auth; this panel surfaces those payloads as JSON for now and
 * gives us the slot where the structured stat grid + table will plug in.
 */
export function Corpus() {
  const apiBase = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'

  const [adminUser, setAdminUser] = useState('vizion_build')
  const [adminPass, setAdminPass] = useState('')
  const [summaryJson, setSummaryJson] = useState('')
  const [documentsJson, setDocumentsJson] = useState('')
  const [error, setError] = useState('')

  async function refresh() {
    setSummaryJson('')
    setDocumentsJson('')
    setError('')
    if (!adminPass) {
      setError('Set your admin_basic_password from .env.')
      return
    }
    const basic = typeof btoa === 'function' ? btoa(`${adminUser}:${adminPass}`) : ''

    try {
      const summaryRes = await fetch(`${apiBase}/admin/summary`, {
        headers: { Authorization: `Basic ${basic}` },
      })
      const summaryText = await summaryRes.text()
      if (!summaryRes.ok) throw new Error(summaryText || `${summaryRes.status}`)
      setSummaryJson(summaryText)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'summary failed')
    }

    try {
      const docsRes = await fetch(`${apiBase}/admin/documents`, {
        headers: { Authorization: `Basic ${basic}` },
      })
      const docsText = await docsRes.text()
      if (!docsRes.ok) throw new Error(docsText || `${docsRes.status}`)
      setDocumentsJson(docsText)
    } catch (cause) {
      setError((prior) =>
        `${prior}${prior ? '\n' : ''}${cause instanceof Error ? cause.message : 'documents failed'}`,
      )
    }
  }

  return (
    <div className="console-section">
      <header className="console-section-head">
        <h2>Corpus</h2>
        <p className="muted">
          Snapshot of ingested documents and recent aggregates. Re-ingest controls
          ship in a later pilot — for now this panel reads
          <code> /admin/summary </code>and<code> /admin/documents</code>.
        </p>
      </header>

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
        <button type="button" className="primary" onClick={refresh}>
          Refresh /admin payloads
        </button>
        <button type="button" className="secondary" disabled title="Wireframe §6.4 — pilot v3 stub">
          Re-ingest all
        </button>
        <button type="button" className="secondary" disabled title="Wireframe §6.4 — pilot v3 stub">
          Edit routing
        </button>
      </div>

      {error && <pre className="error-block">{error}</pre>}

      <div className="admin-columns">
        <div>
          <h3>/admin/summary</h3>
          <pre className="json-pane">{summaryJson || '{}'}</pre>
        </div>
        <div>
          <h3>/admin/documents</h3>
          <pre className="json-pane">{documentsJson || '{}'}</pre>
        </div>
      </div>
    </div>
  )
}
