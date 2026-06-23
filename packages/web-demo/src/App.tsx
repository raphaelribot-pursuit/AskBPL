import { RouterProvider } from 'react-router-dom'

import './App.css'
import { router } from './router'

/**
 * Top-level entry. Routes:
 *
 *  - `/` and `/staff/policies` → host page + Ask BPL modal (no sign-in)
 *  - `/internal/console`        → build-team console (basic auth)
 */
export function App() {
  return <RouterProvider router={router} />
}
