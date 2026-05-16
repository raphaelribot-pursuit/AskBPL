import { Outlet } from 'react-router-dom'

import { AuthProvider } from '../auth/AuthProvider'

/**
 * Top-level layout used by every route. Owns the in-memory `AuthProvider`
 * so `/login`, the host modal, and `/internal/console` see the same
 * `session` reference for the life of the tab. Per Wireframe §3.7 the
 * provider intentionally does not hydrate from `localStorage`.
 */
export function RootLayout() {
  return (
    <AuthProvider>
      <Outlet />
    </AuthProvider>
  )
}
