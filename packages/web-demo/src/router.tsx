import { createBrowserRouter, Navigate } from 'react-router-dom'

import { ConsoleLayout } from './console/ConsoleLayout'
import { Corpus } from './console/sections/Corpus'
import { Feedback } from './console/sections/Feedback'
import { Overview } from './console/sections/Overview'
import { Routing } from './console/sections/Routing'
import { Sessions } from './console/sections/Sessions'
import { Settings } from './console/sections/Settings'
import { HostPage } from './pages/HostPage'
import { LoginPage } from './pages/LoginPage'
import { RootLayout } from './pages/RootLayout'

/**
 * Wireframe §1.5 calls for three logical routes (`/login`, host, `/internal/console`).
 * The router below collapses that into a single SPA bundle; see
 * `docs/architecture/screen-routing.md` for the SPA-vs-dual-bundle decision.
 *
 * `/staff/policies` is the demo host path from Wireframe §4.2; it is a cosmetic
 * alias for `/` so testers can see a “page behind” the modal that looks like an
 * intranet URL.
 */
export const router = createBrowserRouter([
  {
    element: <RootLayout />,
    children: [
      { path: '/login', element: <LoginPage /> },
      { path: '/', element: <HostPage /> },
      { path: '/staff/policies', element: <HostPage /> },
      {
        path: '/internal/console',
        element: <ConsoleLayout />,
        children: [
          // Wireframe §6.3 — Corpus is the default panel.
          { index: true, element: <Corpus /> },
          { path: 'overview', element: <Overview /> },
          { path: 'corpus', element: <Corpus /> },
          { path: 'routing', element: <Routing /> },
          { path: 'sessions', element: <Sessions /> },
          { path: 'feedback', element: <Feedback /> },
          { path: 'settings', element: <Settings /> },
        ],
      },
      { path: '*', element: <Navigate to="/" replace /> },
    ],
  },
])
