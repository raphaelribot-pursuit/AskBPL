# Spline scene contract — `askbpl-book.splinecode`

The runtime expects an exported Spline file living at
**`packages/web-demo/public/scenes/askbpl-book.splinecode`** (served from
`/scenes/askbpl-book.splinecode`). The scene is consumed via
`@splinetool/react-spline` and driven by the avatar state machine.

## Required scene objects (spec §8)

| Object | Notes |
|--------|-------|
| `Book` | Root; parent of the cover, pages, eyes, mouth. |
| `Cover_Front`, `Cover_Back`, `Spine` | Hardcover surfaces. |
| `Pages` | Animated group for riffle / flip. |
| `Eye_L`, `Eye_R` | Drivable for blink, widen, glance. |
| `Mouth` | Drivable for smile / neutral / refusal / confused. |

## Required scene States

The Spline scene must declare a **String variable** named `avatarState`. The
runtime sets it to one of the following names; each one should be wired to
a Spline State (or events) producing the behavior in spec §4:

```
Idle, Listening, Thinking, Retrieving, Answering,
Success, RefusalSoft, RefusalAlert, Routing,
Greeting, Goodbye, Error, Dragging, Minimized
```

`Minimized` should be a static / paused frame — no idle animation. The
runtime additionally calls `Application.stop()` while minimized; `play()`
on restore.

## Performance budget

- Compiled scene under **2 MB**.
- 60 fps on a mid-range laptop; 30 fps minimum on mobile.
- No looping particle systems while in `Minimized`.

## Placeholder behavior

If the asset is missing, `AvatarScene.tsx` renders an SVG book fallback so
CI and local dev never block on art delivery. The fallback honors
`prefers-reduced-motion` and the minimize state.
