/**
 * Wireframe §6.3 — Settings is read-only in pilot v3. Surfaces the env-level
 * knobs the build team should be able to inspect (API base, docs base,
 * Spline toggle) without offering write controls.
 */
export function Settings() {
  const apiBase = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'
  const docsBase = (import.meta.env.VITE_DOCUMENTS_PUBLIC_BASE ?? '').replace(/\/$/, '') || '—'
  const splineEnabled = import.meta.env.VITE_ENABLE_SPLINE === 'true'
  const liteDemo = import.meta.env.VITE_LITE_DEMO === 'true'

  return (
    <div className="console-section">
      <header className="console-section-head">
        <h2>Settings</h2>
        <p className="muted">
          Read-only in pilot v3 (Wireframe §6.3). These values come from the build
          host's environment, not from a server roundtrip — change them in
          <code> .env</code> and rebuild.
        </p>
      </header>
      <dl className="settings-grid">
        <dt>API base URL</dt>
        <dd>
          <code>{apiBase}</code>
        </dd>
        <dt>Documents base URL</dt>
        <dd>
          <code>{docsBase}</code>
        </dd>
        <dt>Spline 3D avatar</dt>
        <dd>{splineEnabled ? 'enabled' : 'disabled'}</dd>
        <dt>Lite demo (book emoji avatar)</dt>
        <dd>{liteDemo ? 'enabled' : 'disabled'}</dd>
      </dl>
    </div>
  )
}
