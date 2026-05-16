/**
 * Wireframe §6.3 — Feedback panel. Aggregates "helpful / not helpful" votes
 * from the modal so the build team can see which answers are landing.
 */
export function Feedback() {
  return (
    <div className="console-section">
      <header className="console-section-head">
        <h2>Feedback</h2>
        <p className="muted">
          Aggregated tester feedback. Pilot v3 expects a weekly digest backed by
          <code> /admin/feedback</code>; the slot is reserved here so the IA
          stays stable while the endpoint lands.
        </p>
      </header>
      <p className="muted">
        PII-gated turns are excluded from feedback aggregates by design
        (Wireframe §5.6, Userflow §5.2.2).
      </p>
    </div>
  )
}
