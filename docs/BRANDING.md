# BPL branding in Ask BPL

Decision D-08 (BPL branding assets). UX specification: "use only an authentic BPL-supplied/approved asset and follow any
provided brand standards"; "all authentic BPL logos, colors and routing destinations must have provenance/approval
recorded".

## Provenance

| | |
|---|---|
| What | BPL logo pack: the "Bklyn Public Library" logo in BPL Blue, black and white (RGB and CMYK PNG at 504 and 2100 px wide, vector EPS), plus the two-page guide "Brooklyn Public Library / Logo Usage" |
| Supplied by | Selvon Smith (BPL), via Lawrence Carrillo |
| Received | 2026-10-31 |
| Questions about the guide | BPL Art & Design Department (contact through Selvon; the guide names two staff members, so it is not stored in this repository) |

**In the repository:** only the file the product uses, `packages/web-demo/src/assets/brand/BklynPublicLibrary_blue_RGB_hires.png`
(2100 x 769, SHA-256 `5e17a696056fa72b041d8dcca72337a8949f3a22a1c9db73f8afb031181e6ecc`, byte-identical to the supplied file).
Keep the full pack with the team's handoff files, not in git.

## The rules (from the guide) and how the widget follows them

| Rule | In Ask BPL |
|---|---|
| Use the logo in BPL Blue or black; white only knocked out of a solid colour or a simple image | BPL Blue logo on a white header |
| BPL Blue: PMS 7455 C, CMYK 85/70/0/0, RGB 60/93/170 | `--bpl-blue: #3c5daa`. The supplied RGB PNG samples at `#4060AF`; the image is used unchanged and the token follows the guide |
| Never smaller than 1.25 inches wide | `--bpl-logo-width: 120px` (1.25 in at 96 CSS px per inch) |
| Clearance on all sides of at least the height of the "n" | The "n" is 0.43 of the logo's height (measured on the artwork): 19 px at 120 px wide. `--bpl-logo-clearance: 20px`; measured in Chrome: 20 / 20 / 21 px and 20 px to the title |
| Do not change the colour, stretch or distort, angle, separate or resize parts, put it in a shape, use "Bklyn" alone, or remake it | The supplied PNG is used as is with `height: auto`. The round launcher button keeps the book icon rather than the logo |
| Do not use the colour logo on a colour background | The header behind the logo is white (`#ffffff`) |

**Colour and contrast** (WCAG 2.1 AA needs 4.5:1 for normal text): white on BPL Blue 6.29:1 (the SharePoint blue it
replaces in the widget was 4.53:1); BPL Blue on white 6.29:1; BPL Blue and `--bpl-blue-dark` on `--bpl-blue-soft` both above 4.5:1.

## Scope

- **Branded:** the Ask BPL widget: launcher button, modal, welcome overlay, document viewer
  (`packages/web-demo/src/theme/bpl-brand.css`, scoped to `.pilot-fab`, `.pilot-modal`, `.pilot-welcome`, `.doc-viewer`).
- **Not branded, on purpose:** the host page. It reproduces Microsoft SharePoint, BPL's intranet, where the widget
  would live, so it keeps SharePoint's own palette. Its green "BPL" site tile is a SharePoint-style text placeholder,
  not a logo.

## Checks

`packages/web-demo/src/test/brand.test.tsx` (6 tests): BPL Blue value, contrast of every brand text pairing, minimum
logo width and clearance, aspect ratio kept, white header, logo bytes unchanged, host palette untouched, logo shown with
the text alternative "Brooklyn Public Library". Nine deliberate breakages were each caught. jsdom does not apply CSS,
so the layout was also measured in headless Chrome.

## Not settled here

- BPL has not reviewed the result. Show a screenshot to Selvon before any demo.
- The black and white logos and the CMYK and vector files are not used yet (print or dark backgrounds would need them).
