# Ask BPL — 3D Avatar (Spline) Implementation Spec

> **Audience:** Cursor IDE agent + Vizion engineering (Denward Lee Aulder).
> **Aligned to:** Ask BPL PRD v3 (Apr 29, 2026) and TRD v0.3 (May 8, 2026).
> **Status:** Implementation-ready. This document is the contract — every behavior, file, and integration point named here should be produced.
> **Replaces:** the placeholder book icon (📖) referenced at TRD-UI-2.

---

## 1. What you are building

A friendly 3D animated book character that serves as the visible identity of the Ask BPL assistant. The avatar lives inside the existing avatar modal (`avatar-modal-mockup.jsx`) and reacts to the orchestrator's request lifecycle. It is **movable**, **minimizable**, and **never blocks the host page** — these are hard requirements from TRD-UI-1.

Think of the lineage: Microsoft's "Zippy" / Clippy successors — persistent, expressive, opt-in. The avatar should feel alive without being annoying. Subtle by default; expressive at meaningful moments.

### Character description

A 3D cartoon book with:
- A hardcover body (BPL-appropriate color — final palette deferred, use a friendly mid-blue placeholder matching the modal accent `#185FA5`)
- Two large, expressive eyes on the front cover
- A wide, friendly smile
- Pages visible along the right edge that can riffle and flip
- No arms by default (gestures are conveyed via tilt, bounce, and page motion); optional small stub arms only if Spline scene budget allows

Visual reference: a 3D cartoon book character with big eyes and a smiling face (PNGTree-style, Pixar-adjacent — not flat icon, not photoreal).

---

## 2. Tech stack

| Layer | Choice | Why |
|---|---|---|
| 3D authoring | **Spline** (spline.design) | Designer-friendly scene authoring; clean web export; supports state-driven events out of the box |
| Runtime | **`@splinetool/react-spline`** | Official React wrapper; loads `.splinecode` exports |
| Loader | **`@splinetool/runtime`** | Underlying runtime; exposes `findObjectByName`, `emitEvent`, and state APIs |
| Host | React component inside the existing avatar modal | Integrates with the wireframed flow |
| State machine | **XState** (recommended) or a typed reducer | Animation states are finite and well-defined; XState gives us visualization for free |
| Drag | **`@use-gesture/react`** + `framer-motion` | Pointer events, momentum, bounds |
| Persistence | `sessionStorage` for position + minimize state | Survives reload within a session; cleared on logout |

> **Note for Cursor:** Spline's React package is the only correct way to embed a Spline scene in a React app. Do not attempt to load the `.splinecode` URL via raw `<iframe>` — we need the runtime API to trigger animation states programmatically.

---

## 3. File structure

Create the following under `src/avatar/`:

```
src/avatar/
├── AskBPLAvatar.tsx          # Top-level component; owns drag + minimize
├── AvatarScene.tsx            # Spline scene loader; exposes a ref API
├── useAvatarStateMachine.ts   # XState (or reducer) for the 14 behaviors
├── useAvatarDrag.ts           # Drag mechanics, bounds, persistence
├── useAvatarMinimize.ts       # Minimize / restore + dormancy rules
├── avatar.types.ts            # Shared types
├── avatar.constants.ts        # Spline object names, event names, defaults
├── scenes/
│   └── askbpl-book.splinecode # Spline scene export (placeholder until art lands)
└── README.md                  # Pointer to this spec + scene authoring notes
```

Wire `AskBPLAvatar` into the existing `avatar-modal-mockup.jsx` (rename to `.tsx` if the project allows). It replaces the `📖` placeholder in both the floating trigger and the modal header.

---

## 4. The 14 behaviors (state machine)

Each behavior is a state in the avatar's finite state machine. Spline animations should be authored as named timelines/states matching the `splineState` column below.

