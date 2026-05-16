import { Link, Outlet, useLocation } from 'react-router-dom'

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
    <div className="console-shell">
      <AdminSidebar currentPath={location.pathname} />
      <main className="console-main">
        <header className="console-topbar">
          <div className="console-topbar-meta">
            <h1 className="console-title">Build-team console</h1>
            <p className="muted small">
              Basic-auth admin surface. Not the tester sign-in flow — sign tester
              traffic in via <Link to="/login">/login</Link>.
            </p>
          </div>
        </header>
        <section className="console-panel brutal-card">
          <Outlet />
        </section>
      </main>
    </div>
  )
}
