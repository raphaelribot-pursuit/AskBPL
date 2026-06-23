import { createBrowserRouter, Navigate } from 'react-router-dom'

import { ConsoleLayout } from './console/ConsoleLayout'
import { Corpus } from './console/sections/Corpus'
import { Feedback } from './console/sections/Feedback'
import { Overview } from './console/sections/Overview'
import { Routing } from './console/sections/Routing'
import { Sessions } from './console/sections/Sessions'
import { Settings } from './console/sections/Settings'
import { HostPage } from './pages/HostPage'
import { RootLayout } from './pages/RootLayout'

/**
 * Public demo routes: host page + modal (no sign-in). Build-team console
 * remains on `/internal/console` with HTTP basic auth.
 */
export const router = createBrowserRouter([
  {
    element: <RootLayout />,
    children: [
      { path: '/', element: <HostPage /> },
      { path: '/staff/policies', element: <HostPage /> },
      { path: '/login', element: <Navigate to="/" replace /> },
      {
        path: '/internal/console',
        element: <ConsoleLayout />,
        children: [
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