| # | State | Trigger | Spline state name | Visual behavior | Duration |
|---|---|---|---|---|---|
| 1 | `idle` | Default when modal open + no activity | `Idle` | Slow blinks (~4s interval), gentle bob (2s loop), occasional page flutter (every 12–20s) | Loop |
| 2 | `listening` | User focuses input or starts typing | `Listening` | Leans forward ~5°, eyes widen slightly, blink rate slows | Hold while typing |
| 3 | `thinking` | `POST /v1/ask` fired, awaiting retrieval | `Thinking` | Eyes glance up-and-right, small "hmm" tilt, pages riffle softly | Loop until next state |
| 4 | `retrieving` | Pinecone query in flight | `Retrieving` | More active page flipping, eyes scan left-right as if reading | Loop until next state |
| 5 | `answering` | Claude generation streaming | `Answering` | Soft pulse/glow on cover, mouth animates subtly | Loop until response complete |
| 6 | `success` | Answer + valid citation returned | `Success` | Satisfied nod, eyes brighten, brief widened smile | ~1.2s, return to `idle` |
| 7 | `refusalOutOfCorpus` | Refusal with routing card | `RefusalSoft` | Apologetic shrug (book tilts side-to-side once), gentle "not found" expression | ~1.5s, return to `idle` |
| 8 | `refusalPII` | PII detected — input rejected | `RefusalAlert` | Alert posture (sits up straight), eyes widen briefly, slight back-lean | ~1.2s, return to `idle` |
| 9 | `routing` | Routing card animates in | `Routing` | Book tilts toward the routing card (camera-relative), eyes track the card | ~1s, return to `idle` |
| 10 | `greeting` | First open of session | `Greeting` | Pages "wave" (flutter outward), big smile, slight hop | ~2s, one-time per session |
| 11 | `goodbye` | Modal closing | `Goodbye` | Tip of front cover (like a bow), brief wave-flutter | ~1s, then unmount |
| 12 | `error` | Network/server error (5xx, timeout) | `Error` | Confused expression — eyes cross slightly, small head-shake. **Visually distinct from refusal** so testers can diagnose | ~1.5s, return to `idle` |
| 13 | `dragging` | User is dragging the avatar | `Dragging` | "Picked up" reaction: eyes widen, slight wobble in-hand, smile holds | While drag active |
| 14 | `minimized` | User collapsed the avatar | `Minimized` (or scene paused) | **Dormant.** No idle animations. No attention-pulling motion. Static thumbnail or paused frame | Until restored |

### State transition rules

```
idle ──(focus input)──> listening
listening ──(submit)──> thinking ──(retrieval starts)──> retrieving
retrieving ──(chunks above threshold)──> answering ──(complete + cited)──> success ──> idle
retrieving ──(below threshold)──> refusalOutOfCorpus ──> routing ──> idle
* ──(PII detected at input)──> refusalPII ──> idle  (skips retrieving/answering)
* ──(5xx/timeout)──> error ──> idle
any ──(drag start)──> dragging ──(drag end)──> previous
any ──(minimize)──> minimized ──(restore)──> idle
modal open (first time this session) ──> greeting ──> idle
modal close ──> goodbye ──> unmount
```

**Concurrency rule:** `dragging` and `minimized` are orthogonal to the request lifecycle. If a response arrives while minimized, queue the resulting state (`success` / `refusal*`) and surface only a subtle notification dot on the minimized avatar — do not auto-restore.

---

## 5. Integration with the orchestrator

The avatar listens to events emitted by the modal's request handler. **Do not** have the avatar poll or own request state directly — keep it a pure consumer of events.

### Events the modal must emit

```ts
type AvatarEvent =
  | { type: 'INPUT_FOCUSED' }
  | { type: 'INPUT_BLURRED' }
  | { type: 'REQUEST_SUBMITTED' }       // POST /v1/ask fired
  | { type: 'RETRIEVAL_STARTED' }       // optional, if orchestrator streams progress
  | { type: 'GENERATION_STARTED' }      // first token from Claude
  | { type: 'RESPONSE_SUCCESS' }        // answer + valid citation
  | { type: 'RESPONSE_REFUSAL_CORPUS' } // out-of-corpus refusal
  | { type: 'RESPONSE_REFUSAL_PII' }    // PII_DETECTED error (400)
  | { type: 'RESPONSE_ROUTING' }        // routing card just rendered
  | { type: 'RESPONSE_ERROR' }          // 5xx / timeout / citation verification failure
  | { type: 'MODAL_OPENED', firstThisSession: boolean }
  | { type: 'MODAL_CLOSING' };
```

