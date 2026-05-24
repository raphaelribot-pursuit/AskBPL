import { useCallback, useState } from 'react'

import { fetchCorpusStatus, fetchReadout, type ReadoutSummary } from '../adminApi'

/**
 * Wireframe §6.3 — Overview digest backed by /v1/internal/readout + corpus stats.
 */
export function Overview() {
  const apiBase = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'

  const [adminUser, setAdminUser] = useState('vizion_build')
  const [adminPass, setAdminPass] = useState('')
  const [readout, setReadout] = useState<ReadoutSummary | null>(null)
  const [docCount, setDocCount] = useState<number | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const creds = { user: adminUser, password: adminPass }

  const refresh = useCallback(async () => {
    setError('')
    if (!adminPass) {
      setError('Set ADMIN_BASIC_PASSWORD from .env.')
      return
    }
    setLoading(true)
    try {
      const [summary, corpus] = await Promise.all([
        fetchReadout(apiBase, creds),
        fetchCorpusStatus(apiBase, creds),
      ])
      setReadout(summary)
      setDocCount(corpus.doc_count)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Failed to load overview')
    } finally {
      setLoading(false)
    }
  }, [adminPass, adminUser, apiBase])

  return (
    <div className="console-section">
      <header className="console-section-head">
        <h2>Overview</h2>
        <p className="muted">
          High-level pilot health for Selvon rehearsal — answer/refusal mix and corpus
          coverage at a glance.
        </p>
      </header>

      <div className="form-grid">
        <label htmlFor="overview-admin-u">Admin user</label>
        <input
          id="overview-admin-u"
          className="brutal-input"
          autoComplete="username"
          value={adminUser}
          onChange={(e) => setAdminUser(e.target.value)}
        />

        <label htmlFor="overview-admin-p">Admin password</label>
        <input
          id="overview-admin-p"
          className="brutal-input"
          type="password"
          autoComplete="current-password"
          value={adminPass}
          onChange={(e) => setAdminPass(e.target.value)}
        />
      </div>

      <div className="row-actions">
        <button type="button" className="primary" onClick={() => void refresh()} disabled={loading}>
          {loading ? 'Loading…' : 'Refresh overview'}
        </button>
      </div>

      {error && <pre className="error-block">{error}</pre>}

      <ul className="overview-stats">
        <li className="overview-stat brutal-border">
          <span className="overview-stat-label">Documents indexed</span>
          <span className="overview-stat-value">{docCount ?? '—'}</span>
        </li>
        <li className="overview-stat brutal-border">
          <span className="overview-stat-label">Questions (last 7 days)</span>
          <span className="overview-stat-value">
            {readout ? readout.questions_submitted_last_7d : '—'}
          </span>
        </li>
        <li className="overview-stat brutal-border">
          <span className="overview-stat-label">Refusals (approx.)</span>
          <span className="overview-stat-value">
            {readout ? readout.responses_non_answer_approx : '—'}
          </span>
        </li>
        <li className="overview-stat brutal-border">
          <span className="overview-stat-label">Feedback helpful / not</span>
          <span className="overview-stat-value">
            {readout
              ? `${readout.feedback_helpful} / ${readout.feedback_not_helpful}`
              : '—'}
          </span>
        </li>
      </ul>
    </div>
  )
}
