import { useCallback, useState } from 'react'

import {
  fetchCorpusStatus,
  triggerReIngest,
  type CorpusStatus,
} from '../adminApi'

/**
 * Wireframe §6.4 — Corpus panel: stat grid, documents table, re-ingest trigger.
 */
export function Corpus() {
  const apiBase = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'

  const [adminUser, setAdminUser] = useState('vizion_build')
  const [adminPass, setAdminPass] = useState('')
  const [corpus, setCorpus] = useState<CorpusStatus | null>(null)
  const [loading, setLoading] = useState(false)
  const [ingesting, setIngesting] = useState(false)
  const [error, setError] = useState('')
  const [ingestNote, setIngestNote] = useState('')

  const creds = { user: adminUser, password: adminPass }

  const refresh = useCallback(async () => {
    setError('')
    setIngestNote('')
    if (!adminPass) {
      setError('Set ADMIN_BASIC_PASSWORD from .env.')
      return
    }
    setLoading(true)
    try {
      setCorpus(await fetchCorpusStatus(apiBase, creds))
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Failed to load corpus')
    } finally {
      setLoading(false)
    }
  }, [adminPass, adminUser, apiBase])

  async function handleReIngest() {
    setError('')
    setIngestNote('')
    if (!adminPass) {
      setError('Set ADMIN_BASIC_PASSWORD from .env.')
      return
    }
    setIngesting(true)
    try {
      const result = await triggerReIngest(apiBase, creds)
      setIngestNote(`Ingest queued: ${result.manifest}`)
      window.setTimeout(() => {
        void refresh()
      }, 2000)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Re-ingest failed')
    } finally {
      setIngesting(false)
    }
  }

  return (
    <div className="console-section">
      <header className="console-section-head">
        <h2>Corpus</h2>
        <p className="muted">
          Selvon curated pilot documents indexed in Postgres + Pinecone. Re-ingest
          runs the manifest batch job in the background.
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
        <button type="button" className="primary" onClick={() => void refresh()} disabled={loading}>
          {loading ? 'Loading…' : 'Refresh corpus'}
        </button>
        <button
          type="button"
          className="secondary"
          onClick={() => void handleReIngest()}
          disabled={ingesting}
        >
          {ingesting ? 'Queueing…' : 'Re-ingest all'}
        </button>
      </div>

      {error && <pre className="error-block">{error}</pre>}
      {ingestNote && <p className="muted">{ingestNote}</p>}

      {corpus && (
        <>
          <ul className="overview-stats">
            <li className="overview-stat brutal-border">
              <span className="overview-stat-label">Documents</span>
              <span className="overview-stat-value">{corpus.doc_count}</span>
            </li>
            <li className="overview-stat brutal-border">
              <span className="overview-stat-label">Pages (est.)</span>
              <span className="overview-stat-value">{corpus.page_count}</span>
            </li>
            <li className="overview-stat brutal-border">
              <span className="overview-stat-label">Chunks</span>
              <span className="overview-stat-value">{corpus.chunk_count}</span>
            </li>
            <li className="overview-stat brutal-border">
              <span className="overview-stat-label">Last ingest</span>
              <span className="overview-stat-value">
                {corpus.last_ingest_at ? new Date(corpus.last_ingest_at).toLocaleString() : '—'}
              </span>
            </li>
          </ul>

          <div className="console-table-wrap">
            <table className="console-table">
              <thead>
                <tr>
                  <th>Title</th>
                  <th>Policy</th>
                  <th>Version</th>
                  <th>Status</th>
                  <th>Ingested</th>
                </tr>
              </thead>
              <tbody>
                {corpus.documents.length === 0 ? (
                  <tr>
                    <td colSpan={5} className="muted">
                      No documents indexed yet — run Re-ingest all.
                    </td>
                  </tr>
                ) : (
                  corpus.documents.map((doc) => (
                    <tr key={doc.document_id}>
                      <td>{doc.title}</td>
                      <td>
                        <code>{doc.policy_type}</code>
                      </td>
                      <td>{doc.version}</td>
                      <td>{doc.ingest_status}</td>
                      <td>
                        {doc.last_ingested_at
                          ? new Date(doc.last_ingested_at).toLocaleString()
                          : '—'}
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  )
}