Wire these from `avatar-modal-mockup.jsx` using a context provider or a simple event emitter. The `useAvatarStateMachine` hook consumes them.

### Mapping to TRD requirements

| Avatar state | TRD requirement satisfied |
|---|---|
| `refusalPII` | TRD-GRD-1, GRD-2 (PII rejected before retrieval) |
| `refusalOutOfCorpus` + `routing` | TRD-GEN-4, RTG-1 through RTG-5 |
| `success` (only fires after citation verifier passes) | TRD-GEN-3, GEN-6 |
| `error` (distinct from refusal) | TRD-LOG-3 (errors not leaked to client; avatar surfaces a generic confused state) |
| `minimized` | TRD-UI-1 (modal never blocks the page) |

---

## 6. Drag mechanics

```ts
// useAvatarDrag.ts — behavior contract

- Pointer-based (mouse + touch). Use @use-gesture/react `useDrag`.
- The drag handle is the avatar itself, not the modal chrome. Dragging the avatar moves the whole modal as one unit.
- Bounds: stay within the viewport with a 16px safe-area inset. Clamp on drag, don't reject.
- Momentum: small flick momentum (framer-motion `dragMomentum: true`, low velocity decay).
- Snap: optional snap-to-corner if released within 80px of a viewport corner. Default off; expose as a prop.
- Persistence: store `{ x, y }` in sessionStorage under key `askbpl.avatar.position`. Restore on mount.
- Reaction: emit `DRAG_START` → state machine → `dragging`. On `DRAG_END`, return to prior state with a 200ms "settled" micro-animation.
- Z-index: dragging raises z-index to ensure the avatar is above all host-page content.
```

The default mount position is bottom-right, 24px inset, matching the wireframe's avatar trigger location.

---

## 7. Minimize behavior

Two collapsed forms, user-selectable via a small caret on the modal header:

### 7a. **Pill** (default minimize)
- The modal collapses to a small rounded pill (~120px wide) showing just the avatar's face + a "Ask BPL" label.
- Stays in the user's last-dragged position.
- Click to restore full modal.

### 7b. **Edge dock** (long-press minimize, or explicit option)
- The avatar tucks against the nearest viewport edge, leaving a 32px-wide tab visible.
- Smallest possible footprint — for when the avatar is truly in the way.
- Click the tab to restore.

### Dormancy rules (both forms)

- **No idle animations run while minimized.** Pause the Spline scene or set state to `Minimized`. This is a battery/CPU concern *and* a respect-the-user concern.
- **No attention-pulling motion** (no bounce, no wave) to summon the user back.
- A **subtle notification dot** (6px, modal accent color) may appear on the minimized form if a response arrived while minimized. The dot is static — no pulse, no animation. Clearing happens on restore.

### Persistence

```ts
sessionStorage['askbpl.avatar.minimized'] = 'none' | 'pill' | 'dock'
sessionStorage['askbpl.avatar.position']  = '{"x":<number>,"y":<number>}'
```

Cleared on logout (which clears the session token per TRD-AUTH-4).

---

## 8. Spline scene authoring notes

These notes are for whoever authors the `.splinecode` file (designer or engineer). Cursor cannot author the Spline scene itself — only wire it up. Treat the scene file as a contract:

**Required named objects in the scene:**
- `Book` — root mesh (parent of cover, pages, eyes, mouth)
- `Cover_Front`, `Cover_Back`, `Spine`
- `Pages` — animated group for riffle/flip
- `Eye_L`, `Eye_R` — drivable for blink, widen, glance direction
- `Mouth` — drivable for smile, neutral, slight-frown (refusal), confused (error)

