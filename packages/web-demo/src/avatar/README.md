# `src/avatar/`

Implementation of the Ask BPL 3D book avatar described in
[`AskBPL_Avatar_Spec.md`](../../../../AskBPL_Avatar_Spec.md). The spec is the
contract; this folder is the runtime.

## Layout

| File | Role |
|------|------|
| `avatar.types.ts` | `AvatarEvent`, state-name union, persisted-position shape. |
| `avatar.constants.ts` | sessionStorage keys, Spline state-name map, default insets, hold timings. |
| `useAvatarStateMachine.ts` | XState v5 machine for spec §4 + §5 concurrency. |
| `useAvatarDrag.ts` | `@use-gesture/react` drag with viewport bounds + persistence (§6). |
| `useAvatarMinimize.ts` | Pill / edge-dock minimize logic (§7). |
| `AvatarScene.tsx` | Lazy Spline loader with a graceful SVG fallback. |
| `AskBPLAvatar.tsx` | Composed face element used in the toolbar and minimized chrome. |
| `AvatarEventsContext.tsx` | Tiny event bus so descendants can `emit(AvatarEvent)`. |
| `AvatarDebugPanel.tsx` | Dev-only panel that exposes every state (`import.meta.env.DEV`). |
| `scenes/README.md` | Scene authoring contract (object names, state names, perf budget). |

## Wiring

The host modal shell — see `../AskPilotShell.tsx` — owns the request
lifecycle and emits `AvatarEvent`s. The avatar never reaches into request
state directly; it only reacts to events.

## Scene asset

`askbpl-book.splinecode` lives at `packages/web-demo/public/scenes/` once
design exports it. Until then the scene loader probes for the asset and
falls back to a friendly SVG book so the demo always renders.
