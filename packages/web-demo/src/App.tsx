import { RouterProvider } from 'react-router-dom'

import './App.css'
import { router } from './router'

/**
 * Top-level entry. The segmented "demo / build" toggle that lived here in
 * pilot v2 has been replaced with real URL-based routes per the screen plan
 * (`/Users/vizion/.cursor/plans/askbpl_screen_structure_6673dcee.plan.md`):
 *
 *  - `/login`              → Screen 1
 *  - `/` and `/staff/policies` → Screen 2 / 3 (host stub + modal)
 *  - `/internal/console`   → Screen 4 (build-team console)
 *
 * The router itself lives in `./router.tsx`; the SPA-vs-dual-bundle decision
 * is documented in `docs/architecture/screen-routing.md`.
 */
export function App() {
  return <RouterProvider router={router} />
}