**Required named states (Spline "States" panel):**
Exactly the 14 names in the `Spline state name` column of Section 4. The runtime triggers these by name via `splineApp.setVariable('avatarState', 'Idle')` (or per Spline's current state API — verify against `@splinetool/runtime` version at install time).

**Performance budget:**
- Scene under 2 MB compiled.
- 60 fps on a mid-range laptop; 30 fps minimum on mobile.
- Pause rendering when minimized (`splineApp.stop()`); resume on restore (`splineApp.play()`).

---

## 9. Accessibility

- The avatar is **decorative** — it must not be the only signal of any state. Every state change that matters (success, refusal, error, routing) must also have a text or ARIA-live equivalent in the modal body. The avatar enhances; it does not inform alone.
- `prefers-reduced-motion: reduce` → disable idle animations and transition effects; keep only state-change cues, and shorten them to under 400ms.
- The minimize and drag controls have keyboard equivalents:
  - `Esc` while modal focused → minimize to pill
  - Arrow keys while avatar focused → nudge position by 10px
  - `Enter` / `Space` on minimized form → restore
- All interactive elements have ARIA labels: "Ask BPL assistant", "Minimize assistant", "Restore assistant", "Move assistant".

---

## 10. Acceptance checks

The avatar implementation is complete when:

1. All 14 states are individually triggerable from a dev-only debug panel (gate behind `NODE_ENV !== 'production'`).
2. The full happy-path flow (`idle` → `listening` → `thinking` → `retrieving` → `answering` → `success` → `idle`) plays correctly when a real `POST /v1/ask` returns a grounded answer with citation.
3. A PII-bearing input triggers `refusalPII` in under 500ms (matches TRD-NFR-3).
4. An out-of-corpus question triggers `refusalOutOfCorpus` → `routing` → `idle`.
5. The avatar is draggable to any viewport corner and stays inside bounds.
6. Minimize-to-pill and minimize-to-dock both work; idle animations are confirmed paused via DevTools performance trace.
7. Position and minimize state survive a page reload within the same session.
8. With `prefers-reduced-motion: reduce`, idle and ambient motion are disabled.
9. The avatar is not the sole signal for any state — text equivalents are present in the modal body (verify with screen reader).
10. Scene file is under 2 MB; 60 fps on the build team's reference hardware.

---

## 11. What this spec does *not* cover

- **Final visual design of the book character.** Color, proportions, eye style, and detail level are a design decision deferred per PRD v3. The placeholder color (`#185FA5`) and "friendly book" description are scaffolding, not a brand decision.
- **The Spline scene file itself.** Authored separately; this spec only contracts its API.
- **Voice or sound effects.** Out of pilot scope. The seam is open (add a `useAvatarSound` hook later) but no audio in v1.
- **Activation-phase changes.** When the modal moves from the demo environment to the BPL intranet (post-pilot), the avatar component itself does not change — only its host. Per TRD-AUTH-5, endpoint shapes are stable.

---

## 12. References

- **PRD v3** — Ask BPL Product Requirements, April 29, 2026.
- **TRD v0.3** — Ask BPL Technical Requirements, May 8, 2026. Specifically TRD-UI-1, UI-2, UI-3, UI-4, UI-6.
- **Wireframe** — `AskBPL_Wireframe.html`, screen 2 (avatar trigger + modal) and screen 3 (refusal states).
- **Existing component** — `avatar-modal-mockup.jsx` (current React mockup to be extended).
- **Spline React docs** — https://github.com/splinetool/react-spline
- **XState docs** — https://stately.ai/docs (for the state machine)
- **use-gesture** — https://use-gesture.netlify.app (for drag)

---

*Document owner: Vizion engineering (Denward Lee Aulder). Reviewed against PRD v3 and TRD v0.3. Open questions go to Selvon Smith (ssmith@bklynlibrary.org) only if they touch pilot scope — pure implementation details stay internal.*
