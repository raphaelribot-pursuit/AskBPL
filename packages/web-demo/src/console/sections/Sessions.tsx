/**
 * Wireframe §6.3 — Sessions review panel. Build team reviews recent tester
 * sessions to spot drift, broken routing, and PII rejections.
 */
export function Sessions() {
  return (
    <div className="console-section">
      <header className="console-section-head">
        <h2>Sessions</h2>
        <p className="muted">
          Recent tester sessions, the assistant turns they produced, and the
          response type breakdown (answer / refusal / PII gate). Pilot v3 surfaces
          the list read-only; click-through drill-downs land alongside the routing
          approval workflow.
        </p>
      </header>
      <p className="muted">
        Wire this to <code>GET /admin/sessions</code> when ready. The polling
        cadence is 2 s per Wireframe §6.7 (no SSE in pilot scope).
      </p>
    </div>
  )
}
