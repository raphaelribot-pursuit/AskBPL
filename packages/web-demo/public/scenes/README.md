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
