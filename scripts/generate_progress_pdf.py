#!/usr/bin/env python3
"""Generate a one-page Ask BPL pilot progress summary PDF."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from fpdf import FPDF

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "AskBPL_Progress_Summary.pdf"

_ASCII = str.maketrans(
    {
        "\u2014": "-",
        "\u2013": "-",
        "\u2022": "-",
        "\u2192": "->",
        "\u00a7": "Sec.",
    }
)


def _t(text: str) -> str:
    return text.translate(_ASCII)


class SummaryPDF(FPDF):
    def header(self) -> None:
        self.set_font("Helvetica", "B", 13)
        self.set_text_color(26, 26, 46)
        self.cell(0, 7, "Ask BPL Pilot - Completion Summary", new_x="LMARGIN", new_y="NEXT")
        self.set_font("Helvetica", "", 7.5)
        self.set_text_color(100, 100, 120)
        self.cell(
            0,
            4,
            f"VizionScop3 LLC  |  Brooklyn Public Library  |  {date.today().isoformat()}",
            new_x="LMARGIN",
            new_y="NEXT",
        )
        self.ln(1)

    def section(self, title: str) -> None:
        self.set_font("Helvetica", "B", 8.5)
        self.set_text_color(0, 180, 212)
        self.cell(0, 4.5, title, new_x="LMARGIN", new_y="NEXT")
        self.set_font("Helvetica", "", 7)
        self.set_text_color(30, 30, 30)

    def bullets(self, items: list[str]) -> None:
        w = self.w - self.l_margin - self.r_margin
        for item in items:
            self.multi_cell(w, 2.9, f"- {_t(item)}")


def build() -> None:
    pdf = SummaryPDF(orientation="P", unit="mm", format="letter")
    pdf.set_auto_page_break(auto=False)
    pdf.set_margins(11, 11, 11)
    pdf.add_page()

    w = pdf.w - pdf.l_margin - pdf.r_margin
    pdf.set_font("Helvetica", "", 7.2)
    pdf.set_text_color(50, 50, 50)
    pdf.multi_cell(
        w,
        3.2,
        _t(
            "Internal AI policy Q&A pilot (PRD v3 / TRD). Monorepo: FastAPI orchestrator + Vite/React web demo. "
            "Closed-corpus RAG (Pinecone + Postgres), JWT tester auth, build-team admin APIs, scripted demo acceptance."
        ),
    )
    pdf.ln(1)

    pdf.section("Backend (packages/orchestrator)")
    pdf.bullets(
        [
            "FastAPI: /healthz, /readyz (Postgres SELECT 1), X-Request-ID on all responses",
            "POST /auth/sign-in (JWT, 8h TTL); bearer guard on /questions/ask and /feedback",
            "RAG pipeline: Pinecone top-K retrieval, generation, citation verifier, routing decisions",
            "PII regex gate (400 error_pii) before embeddings; supersede on re-ingest (PRD Sec.8.5)",
            "CLIs: askbpl-ingest, askbpl-seed, askbpl-latency-smoke; Alembic migrations",
            "Admin: GET /admin/summary and /admin/documents (HTTP basic auth)",
            "Tests: PII gate, API smoke, integration tests (GitHub Actions + Postgres service)",
        ]
    )

    pdf.section("Frontend (packages/web-demo)")
    pdf.bullets(
        [
            "React Router SPA: /login, host (/ and /staff/policies), /internal/console/* panels",
            "In-memory session token (no localStorage); AuthProvider + 401 redirects to login",
            "AskPilot modal: FAB, drag/minimize, transcript rows (answer, refusal, PII, routing)",
            "Citations, sample prompts, thumbs feedback wired to orchestrator APIs",
            "3D avatar (AvatarScene) with scene assets; Neubrutomorphism design tokens",
            "Console sections: Corpus, Overview, Routing, Sessions, Feedback, Settings",
            "Modal vs console import boundary documented (architecture/shared-vs-console.md)",
        ]
    )

    pdf.section("DevOps, documentation, and demo readiness")
    pdf.bullets(
        [
            "GitHub Actions CI: Python 3.11 (ruff, migrate, seed, pytest) + Node 22 (lint, build)",
            "Docker Compose Postgres; .env.example for orchestrator and web-demo",
            "Docs: demo_acceptance.md, PINECONE_CORPUS_INGEST, requirements-matrix, wireframe parity",
            "Seeded demo login: pilot-demo@bklynlibrary.org / DEMO2026",
            "Acceptance checklist: PII refusal, closed-corpus refusal, citations, admin readout",
        ]
    )

    pdf.section("Known gaps (still in pilot scope)")
    pdf.bullets(
        [
            "Console UI is panel stubs / JSON readout vs wireframe stat grid and document table",
            "Ingest and routing edits via CLI/seed, not in-SPA buttons; citations below bubble not inset",
            "Production hosting, Entra/SharePoint embed, and full production security hardening deferred",
        ]
    )

    pdf.set_y(-14)
    pdf.set_font("Helvetica", "I", 6.5)
    pdf.set_text_color(120, 120, 130)
    pdf.cell(
        0,
        3,
        _t(
            "Repo: AskBPL on main - commits: initial import -> orchestrator RAG/Pinecone -> AskPilot shell/avatar -> layout polish + routing refactor (in progress)"
        ),
        align="C",
    )

    OUT.parent.mkdir(parents=True, exist_ok=True)
    pdf.output(str(OUT))
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    build()
