# Avatar scene drop point

Place the exported Spline file here:

```
packages/web-demo/public/scenes/askbpl-book.splinecode
```

It is served at the URL `/scenes/askbpl-book.splinecode` and consumed by
`packages/web-demo/src/avatar/AvatarScene.tsx`.

The full authoring contract — required objects, the `avatarState` String
variable, the 14 named States, and performance budget — lives next to the
React code at:

```
packages/web-demo/src/avatar/scenes/README.md
```

If this folder is empty (or the file fails to load) the avatar falls back to
an SVG book so CI and local development continue to work without the asset.

**Spline / WebGL:** even with a valid file, mounting `@splinetool/react-spline` can
blank the entire browser tab on some GPUs. The demo does **not** load Spline unless you set
`VITE_ENABLE_SPLINE=true` in `.env.local` (see root `.env.example`). Use `VITE_LITE_DEMO=true`
instead if you want the toolbar emoji with zero 3D code.