"""Human validation of scanned / OCR text before it may be indexed (PRD ING-3, ING-11, GATE-04).

Why this exists
---------------
A scanned PDF has no trustworthy text layer. Machine OCR is good but not proof: one wrong word in a
policy ("shall" for "shall not") becomes a wrong answer with a verified-looking citation. So a person
compares every page image with its text, and only that person's signed-off text can be indexed.

Flow (no database, no network, nothing here can make a document answerable by itself)
  prepare   OCR every page, write a review packet: page images, editable page text, flags, review.yaml
  (person)  fix the text, set a verdict per page, fill in name/date, tick the confirmation
  finalize  check the review is complete and consistent, write validated_text.md + validation_record.json
  verify    re-check a record against the PDF and its text (ingest does this too, fail-closed)

The record binds the PDF (sha256), the exact validated text (sha256), the reviewer and the date. If the
PDF or the text changes afterwards, verification fails and the document cannot be ingested as validated.
Activation is a separate, deliberate step (see docs/EXTRACTION_REVIEW.md).
"""

from __future__ import annotations

import argparse
import difflib
import hashlib
import html
import json
import re
import sys
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import yaml

SCHEMA_VERSION = 1
VERDICT_VERIFIED = "verified"
VERDICT_EXCLUDED = "excluded"
VERDICT_PENDING = "pending"
LOW_CONFIDENCE = 70.0   # mean tesseract word confidence (0-100) below this is flagged
THIN_WORDS = 60         # a page with fewer words than this is flagged (blank, stamp-only or partly lost)
MIN_EXCLUDE_NOTE = 10   # an excluded page needs a real reason

SOURCE_FILE = "source.json"
REVIEW_FILE = "review.yaml"
RECORD_FILE = "validation_record.json"
TEXT_FILE = "validated_text.md"
_SOURCE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{1,31}$")
_PAGE_HEADER = re.compile(r"^## Page (\d+)\s*$", re.MULTILINE)


class ExtractionValidationError(ValueError):
    """The review is incomplete or inconsistent, or a record does not match its files. Fail closed."""


@dataclass(frozen=True)
class PageReading:
    """What the machine saw on one page. `image_png` is optional so tests need no imaging stack."""

    page: int
    textlayer: str
    ocr_text: str
    confidence: Optional[float]
    image_png: Optional[bytes] = None


@dataclass(frozen=True)
class ValidatedExtraction:
    """A record that passed verification: safe to ingest in place of automatic extraction."""

    text: str
    source_id: str
    reviewer: str
    reviewed_on: date
    record_sha256: str
    pdf_sha256: str
    page_count: int


