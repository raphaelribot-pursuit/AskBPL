# Shared primitives vs console-only layouts

> Companion to the plan at `/Users/vizion/.cursor/plans/askbpl_screen_structure_6673dcee.plan.md`,
> Wireframe §2 and §6.7.

## What lives where

| Concern                         | Lives in                                     | Used by host modal? | Used by `/internal/console`? |
| ------------------------------- | -------------------------------------------- | ------------------- | ----------------------------- |
| CSS tokens (`:root` vars)       | `packages/web-demo/src/index.css` + `App.css` (`:root`) | Yes                 | Yes (tokens only)             |
| `AvatarTrigger` (FAB)           | `AskPilotShell.tsx`                          | Yes                 | No                            |
| `Modal` shell + toolbar         | `AskPilotShell.tsx`                          | Yes                 | No                            |
| Avatar state machine + drag     | `src/avatar/*`                               | Yes                 | No                            |
| `Bubble`, `CitationCard`, `RoutingCard`, `PIIBanner`, `FeedbackControl` | `src/conversation/TranscriptRows.tsx` | Yes                 | No                            |
| Transcript discriminated union  | `src/conversation/types.ts`                  | Yes                 | No                            |
| `AuthProvider` (in-memory JWT)  | `src/auth/AuthContext.tsx`                   | Yes                 | Console reuses for admin creds in v3+ |
| `AdminSidebar`                  | `src/console/AdminSidebar.tsx`               | No                  | Yes                           |
| `ConsoleLayout`                 | `src/console/ConsoleLayout.tsx`              | No                  | Yes                           |
| Section panels (Overview, Corpus, …) | `src/console/sections/*`                | No                  | Yes                           |

## The single rule

> The console **must not** import anything from `src/conversation/`,
> `src/avatar/`, or `AskPilotShell.tsx`. It may import design tokens via
> `src/index.css` / `src/App.css` and read process-level utilities (e.g.
> `import.meta.env`). That is the entirety of the sharing surface (Wireframe
> §6.7).

This is enforced by code review for the pilot. If we promote the console to
its own Vite bundle (see `screen-routing.md`), the rule becomes
filesystem-enforced — the console bundle won't have the modal files in its
graph at all.

## Why the boundary matters

1. **Different auth posture** — the modal authenticates testers (Userflow
   §3); the console authenticates BPL build-team admins via basic auth
   today, Entra later. Pulling modal primitives into the console couples
   the two flows and makes the planned migration painful.
2. **Different a11y commitments** — the modal is a non-modal dialog with
   strict focus management for tester ergonomics (Wireframe §2.2). The
   console is a standard page layout. Reusing `Modal` for the console
   would mismatch ARIA roles.
3. **Different visual rhythm** — both surfaces share the
   Neubrutomorphism token palette (cyan accent, hard offset shadow, 2–4 px
   borders) but the console uses denser tabular density that the modal
   never needs.

## What changed in this refactor

- `Bubble`, `RoutingDeck`, `CitationCard`, `PIIBanner`, and
  `FeedbackControl` moved out of `AskPilotShell.tsx` and into
  `src/conversation/TranscriptRows.tsx`. They are still only used by the
  modal — but now they're picked by the `TranscriptList` switch instead of
  branching inside a single `<AssistantTurn>` block.
- The console's section files (`src/console/sections/*`) deliberately
  import only `react` and (later) the API client. They do **not** import
  any conversation, avatar, or modal code.
- A future code-owner rule should treat `src/conversation` and
  `src/avatar` as off-limits from `src/console`, mirroring the architecture
  doc above.
