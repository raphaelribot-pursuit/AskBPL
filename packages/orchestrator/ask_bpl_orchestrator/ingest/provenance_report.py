"""Read-only report of the page and heading labels patch 0013 would store for given PDFs.

    askbpl-provenance-report "path/to/Policy.pdf" [more.pdf ...]

No database, no Pinecone, no embeddings, no API keys. It uses the real extractor and the real chunker, so run
it with the real tokenizer before re-ingesting. Use it to see what staff would be shown, and to spot a wrong
heading BEFORE it is stored. ``--stand-in-tokenizer`` swaps in a byte-level vocabulary (about 4 bytes per real
token) for machines that cannot download the tokenizer file; page and heading results hold, boundaries differ.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ask_bpl_orchestrator.config import get_settings
from ask_bpl_orchestrator.ingest.chunking import split_text_with_sections
from ask_bpl_orchestrator.ingest.loaders import load_bytes
from ask_bpl_orchestrator.ingest.provenance import find_headings, format_pages, heading_at, page_range


def _stand_in_encoder():
    import tiktoken

    return tiktoken.Encoding(
        name="stand-in-bytes",
        pat_str=r"(?s).",
        mergeable_ranks={bytes([i]): i for i in range(256)},
        special_tokens={},
    )


def report(path: Path, *, stand_in: bool) -> str:
    cfg = get_settings()
    text = load_bytes(path)
    stripped = text.strip()
    scale = 4 if stand_in else 1
    segments = split_text_with_sections(
        text,
        model_name=cfg.openai_embedding_model,
        chunk_size=cfg.chunk_size_tokens * scale,
        overlap=cfg.chunk_overlap_tokens * scale,
        encoder=_stand_in_encoder() if stand_in else None,
    )
    headings = find_headings(stripped)
    spans = getattr(text, "pages", None) or []
    lines = [f"=== {path.name}", f"pages with text: {len(spans)}   chunks: {len(segments)}   headings found: {len(headings)}"]
    labelled = with_page = 0
    for i, seg in enumerate(segments, start=1):
        ps, pe = page_range(spans, seg.start_char, seg.end_char)
        heading = seg.section_heading or heading_at(headings, seg.start_char if seg.start_char is not None else -1)
        labelled += bool(heading)
        with_page += ps is not None
        preview = " ".join(seg.text.split())[:60]
        lines.append(f"  #{i:<3} {format_pages(ps, pe) or '-':<9} {heading or '(no confident heading)':<44.44} | {preview}")
    lines.append(f"  -> {with_page}/{len(segments)} chunks have a page; {labelled}/{len(segments)} have a heading")
    lines.append("  headings: " + (" | ".join(h.text for h in headings) or "none"))
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Show the page and heading labels 0013 would store (read-only).")
    parser.add_argument("pdfs", nargs="+", type=Path)
    parser.add_argument("--stand-in-tokenizer", action="store_true", help="byte-level stand-in when the tokenizer cannot be downloaded")
    args = parser.parse_args(argv)
    for pdf in args.pdfs:
        if not pdf.is_file():
            print(f"not a file: {pdf}", file=sys.stderr)
            return 2
        print(report(pdf, stand_in=args.stand_in_tokenizer))
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
