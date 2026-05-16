import { NavLink } from 'react-router-dom'

/**
 * Wireframe §6.3 — six sections, Corpus is the default. The index route
 * (`/internal/console`) renders Corpus, so we also mark the "Corpus" link
 * active when the user is sitting on the bare console root.
 */

type SectionLink = {
  to: string
  label: string
  /** When set, this link is also highlighted at the parent route. */
  defaultRoot?: boolean
}

const SECTIONS: SectionLink[] = [
  { to: 'overview', label: 'Overview' },
  { to: 'corpus', label: 'Corpus', defaultRoot: true },
  { to: 'routing', label: 'Routing' },
  { to: 'sessions', label: 'Sessions' },
  { to: 'feedback', label: 'Feedback' },
  { to: 'settings', label: 'Settings' },
]

export function AdminSidebar({ currentPath }: { currentPath: string }) {
  return (
    <nav className="admin-sidebar" aria-label="Console sections">
      <div className="admin-sidebar-brand">
        <strong>Ask BPL</strong>
        <span className="muted small">internal console</span>
      </div>
      <ul className="admin-sidebar-list">
        {SECTIONS.map((section) => {
          const isRootDefault =
            section.defaultRoot && currentPath.replace(/\/$/, '') === '/internal/console'
          return (
            <li key={section.to}>
              <NavLink
                to={section.to}
                end
                className={({ isActive }: { isActive: boolean }) =>
                  `admin-sidebar-link${isActive || isRootDefault ? ' active' : ''}`
                }
              >
                {section.label}
              </NavLink>
            </li>
          )
        })}
      </ul>
    </nav>
  )
}
