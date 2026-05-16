import { useEffect } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'

import { AskPilotShell } from '../AskPilotShell'
import { useAuth } from '../auth/useAuth'
import { UiErrorBoundary } from '../UiErrorBoundary'

/**
 * Screen 2 + Screen 3 host (Wireframe §4–§5). The host body is intentionally
 * a stub so testers see the “page behind” the chat modal; the chat surface
 * itself lives in `<AskPilotShell />`, which mounts the wireframe-spec FAB
 * and modal at the page root.
 *
 * The page sits on the wireframe pilot surface
 * (`.askbpl-pilot-surface`, defined in `theme/wireframe-tokens.css`) so
 * the visual language matches Screens 1 + 2 + 3 of the pilot.
 */
export function HostPage() {
  const apiBase = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'
  const docsBase = (import.meta.env.VITE_DOCUMENTS_PUBLIC_BASE ?? '').replace(/\/$/, '')
  const navigate = useNavigate()
  const location = useLocation()
  const { session } = useAuth()

  // Authenticated host. If the user lands here cold (refresh wipes the
  // in-memory token by design — Wireframe §3.7) we bounce to /login and keep
  // the attempted path for the post-login redirect.
  useEffect(() => {
    if (session) return
    navigate('/login', { replace: true, state: { from: location.pathname } })
  }, [session, location.pathname, navigate])

  if (!session) {
    return null
  }

  return (
    <div className="askbpl-pilot-surface pilot-host">
      <header className="pilot-host-topbar">
        <div className="pilot-host-brand">
          <p className="pilot-host-title">BPL Staff Intranet — Policies</p>
          <p className="pilot-host-subtitle">
            Signed in as <strong>{session.email}</strong>
          </p>
        </div>
        <nav className="pilot-host-nav" aria-label="Pilot navigation">
          <Link to="/staff/policies">/staff/policies (demo host)</Link>
          <Link to="/internal/console">Build console</Link>
        </nav>
      </header>

      <section className="pilot-host-stub" aria-label="Host page placeholder">
        <h1>Staff policies — host page (stub)</h1>
        <p>
          This stub stands in for an internal BPL page. Open the floating Ask
          BPL book in the bottom-right to ask any question about policies and
          procedures from Selvon’s curated corpus.
        </p>
        <p>
          Answers cite the source documents inline. Out-of-corpus questions
          surface a routing card with the right team to contact instead of
          guessing.
        </p>
      </section>

      <UiErrorBoundary
        label="AskPilotShell"
        fallback={
          <section className="pilot-host-stub" role="alert">
            <h1>Chat shell crashed</h1>
            <p>
              Open DevTools → Console for the stack trace. The pilot build
              runs in wireframe-modal mode by default; set{' '}
              <code>VITE_ENABLE_AVATAR_SHELL=true</code> only if you want the
              draggable avatar variant back.
            </p>
          </section>
        }
      >
        <AskPilotShell apiBase={apiBase} docsBase={docsBase} />
      </UiErrorBoundary>
    </div>
  )
}