# ----------------------------------------------------------------------------- helpers
def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def _norm(text: str) -> str:
    """Normalise line endings and trailing space so hashes do not depend on editor habits."""
    return "\n".join(line.rstrip() for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n")).strip()


def _page_name(n: int, suffix: str) -> str:
    return f"page-{n:02d}{suffix}"


def _parse_day(value: Any, what: str) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return datetime.strptime(str(value).strip(), "%Y-%m-%d").date()
    except ValueError as exc:
        raise ExtractionValidationError(f"{what} must be a date written YYYY-MM-DD, got {value!r}") from exc


# ----------------------------------------------------------------------------- reading pages
def read_pages_with_ocr(pdf_path: Path, dpi: int) -> List[PageReading]:
    """OCR every page (not only thin ones) and keep the text layer for comparison."""
    try:
        import pytesseract
        from pdf2image import convert_from_path
        from pypdf import PdfReader
    except ImportError as exc:  # pragma: no cover - environment dependent
        raise ExtractionValidationError(
            f"OCR tools are missing ({exc}). Install: pip install -e '.[ocr]' plus the system packages "
            "tesseract and poppler (macOS: brew install tesseract poppler)."
        ) from exc
    import io

    reader = PdfReader(str(pdf_path))
    out: List[PageReading] = []
    for index, page in enumerate(reader.pages, start=1):
        layer = (page.extract_text() or "").replace("", "").strip()
        images = convert_from_path(str(pdf_path), first_page=index, last_page=index, dpi=dpi)
        if not images:
            out.append(PageReading(index, layer, "", None, None))
            continue
        image = images[0]
        text = (pytesseract.image_to_string(image) or "").replace("", "").strip()
        data = pytesseract.image_to_data(image, output_type=pytesseract.Output.DICT)
        confs = [float(c) for c, w in zip(data.get("conf", []), data.get("text", [])) if str(w).strip() and float(c) >= 0]
        mean = round(sum(confs) / len(confs), 1) if confs else None
        preview = image.copy()
        preview.thumbnail((1100, 1500))
        buf = io.BytesIO()
        preview.save(buf, format="PNG")
        out.append(PageReading(index, layer, text, mean, buf.getvalue()))
    return out


def _flags(reading: PageReading, working: str) -> List[str]:
    flags: List[str] = []
    words = len(working.split())
    if not working.strip():
        flags.append("empty")
    elif words < THIN_WORDS:
        flags.append("thin")
    if reading.confidence is not None and reading.confidence < LOW_CONFIDENCE:
        flags.append("low_confidence")
    if reading.confidence is None and reading.ocr_text == "":
        flags.append("no_ocr")
    return flags


# ----------------------------------------------------------------------------- prepare
_REVIEW_TEMPLATE = """\
# Extraction review for {source_id}  ({pdf_name})
#
# 1. Open report.html (or each pages/page-NN.png next to pages/page-NN.txt) and compare image and text.
# 2. Correct any wrong word, number or missing line directly in pages/page-NN.txt. Never edit *.ocr.txt.
# 3. For each page below set verdict to  verified  (text is a faithful copy of the page)
#    or  excluded  (page is blank / unreadable / not policy text; give the reason in note).
# 4. Fill in reviewer, reviewed_on (YYYY-MM-DD) and set confirmed: true.
# 5. Run:  askbpl-extraction-review finalize --dir <this folder>
#
# Nothing here makes the policy answerable. Activation is a separate step (docs/EXTRACTION_REVIEW.md).

source_id: {source_id}
pdf_sha256: {pdf_sha256}

reviewer: ""          # your full name
reviewed_on: ""       # YYYY-MM-DD
confirmed: false      # true = "I compared every page image with its text; the text is faithful"

pages:
{pages}
"""


def prepare_review(
    pdf_path: Path,
    source_id: str,
    out_dir: Path,
    *,
    dpi: Optional[int] = None,
    force: bool = False,
    reader: Optional[Callable[[Path, int], List[PageReading]]] = None,
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Create the review packet. Refuses to overwrite review work already done unless `force`."""
    if not _SOURCE_ID.match(source_id or ""):
        raise ExtractionValidationError(f"source id {source_id!r} must look like SRC-13")
    pdf_path = Path(pdf_path)
    if not pdf_path.is_file():
        raise ExtractionValidationError(f"PDF not found: {pdf_path}")
    out_dir = Path(out_dir)
    if out_dir.exists() and any(out_dir.iterdir()) and not force:
        raise ExtractionValidationError(
            f"{out_dir} already exists. Review work in it would be lost; use --force only if you mean to start over."
        )
    if dpi is None:
        from ask_bpl_orchestrator.config import get_settings

        dpi = get_settings().ocr_dpi
    readings = (reader or read_pages_with_ocr)(pdf_path, dpi)
    if not readings:
        raise ExtractionValidationError("the PDF has no pages")

    created = (now or datetime.now(timezone.utc)).replace(microsecond=0)
    (out_dir / "pages").mkdir(parents=True, exist_ok=True)
    page_rows: List[Dict[str, Any]] = []
    html_blocks: List[str] = []
    yaml_pages: List[str] = []
    for r in readings:
        working_source = "ocr" if r.ocr_text.strip() else "text_layer"
        working = r.ocr_text if r.ocr_text.strip() else r.textlayer
        (out_dir / "pages" / _page_name(r.page, ".ocr.txt")).write_text(_norm(working) + "\n", encoding="utf-8")
        (out_dir / "pages" / _page_name(r.page, ".txt")).write_text(_norm(working) + "\n", encoding="utf-8")
        (out_dir / "pages" / _page_name(r.page, ".textlayer.txt")).write_text(_norm(r.textlayer) + "\n", encoding="utf-8")
        if r.image_png:
            (out_dir / "pages" / _page_name(r.page, ".png")).write_bytes(r.image_png)
        flags = _flags(r, working)
        page_rows.append({
            "page": r.page, "working_text_from": working_source, "mean_confidence": r.confidence,
            "words": len(working.split()), "textlayer_chars": len(r.textlayer), "flags": flags,
            "machine_text_sha256": sha256_bytes(_norm(working).encode("utf-8")),
        })
        yaml_pages.append(
            f"  - page: {r.page}\n    verdict: {VERDICT_PENDING}   # verified | excluded\n    note: \"\"      # required when excluded"
            + (f"\n    # flags: {', '.join(flags)}" if flags else "")
        )
        img = (f'<img src="pages/{_page_name(r.page, ".png")}" alt="Scan of page {r.page}">'
               if r.image_png else "<p><em>No image rendered.</em></p>")
        html_blocks.append(
            f'<section><h2>Page {r.page}'
            + (f' <span class="flag">{html.escape(", ".join(flags))}</span>' if flags else "")
            + f'</h2><p class="meta">words: {len(working.split())} &middot; OCR confidence: '
            f'{"n/a" if r.confidence is None else r.confidence} &middot; edit pages/{_page_name(r.page, ".txt")}</p>'
            f'<div class="pair">{img}<pre>{html.escape(_norm(working))}</pre></div></section>'
        )

    pdf_sha = sha256_file(pdf_path)
    source = {
        "schema_version": SCHEMA_VERSION, "source_id": source_id, "pdf_file_name": pdf_path.name,
        "pdf_sha256": pdf_sha, "created_at_utc": created.isoformat(), "ocr_dpi": dpi,
        "low_confidence_below": LOW_CONFIDENCE, "thin_below_words": THIN_WORDS, "pages": page_rows,
    }
    try:  # informational only
        import pytesseract

        source["tesseract_version"] = str(pytesseract.get_tesseract_version())
    except Exception:  # noqa: BLE001
        source["tesseract_version"] = None
    (out_dir / SOURCE_FILE).write_text(json.dumps(source, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (out_dir / REVIEW_FILE).write_text(
        _REVIEW_TEMPLATE.format(source_id=source_id, pdf_name=pdf_path.name, pdf_sha256=pdf_sha, pages="\n".join(yaml_pages)),
        encoding="utf-8",
    )
    (out_dir / "report.html").write_text(
        "<!doctype html><meta charset=utf-8><title>Extraction review " + html.escape(source_id) + "</title>"
        "<style>body{font:15px/1.4 system-ui;margin:1.5rem;max-width:1500px}.pair{display:grid;grid-template-columns:1fr 1fr;gap:1rem}"
        "img{max-width:100%;border:1px solid #bbb}pre{white-space:pre-wrap;background:#f6f6f6;padding:.75rem;margin:0}"
        ".flag{background:#fde68a;padding:0 .4rem;border-radius:3px;font-size:.8em}.meta{color:#555}"
        "section{margin-bottom:2rem}</style><h1>Extraction review: " + html.escape(source_id) + " ("
        + html.escape(pdf_path.name) + ")</h1><p>Compare each scan (left) with its text (right). Correct the text in "
        "<code>pages/page-NN.txt</code>, then fill in <code>review.yaml</code>. This page shows the machine text as first read.</p>"
        + "".join(html_blocks), encoding="utf-8",
    )
    flagged = [p["page"] for p in page_rows if p["flags"]]
    return {"pages": len(readings), "flagged_pages": flagged, "dir": str(out_dir), "pdf_sha256": pdf_sha}


# ----------------------------------------------------------------------------- finalize
def finalize_review(review_dir: Path, *, today: Optional[date] = None) -> Path:
    """Validate the completed review and write the hash-bound record. Writes nothing on failure."""
    review_dir = Path(review_dir)
    try:
        source = json.loads((review_dir / SOURCE_FILE).read_text(encoding="utf-8"))
        review = yaml.safe_load((review_dir / REVIEW_FILE).read_text(encoding="utf-8")) or {}
    except FileNotFoundError as exc:
        raise ExtractionValidationError(f"{exc.filename} not found: run prepare first") from exc
    errors: List[str] = []

    if review.get("source_id") != source["source_id"]:
        errors.append("review.yaml source_id does not match source.json")
    if review.get("pdf_sha256") != source["pdf_sha256"]:
        errors.append("review.yaml pdf_sha256 does not match source.json (was the file edited?)")
    reviewer = str(review.get("reviewer") or "").strip()
    if len(reviewer) < 3 or not re.search(r"[A-Za-z]", reviewer):
        errors.append("reviewer: enter the full name of the person who did the review")
    reviewed_on: Optional[date] = None
    try:
        reviewed_on = _parse_day(review.get("reviewed_on"), "reviewed_on")
        created_day = datetime.fromisoformat(source["created_at_utc"]).date()
        now_day = today or datetime.now(timezone.utc).date()
        if reviewed_on < created_day - timedelta(days=1):
            errors.append("reviewed_on is before the review packet was created")
        if reviewed_on > now_day + timedelta(days=1):
            errors.append("reviewed_on is in the future")
    except ExtractionValidationError as exc:
        errors.append(str(exc))
    if review.get("confirmed") is not True:
        errors.append("confirmed must be true once every page has been compared with its text")

    expected = {p["page"] for p in source["pages"]}
    listed = review.get("pages") or []
    seen = [p.get("page") for p in listed if isinstance(p, dict)]
    if sorted(map(str, seen)) != sorted(map(str, expected)):
        errors.append(f"review.yaml must list exactly pages {sorted(expected)} once each")

    pages_out: List[Dict[str, Any]] = []
    text_parts: List[str] = []
    machine = {p["page"]: p for p in source["pages"]}
    for entry in sorted((p for p in listed if isinstance(p, dict) and p.get("page") in expected), key=lambda p: p["page"]):
        n = entry["page"]
        verdict = str(entry.get("verdict") or "").strip().lower()
        note = str(entry.get("note") or "").strip()
        if verdict not in (VERDICT_VERIFIED, VERDICT_EXCLUDED):
            errors.append(f"page {n}: verdict must be verified or excluded (found {verdict or 'empty'!r})")
            continue
        if verdict == VERDICT_EXCLUDED:
            if len(note) < MIN_EXCLUDE_NOTE:
                errors.append(f"page {n}: an excluded page needs a note giving the reason")
            pages_out.append({"page": n, "verdict": verdict, "note": note, "text_sha256": None, "edited": None})
            continue
        path = review_dir / "pages" / _page_name(n, ".txt")
        if not path.is_file():
            errors.append(f"page {n}: {path.name} is missing")
            continue
        text = _norm(path.read_text(encoding="utf-8"))
        if not text:
            errors.append(f"page {n}: marked verified but its text is empty; mark it excluded with a reason")
            continue
        edited = sha256_bytes(text.encode("utf-8")) != machine[n]["machine_text_sha256"]
        entry_out: Dict[str, Any] = {
            "page": n, "verdict": verdict, "note": note, "edited": edited,
            "text_sha256": sha256_bytes(text.encode("utf-8")),
        }
        if edited:
            original = _norm((review_dir / "pages" / _page_name(n, ".ocr.txt")).read_text(encoding="utf-8"))
            entry_out["similarity_to_machine_text"] = round(difflib.SequenceMatcher(None, original, text).ratio(), 3)
        pages_out.append(entry_out)
        text_parts.append(f"## Page {n}\n\n{text}\n")

    if not text_parts and not errors:
        errors.append("every page is excluded: there is no validated text to index")
    if errors:
        raise ExtractionValidationError("review is not complete:\n  - " + "\n  - ".join(errors))

    validated_text = "\n".join(text_parts)
    (review_dir / TEXT_FILE).write_text(validated_text, encoding="utf-8")
    record = {
        "schema_version": SCHEMA_VERSION,
        "source_id": source["source_id"],
        "pdf_file_name": source["pdf_file_name"],
        "pdf_sha256": source["pdf_sha256"],
        "reviewer": reviewer,
        "reviewed_on": reviewed_on.isoformat() if reviewed_on else None,
        "finalized_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "validated_text_file": TEXT_FILE,
        "validated_text_sha256": sha256_bytes(validated_text.encode("utf-8")),
        "pages": pages_out,
        "excluded_pages": [p["page"] for p in pages_out if p["verdict"] == VERDICT_EXCLUDED],
        "edited_pages": [p["page"] for p in pages_out if p.get("edited")],
        "ocr_dpi": source.get("ocr_dpi"),
        "tesseract_version": source.get("tesseract_version"),
    }
    path = review_dir / RECORD_FILE
    path.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


# ----------------------------------------------------------------------------- verify
def verify_record(record_path: Path, pdf_path: Path) -> ValidatedExtraction:
    """Re-check a record against the PDF and its text. Raises ExtractionValidationError on any mismatch."""
    record_path, pdf_path = Path(record_path), Path(pdf_path)
    if not record_path.is_file():
        raise ExtractionValidationError(f"validation record not found: {record_path}")
    if not pdf_path.is_file():
        raise ExtractionValidationError(f"PDF not found: {pdf_path}")
    raw = record_path.read_bytes()
    try:
        rec = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ExtractionValidationError(f"validation record is not valid JSON: {exc}") from exc
    if rec.get("schema_version") != SCHEMA_VERSION:
        raise ExtractionValidationError(f"unsupported record schema_version {rec.get('schema_version')!r}")
    for key in ("source_id", "pdf_sha256", "reviewer", "reviewed_on", "validated_text_file", "validated_text_sha256", "pages"):
        if not rec.get(key):
            raise ExtractionValidationError(f"validation record is missing {key}")
    reviewer = str(rec["reviewer"]).strip()
    if len(reviewer) < 3:
        raise ExtractionValidationError("validation record has no reviewer name")
    reviewed_on = _parse_day(rec["reviewed_on"], "reviewed_on")
    if sha256_file(pdf_path) != rec["pdf_sha256"]:
        raise ExtractionValidationError(
            f"{pdf_path.name} is not the file that was reviewed (sha256 differs). Review the new file again."
        )
    text_path = record_path.parent / Path(str(rec["validated_text_file"])).name  # no path tricks
    if not text_path.is_file():
        raise ExtractionValidationError(f"validated text file not found next to the record: {text_path.name}")
    text_bytes = text_path.read_bytes()
    if sha256_bytes(text_bytes) != rec["validated_text_sha256"]:
        raise ExtractionValidationError("validated text was changed after the review was finalized")
    pages = rec["pages"]
    verified = [p["page"] for p in pages if p.get("verdict") == VERDICT_VERIFIED]
    if not verified or any(p.get("verdict") not in (VERDICT_VERIFIED, VERDICT_EXCLUDED) for p in pages):
        raise ExtractionValidationError("validation record has no verified pages or an invalid verdict")
    text = text_bytes.decode("utf-8")
    if [int(n) for n in _PAGE_HEADER.findall(text)] != verified:
        raise ExtractionValidationError("validated text pages do not match the verified pages in the record")
    return ValidatedExtraction(
        text=text, source_id=rec["source_id"], reviewer=reviewer, reviewed_on=reviewed_on,
        record_sha256=sha256_bytes(raw), pdf_sha256=rec["pdf_sha256"], page_count=len(pages),
    )


# ----------------------------------------------------------------------------- CLI
def main(argv: Optional[List[str]] = None) -> None:
    parser = argparse.ArgumentParser(
        prog="askbpl-extraction-review",
        description="Validate OCR text of a scanned policy before it can be indexed (docs/EXTRACTION_REVIEW.md)",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("prepare", help="OCR every page and write the review packet")
    p.add_argument("--pdf", required=True)
    p.add_argument("--source-id", required=True, help="Inventory source id, e.g. SRC-13")
    p.add_argument("--out", default=None, help="Packet folder (default: extraction_reviews/<source-id>)")
    p.add_argument("--dpi", type=int, default=None)
    p.add_argument("--force", action="store_true", help="Overwrite an existing packet (discards review work)")
    f = sub.add_parser("finalize", help="Check the completed review and write validation_record.json")
    f.add_argument("--dir", required=True)
    v = sub.add_parser("verify", help="Check a validation record against the PDF and its text")
    v.add_argument("--record", required=True)
    v.add_argument("--pdf", required=True)
    args = parser.parse_args(argv)
    try:
        if args.cmd == "prepare":
            out = Path(args.out) if args.out else Path("extraction_reviews") / args.source_id
            info = prepare_review(Path(args.pdf), args.source_id, out, dpi=args.dpi, force=args.force)
            print(f"packet written: {info['dir']}")  # noqa: T201
            print(f"pages: {info['pages']}; flagged for extra care: {info['flagged_pages'] or 'none'}")  # noqa: T201
            print("next: open report.html, correct pages/*.txt, complete review.yaml, then run finalize")  # noqa: T201
        elif args.cmd == "finalize":
            path = finalize_review(Path(args.dir))
            print(f"validated: {path}")  # noqa: T201
            print("This does not activate anything. See docs/EXTRACTION_REVIEW.md, step 'Activate'.")  # noqa: T201
        else:
            ve = verify_record(Path(args.record), Path(args.pdf))
            print(f"OK: {ve.source_id} reviewed by {ve.reviewer} on {ve.reviewed_on}; {ve.page_count} pages")  # noqa: T201
    except ExtractionValidationError as exc:
        print(f"error: {exc}", file=sys.stderr)  # noqa: T201
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
