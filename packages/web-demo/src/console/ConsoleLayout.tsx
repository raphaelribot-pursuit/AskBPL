import { Outlet, useLocation } from 'react-router-dom'

import { AdminSidebar } from './AdminSidebar'

/**
 * Console shell per Wireframe §6.1–§6.3:
 *
 *  - ~200 px left rail (`AdminSidebar`)
 *  - main panel switches by nested route (`<Outlet />`)
 *  - top bar with a hint that this is a different auth surface
 *
 * The component is deliberately spare — Wireframe §6.7 says the console
 * shares **only design tokens** with the modal, so we do not import
 * `AskPilotShell` or any conversation primitive here.
 */
export function ConsoleLayout() {
  const location = useLocation()
  return (
    <div className="console-app">
      <header className="console-global-topbar">
        <div className="console-global-brand">
          <strong>Ask BPL</strong>
          <span>Internal console</span>
        </div>
      </header>
      <div className="console-shell">
        <AdminSidebar currentPath={location.pathname} />
        <main className="console-main">
          <header className="console-page-header">
            <div className="console-topbar-meta">
              <h1 className="console-title">Build-team console</h1>
              <p className="muted small">
                Basic-auth admin surface for build-team corpus and session review.
              </p>
            </div>
          </header>
          <section className="console-panel">
            <Outlet />
          </section>
        </main>
      </div>
    </div>
  )
}
