/**
 * Wireframe §6.3 — Routing edits panel. Authoring routing tables is out of
 * pilot v3 scope (Wireframe §10) so this panel is a read-only stub today;
 * the route is wired so the build team can deep-link to it.
 */
export function Routing() {
  return (
    <div className="console-section">
      <header className="console-section-head">
        <h2>Routing</h2>
        <p className="muted">
          Suggested routing contacts per policy area. Pilot v3 surfaces the table
          read-only; an approval workflow for edits is queued for the post-pilot
          release (Wireframe §10).
        </p>
      </header>
      <p className="muted">
        Hook this panel to <code>GET /admin/routing</code> when the orchestrator
        exposes it. The screen owns the layout slot.
      </p>
    </div>
  )
}
