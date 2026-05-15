# Wireframe v3 ↔ pilot code parity

Source: **Ask BPL — Clickable Wireframe (v3)** (static HTML handoff: flow strip *Login → Ask & grounded answer → Refusal → Build-team console*). Aligns with PRD v3 / TRD IDs noted in that document’s annotations.

| Screen | Wireframe intent | Code / package | Parity notes |
|--------|------------------|----------------|--------------|
| **1 — Login & attribution** | Email, tester access code, attributed vs anonymous, sign-in | `AskPilotShell` `ShellBody` sign-in form (`packages/web-demo/src/AskPilotShell.tsx`) + `POST /auth/sign-in` | **Parity**: JWT session, attribution radios, copy differs slightly (wireframe uses friendlier labels). |
| **2 — Grounded answer** | FAB → modal; user bubble; bot bubble with **citation card inside** same bubble; footer composer + Send | Same file: FAB, modal toolbar (drag/minimize/close), history + `AssistantTurn`, composer | **Partial**: Citations are a **separate pane** below the answer with chips (links to `DOCUMENTS_PUBLIC_BASE_URL`), not an inset card inside the bubble. Optional post-pilot CSS/layout to match wireframe. Wireframe omits **sample prompt card** and **feedback thumbs** — present in code (TRD feedback). |
| **3 — Refusal & PII** | PII banner under user message; separate refusal bubble + route card | `AssistantTurn` error / `error_pii` / refusal branches + `RoutingDeck` | **Close**: PII shown on assistant error path; routing cards use different visual tokens (wireframe warn colors vs brutal theme). |
| **4 — Build-team console** | Full admin shell: sidebar, stats, document table, re-ingest / edit routing | `App.tsx` **Build-team readout** tab + `GET /admin/summary` and `GET /admin/documents` | **Partial**: Readout is JSON panes, not the wireframe’s **stat grid + status table UI**. Ingest/routing actions are **CLI / seed** (see `docs/PINECONE_CORPUS_INGEST.md`), not buttons in the SPA. |

## Hotspot → TRD

Use the wireframe’s annotation TRD IDs (e.g. TRD-GEN-3, TRD-UI-1) as the checklist when changing UI or retrieval; `docs/requirements-matrix.md` maps many of these to modules.

## Canonical HTML

If you version the clickable HTML in git, save it as:

`docs/pilot/AskBPL_wireframe_v3.html`

and link it from the root `README.md` under Documentation.
