/**
 * Wireframe §6.3 — Overview is a read-only digest. It is intentionally
 * scoped to "what the build team should glance at first" without duplicating
 * the Corpus table.
 */
export function Overview() {
  return (
    <div className="console-section">
      <header className="console-section-head">
        <h2>Overview</h2>
        <p className="muted">
          High-level health of the pilot: corpus status, recent answer/refusal mix,
          and any open issues. Pilot v3 ships this as a read-only digest backed by
          the same admin endpoints the Corpus panel hits.
        </p>
      </header>
      <ul className="overview-stats">
        <li className="overview-stat brutal-border">
          <span className="overview-stat-label">Documents indexed</span>
          <span className="overview-stat-value">—</span>
        </li>
        <li className="overview-stat brutal-border">
          <span className="overview-stat-label">Answered / refused (last 7 days)</span>
          <span className="overview-stat-value">—</span>
        </li>
        <li className="overview-stat brutal-border">
          <span className="overview-stat-label">Open routing edits</span>
          <span className="overview-stat-value">—</span>
        </li>
      </ul>
      <p className="muted">
        Numbers populate once the corresponding admin endpoints land. The IA is
        wired so the build team can hit this panel directly via
        <code> /internal/console/overview</code>.
      </p>
    </div>
  )
}
