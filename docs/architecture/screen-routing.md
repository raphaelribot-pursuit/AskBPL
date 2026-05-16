# Screen routing & bundle choice

> Companion to the plan at `/Users/vizion/.cursor/plans/askbpl_screen_structure_6673dcee.plan.md`.

## URL map

| Route                  | Surface                                        | Source spec                              |
| ---------------------- | ---------------------------------------------- | ---------------------------------------- |
| `/login`               | Screen 1 — standalone tester login             | Wireframe §3, Userflow §3 (Flow A)       |
| `/`                    | Authenticated host stub + FAB + Modal          | Wireframe §4, Userflow §4 (Flow B)       |
| `/staff/policies`      | Cosmetic alias for `/` (demo host path)        | Wireframe §4.2                           |
| `/internal/console`    | Build-team console root → redirects to Corpus  | Wireframe §6                             |
| `/internal/console/corpus`   | Default console panel (stat grid + table) | Wireframe §6.3, §6.4                     |
| `/internal/console/overview` | Read-only digest                          | Wireframe §6.3                           |
| `/internal/console/routing`  | Routing edits                             | Wireframe §6.3                           |
| `/internal/console/sessions` | Session review                            | Wireframe §6.3                           |
| `/internal/console/feedback` | Feedback                                  | Wireframe §6.3                           |
| `/internal/console/settings` | Settings (read-only in v3)                | Wireframe §6.3                           |

Screen 2 and Screen 3 share **one** route. The visible difference is only the
rendered transcript row kind, not a route change (Wireframe §4–§5).

## SPA bundle decision

The Wireframe (§6.7) and Userflow docs gloss the console as a
“**separate frontend bundle/auth**.” The pilot ships it as **one Vite SPA**
that serves all three surfaces, behind one `createBrowserRouter`. Reasons:

1. **Auth boundary today is a route guard, not a deployment boundary.**
   The pilot's “different auth” for `/internal/console` is implemented as a
   basic-auth admin password check against the orchestrator's `/admin/*`
   endpoints — not a different identity provider. Splitting Vite bundles
   does not change that surface today.
2. **No production hosting target yet.** Wireframe §10 leaves SharePoint
   embedding and the Entra activation flow out of pilot scope. Splitting
   bundles now would invent two deployment targets before either is real.
3. **Single source of design tokens.** The console “may only share design
   tokens” per Wireframe §6.7. One bundle still enforces that rule via the
   `src/shared/` boundary (see `shared-vs-console.md`) — the console imports
   tokens (`index.css`) but does not import `AskPilotShell` or any modal
   primitive.
4. **Cheap to split later.** Vite supports multiple entries; if the console
   grows its own identity stack (Entra, MS Graph, etc.) we can promote it to
   its own bundle without touching the orchestrator or the modal code.

A second-bundle escape hatch is documented in `package.json` only when we are
ready to host the console behind a separate origin (e.g. `console.askbpl…`).
For now: one bundle, one router, three top-level surfaces.

## Auth & session

`session_token` lives in memory only — never `localStorage`, never
`sessionStorage` (Wireframe §3.7). It is owned by `src/auth/AuthContext.tsx`
and cleared on:

- Sign-out
- Tab reload (the in-memory value goes away with the JS heap)
- Any 401/403 from `/v1/ask` or `/v1/feedback` — the host page routes back
  to `/login` with a status toast (Wireframe §4.6, Userflow §8.1)

`AskBPL_Avatar_Spec.md` continues to use `sessionStorage` for drag/minimize
UX. That is a separate concern from the auth session and does not violate
the pilot rule above.
