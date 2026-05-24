import { useCallback, useState } from 'react'

import {
  fetchRoutingRules,
  setRoutingApproval,
  type RoutingRuleRow,
} from '../adminApi'

/**
 * Wireframe §6.3 — Routing with Selvon approval workflow (TRD-RTG-4).
 */
export function Routing() {
  const apiBase = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'

  const [adminUser, setAdminUser] = useState('vizion_build')
  const [adminPass, setAdminPass] = useState('')
  const [rules, setRules] = useState<RoutingRuleRow[]>([])
  const [pendingCount, setPendingCount] = useState(0)
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
      const data = await fetchRoutingRules(apiBase, creds)
      setRules(data.rules)
      setPendingCount(data.pending_approval_count)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Failed to load routing')
    } finally {
      setLoading(false)
    }
  }, [adminPass, adminUser, apiBase])

  async function toggleApproval(rule: RoutingRuleRow, approve: boolean) {
    setError('')
    try {
      await setRoutingApproval(apiBase, creds, rule.rule_id, approve)
      await refresh()
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Approval update failed')
    }
  }

  return (
    <div className="console-section">
      <header className="console-section-head">
        <h2>Routing</h2>
        <p className="muted">
          Policy → owning team mappings. Only Selvon-approved rules are active in
          the pilot ask flow.
        </p>
      </header>

      <div className="form-grid">
        <label htmlFor="routing-admin-u">Admin user</label>
        <input
          id="routing-admin-u"
          className="brutal-input"
          autoComplete="username"
          value={adminUser}
          onChange={(e) => setAdminUser(e.target.value)}
        />

        <label htmlFor="routing-admin-p">Admin password</label>
        <input
          id="routing-admin-p"
          className="brutal-input"
          type="password"
          autoComplete="current-password"
          value={adminPass}
          onChange={(e) => setAdminPass(e.target.value)}
        />
      </div>

      <div className="row-actions">
        <button type="button" className="primary" onClick={() => void refresh()} disabled={loading}>
          {loading ? 'Loading…' : 'Refresh routing'}
        </button>
        {pendingCount > 0 && (
          <span className="muted">{pendingCount} rule(s) pending Selvon approval</span>
        )}
      </div>

      {error && <pre className="error-block">{error}</pre>}

      <div className="console-table-wrap">
        <table className="console-table">
          <thead>
            <tr>
              <th>Policy</th>
              <th>Team</th>
              <th>Contact</th>
              <th>Priority</th>
              <th>Approved</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {rules.length === 0 ? (
              <tr>
                <td colSpan={6} className="muted">
                  Load routing rules after entering admin credentials.
                </td>
              </tr>
            ) : (
              rules.map((rule) => (
                <tr key={rule.rule_id}>
                  <td>
                    <strong>{rule.policy_display_name}</strong>
                    <br />
                    <code>{rule.policy_type}</code>
                  </td>
                  <td>{rule.team_name}</td>
                  <td>{rule.contact_hint}</td>
                  <td>{rule.priority}</td>
                  <td>{rule.selvon_approved ? 'Yes' : 'Pending'}</td>
                  <td>
                    {rule.selvon_approved ? (
                      <button
                        type="button"
                        className="secondary"
                        onClick={() => void toggleApproval(rule, false)}
                      >
                        Revoke
                      </button>
                    ) : (
                      <button
                        type="button"
                        className="primary"
                        onClick={() => void toggleApproval(rule, true)}
                      >
                        Approve
                      </button>
                    )}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}
