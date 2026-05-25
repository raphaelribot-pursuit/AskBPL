import { useCallback, useMemo, useState } from 'react'

import {
  fetchFeedbackList,
  type FeedbackListResponse,
} from '../adminApi'

function pct(part: number, whole: number): string {
  if (whole <= 0) return '0%'
  return `${Math.round((100 * part) / whole)}%`
}

export function Feedback() {
  const apiBase = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'

  const [adminUser, setAdminUser] = useState('vizion_build')
  const [adminPass, setAdminPass] = useState('')
  const [payload, setPayload] = useState<FeedbackListResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const creds = { user: adminUser, password: adminPass }

  const totals = payload?.total ?? 0

  const helpfulPct = useMemo(
    () => pct(payload?.helpful_count ?? 0, totals),
    [payload?.helpful_count, totals],
  )
  const notHelpfulPct = useMemo(
    () => pct(payload?.not_helpful_count ?? 0, totals),
    [payload?.not_helpful_count, totals],
  )

  const refresh = useCallback(async () => {
    setError('')
    if (!adminPass) {
      setError('Set ADMIN_BASIC_PASSWORD from .env.')
      return
    }
    setLoading(true)
    try {
      setPayload(await fetchFeedbackList(apiBase, creds, 50, 0))
    } catch (cause) {
      setPayload(null)
      setError(cause instanceof Error ? cause.message : 'Failed to load feedback')
    } finally {
      setLoading(false)
    }
  }, [adminPass, adminUser, apiBase])

  return (
    <div className="console-section">
      <header className="console-section-head">
        <h2>Feedback</h2>
        <p className="muted">
          Tester thumbs-up / thumbs-down captured after each answer (`POST /feedback`). Session IDs shown are anonymous UUID markers only.
        </p>
      </header>

      <div className="form-grid">
        <label htmlFor="fb-admin-u">Admin user</label>
        <input
          id="fb-admin-u"
          className="brutal-input"
          autoComplete="username"
          value={adminUser}
          onChange={(e) => setAdminUser(e.target.value)}
        />

        <label htmlFor="fb-admin-p">Admin password</label>
        <input
          id="fb-admin-p"
          className="brutal-input"
          type="password"
          autoComplete="current-password"
          value={adminPass}
          onChange={(e) => setAdminPass(e.target.value)}
        />
      </div>

      <div className="row-actions">
        <button type="button" className="primary" onClick={() => void refresh()} disabled={loading}>
          {loading ? 'Loading…' : 'Refresh feedback'}
        </button>
      </div>

      {error && <pre className="error-block">{error}</pre>}

      {payload && totals > 0 && (
        <>
          <ul className="overview-stats">
            <li className="overview-stat brutal-border">
              <span className="overview-stat-label">Total votes</span>
              <span className="overview-stat-value">{totals}</span>
            </li>
            <li className="overview-stat brutal-border">
              <span className="overview-stat-label">Helpful</span>
              <span className="overview-stat-value">
                {payload.helpful_count} ({helpfulPct})
              </span>
            </li>
            <li className="overview-stat brutal-border">
              <span className="overview-stat-label">Not helpful</span>
              <span className="overview-stat-value">
                {payload.not_helpful_count} ({notHelpfulPct})
              </span>
            </li>
          </ul>

          <div className="console-table-wrap">
            <table className="console-table">
              <thead>
                <tr>
                  <th>Time</th>
                  <th>Request ID</th>
                  <th>Helpful</th>
                  <th>Comment</th>
                </tr>
              </thead>
              <tbody>
                {payload.items.length === 0 ? (
                  <tr>
                    <td colSpan={4} className="muted">
                      No rows in this slice.
                    </td>
                  </tr>
                ) : (
                  payload.items.map((row) => (
                    <tr key={row.request_id}>
                      <td>{new Date(row.created_at).toLocaleString()}</td>
                      <td>
                        <code>{row.request_id}</code>
                      </td>
                      <td>{row.helpful ? 'Yes' : 'No'}</td>
                      <td className={row.comment ? undefined : 'muted'}>
                        {row.comment ?? '—'}
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
          <p className="muted" style={{ marginTop: '0.75rem' }}>
            Showing up to {payload.items.length} most recent entries (`GET /v1/internal/feedback`).
          </p>
        </>
      )}

      {payload && totals === 0 && !error && (
        <p className="muted">
          No feedback yet — answers need ratings from the tester UI first.
        </p>
      )}
    </div>
  )
}
