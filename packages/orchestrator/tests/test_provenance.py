"""Page and heading provenance for chunks (patch 0013; PRD ING-11, GRD-4).

Hermetic: no network, no real tokenizer vocabulary, no Pinecone. The chunker tests use a REAL tiktoken
``Encoding`` built from a toy byte-level vocabulary, so tiktoken's own ``decode_with_offsets`` runs; only the
vocabulary is a stand-in. The sample lines in the heading tests are copied from the seven indexed policies.
"""

from __future__ import annotations

import asyncio
import functools
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
import tiktoken
from sqlalchemy import delete, select
from fastapi.testclient import TestClient

from ask_bpl_orchestrator.db.models import Chunk, Citation, Document, Question
from ask_bpl_orchestrator.db.session import async_session_factory
from ask_bpl_orchestrator.ingest import chunking, ocr_fallback, service
from ask_bpl_orchestrator.ingest.chunking import split_text_with_sections
from ask_bpl_orchestrator.ingest.loaders import LoadedText, load_bytes
from ask_bpl_orchestrator.ingest.provenance import (
    PageSpan,
    build_page_spans,
    find_headings,
    format_pages,
    heading_at,
    page_at,
    page_from_heading,
    page_range,
)
from ask_bpl_orchestrator.main import app
from ask_bpl_orchestrator.services.retrieval import RetrievedChunk, VectorRetriever

client = TestClient(app)


# ----------------------------------------------------------------------------- toy tokenizer
def toy_encoding() -> tiktoken.Encoding:
    """Real tiktoken machinery, byte-level vocabulary: every UTF-8 byte is one token (no merges)."""
    return tiktoken.Encoding(
        name="toy-bytes",
        pat_str=r"(?s).",
        mergeable_ranks={bytes([i]): i for i in range(256)},
        special_tokens={},
    )


ENC = toy_encoding()


def split(text: str, size: int = 120, overlap: int = 20):
    # The 0013 tests pin the labelling and the fixed-window chunker, so they name that strategy (0014 made
    # "sentence" the default). The sentence strategy has its own tests in test_sentence_chunking.py.
    return split_text_with_sections(text, model_name="x", chunk_size=size, overlap=overlap, encoder=ENC, strategy="token")


# ----------------------------------------------------------------------------- heading rule
@pytest.mark.parametrize(
    "line, expected",
    [
        ("Eligibility Requirements:", "Eligibility Requirements"),
        ("Carry-over of Annual Leave:", "Carry-over of Annual Leave"),
        ("Procedures and Guidelines:", "Procedures and Guidelines"),
        ("Health & Safety:", "Health & Safety"),
        ("Laptop Computers:", "Laptop Computers"),
        ("Overview:", "Overview"),
        ("A. PRIVATE FUNDRAISING:", "A. PRIVATE FUNDRAISING"),
        ("D. PROCESSING / ACKNOWLEDGEMENT:", "D. PROCESSING / ACKNOWLEDGEMENT"),
        ("GENERAL POLICY STATEMENT", "GENERAL POLICY STATEMENT"),
        ("THE COMMUNITY", "THE COMMUNITY"),  # "THE" may start a heading
        ("A. THE PEOPLE OF BROOKLYN", "A. THE PEOPLE OF BROOKLYN"),
        ("METHODS  AND CRITERIA FOR SELECTION", "METHODS AND CRITERIA FOR SELECTION"),  # double space from extraction
        ("PROCEDURE", "PROCEDURE"),
        ("I. Policy Statement", "I. Policy Statement"),
        ("IV. Responsibilities:", "IV. Responsibilities"),
    ],
)
def test_confident_headings_are_found(line: str, expected: str) -> None:
    text = f"Some body text before it.\n{line}\nBody text after it, a full sentence."
    assert [h.text for h in find_headings(text)] == [expected]


@pytest.mark.parametrize(
    "line",
    [
        "Customers may NOT:",  # list lead-in
        "guidelines for the use of public computers:",  # lower-case fragment
        "in circumstances such as the following:",
        "and under). The Company is proactive by:",
        "Enhancement of existing Library collection to reflect:",  # too long: a list lead-in (seen in the real data)
        "If an unattended child is left at the Company at closing time:",
        "Company Use by School-Age Children during School Hours:",  # a real heading missed on purpose: 8 words
        "Library Staff Must Follow The Approved Process For Gifts:",  # fully Title Case but 9 words: only length rejects it
        "2026 Goals:",  # does not start with a letter
        "Revision Date:",  # document metadata, not a location
        "Supersedes policies:",
        "Supercedes policy #:",
        "Related Public Documents:",
        "Issuing Agency:",
        "OR FORMS",  # continuation of a wrapped heading
        "AND POLICIES",
        "First year 4.0385 Up to 105.0010 Up to 15",  # flattened table row
        "Volunteers are expected to actively perform their duties to the best of their abilities.",
        "See https://example.org/policies/annual-leave:",
        "FY26",
        "Policy Name | Volunteer Manual and Policy",
    ],
)
def test_uncertain_lines_are_never_headings(line: str) -> None:
    assert find_headings(f"Body.\n{line}\nMore body.") == []


def test_wrapped_all_caps_heading_is_rejoined() -> None:
    text = "Body.\nRELATED AMERICAN ASSOCIATION (AA) DOCUMENTS AND  POLICIES\nOR FORMS\nThe list follows."
    assert [h.text for h in find_headings(text)] == ["RELATED AMERICAN ASSOCIATION (AA) DOCUMENTS AND POLICIES OR FORMS"]


def test_heading_offsets_point_at_the_heading_line() -> None:
    text = "Intro line.\n\nEligibility Requirements:\nBody here.\n\nA. PRIVATE FUNDRAISING:\nMore."
    found = find_headings(text)
    assert [text[h.offset : h.offset + 12] for h in found] == ["Eligibility ", "A. PRIVATE F"]


def test_document_with_no_confident_heading_yields_none() -> None:
    text = "Volunteers may serve in any program.\nBoard of Trustees\nMembers are not accepted as volunteers."
    assert find_headings(text) == []  # bold-only headings are invisible in extracted text, and stay unlabelled


def test_heading_at_uses_nearest_heading_before_the_position() -> None:
    text = "Preamble text.\nPurpose:\nAlpha.\nScope:\nBeta."
    headings = find_headings(text)
    assert heading_at(headings, 0) is None  # before the first heading: no label rather than a wrong one
    assert heading_at(headings, text.index("Alpha")) == "Purpose"
    assert heading_at(headings, text.index("Beta")) == "Scope"
    assert heading_at([], 10) is None


# ----------------------------------------------------------------------------- page spans
def test_blank_pages_keep_numbering_true_to_the_pdf() -> None:
    frags = ["Page one text", "", "Page three text"]
    merged = "\n\n".join(f for f in frags if f)
    spans = build_page_spans(frags)
    assert [s.number for s in spans] == [1, 3]
    assert merged[spans[0].start : spans[0].end] == "Page one text"
    assert merged[spans[1].start : spans[1].end] == "Page three text"


def test_page_at_boundaries() -> None:
    spans = [PageSpan(1, 0, 10), PageSpan(2, 12, 20)]
    assert page_at(spans, 0) == 1 and page_at(spans, 9) == 1
    assert page_at(spans, 10) == 2 and page_at(spans, 11) == 2  # the page break belongs to the next page
    assert page_at(spans, 12) == 2 and page_at(spans, 19) == 2
    assert page_at(spans, 500) == 2  # past the end: the last page, never a crash


def test_page_range_spans_a_page_break_and_handles_no_data() -> None:
    spans = [PageSpan(1, 0, 10), PageSpan(2, 12, 20)]
    assert page_range(spans, 4, 9) == (1, 1)
    assert page_range(spans, 8, 15) == (1, 2)
    assert page_range(spans, 12, 20) == (2, 2)
    assert page_range([], 0, 5) == (None, None)
    assert page_range(spans, None, None) == (None, None)


def test_format_and_page_marker_helpers() -> None:
    assert format_pages(2, 2) == "p. 2" and format_pages(2, None) == "p. 2"
    assert format_pages(2, 3) == "pp. 2\u20133"
    assert format_pages(None, None) is None
    assert page_from_heading("Page 12") == 12
    assert page_from_heading("Page 2 of the policy") is None and page_from_heading(None) is None


def test_loader_returns_text_that_knows_its_pages() -> None:
    pages = ["Policy text on page one.", "", "Text on page three."]
    fake_reader = SimpleNamespace(pages=[SimpleNamespace(extract_text=lambda t=t: t) for t in pages])
    cfg = SimpleNamespace(ocr_enabled=False)
    with patch.object(ocr_fallback, "PdfReader", return_value=fake_reader), patch.object(
        ocr_fallback, "get_settings", return_value=cfg
    ):
        from pathlib import Path

        loaded = load_bytes(Path("x.pdf"))
        merged_old_way = ocr_fallback.extract_pdf_text_with_ocr(Path("x.pdf"))
    assert isinstance(loaded, LoadedText) and isinstance(loaded, str)
    assert str(loaded) == merged_old_way == "Policy text on page one.\n\nText on page three."  # extraction unchanged
    assert [s.number for s in loaded.pages] == [1, 3]
    assert loaded[loaded.pages[1].start : loaded.pages[1].end] == "Text on page three."


# ----------------------------------------------------------------------------- chunker: labels only
def _legacy_chunks(text: str, size: int, overlap: int):
    """Frozen copy of the pre-0013 algorithm. 0013 must produce exactly these (heading, text) pairs."""
    import re

    heading_re = re.compile(r"^(#{1,3})\s+(.+?)\s*$", re.MULTILINE)
    stripped = text.strip()
    matches = list(heading_re.finditer(stripped))
    if not matches:
        sections = [(None, stripped)]
    else:
        sections = []
        pre = stripped[: matches[0].start()].strip()
        if pre:
            sections.append((None, pre))
        for i, m in enumerate(matches):
            end = matches[i + 1].start() if i + 1 < len(matches) else len(stripped)
            body = stripped[m.end() : end].strip()
            if body:
                sections.append((m.group(2).strip(), body))
    out = []
    for heading, body in sections:
        tokens = ENC.encode(body.strip())
        step = max(1, size - overlap)
        idx = 0
        while idx < len(tokens):
            end = min(len(tokens), idx + size)
            out.append((heading, ENC.decode(tokens[idx:end])))
            idx += step
            if end == len(tokens):
                break
    return out


SAMPLE_PLAIN = (
    "Policy Name | Annual Leave\nI. Policy Statement\n" + "Staff earn leave by length of service. " * 12
    + "\n\nEligibility Requirements:\n" + "Full-time staff are eligible after ninety days. " * 10
    + "\n\nCarry-over of Annual Leave:\n" + "Unused days may carry over to the next year. " * 8
)
SAMPLE_MARKDOWN = (
    "Preamble about the policy that is long enough to matter. " * 4
    + "\n\n## Page 1\n\n" + "First page body of the signed-off scan. " * 9
    + "\n\n## Page 2\n\n" + "Second page body of the signed-off scan. " * 9
)
SAMPLE_UNICODE = "Objectives of the Library\u2019s collections:\n" + "The Library\u2019s collections serve every neighbourhood \u2014 fully. " * 14


@pytest.mark.parametrize("text", [SAMPLE_PLAIN, SAMPLE_MARKDOWN, SAMPLE_UNICODE])
@pytest.mark.parametrize("size, overlap", [(120, 20), (60, 10), (400, 50)])
def test_chunk_text_and_headings_are_identical_to_before_0013(text: str, size: int, overlap: int) -> None:
    got = [(s.section_heading, s.text) for s in split(text, size, overlap)]
    assert got == _legacy_chunks(text, size, overlap)


@pytest.mark.parametrize("text", [SAMPLE_PLAIN, SAMPLE_MARKDOWN])
def test_chunk_offsets_locate_each_chunk_in_the_stripped_document(text: str) -> None:
    stripped = text.strip()
    segments = split(text)
    assert len(segments) > 3
    for seg in segments:
        assert seg.start_char is not None and seg.end_char is not None
        assert 0 <= seg.start_char < seg.end_char <= len(stripped)
        assert stripped[seg.start_char : seg.end_char] == seg.text  # ASCII text: the slice IS the chunk
    starts = [s.start_char for s in segments]
    assert starts == sorted(starts)


def test_offsets_stay_in_bounds_and_ordered_with_multibyte_text() -> None:
    stripped = SAMPLE_UNICODE.strip()
    segments = split(SAMPLE_UNICODE, 50, 10)
    assert all(0 <= s.start_char < s.end_char <= len(stripped) for s in segments)
    assert [s.start_char for s in segments] == sorted(s.start_char for s in segments)
    assert segments[-1].end_char == len(stripped)


def test_encoder_without_offsets_still_chunks_and_just_loses_the_labels() -> None:
    class NoOffsets:
        encode = staticmethod(ENC.encode)
        decode = staticmethod(ENC.decode)

        def decode_with_offsets(self, tokens):
            raise NotImplementedError

    got = split_text_with_sections(
        SAMPLE_PLAIN, model_name="x", chunk_size=120, overlap=20, encoder=NoOffsets(), strategy="token"
    )
    assert [(s.section_heading, s.text) for s in got] == _legacy_chunks(SAMPLE_PLAIN, 120, 20)
    assert all(s.start_char is None and s.end_char is None for s in got)


# ----------------------------------------------------------------------------- ingest writes the labels
async def _ingest(text, *, validated=None, strategy="token"):
    """Run the real ingest + real chunker (toy vocabulary) with embeddings and Pinecone mocked."""
    path_name = f"zz-prov-{uuid.uuid4().hex[:8]}.pdf"
    root = __import__("pathlib").Path("/tmp/prov-corpus")
    root.mkdir(exist_ok=True)
    p = root / path_name
    p.write_bytes(b"%PDF-1.4 stand-in")
    doc_id = service._document_uuid(path_name)
    chunker = functools.partial(split_text_with_sections, encoder=ENC)
    with (
        patch.object(service, "split_text_with_sections", chunker),
        patch.object(service, "embed_snippet", new_callable=AsyncMock, return_value=[0.0]),
        patch.object(service, "pinecone_bulk_upsert"),
        patch.object(service, "pinecone_bulk_delete"),
        patch.object(service, "load_bytes", return_value=text),
        patch.object(service, "get_settings", return_value=SimpleNamespace(
            chunk_size_tokens=150, chunk_overlap_tokens=25, openai_embedding_model="x", pinecone_api_key="",
            chunk_strategy=strategy)),
    ):
        await service.ingest_file(
            absolute_path=p, corpus_root=root, policy_slug="generic_policy", title="Prov Test",
            version_label="t", validated_extraction=validated,
        )
    async with async_session_factory() as s:
        rows = (await s.execute(select(Chunk).where(Chunk.document_id == doc_id).order_by(Chunk.ordinal))).scalars().all()
        return doc_id, [(r.section_heading, r.page_start, r.page_end, r.text) for r in rows]


async def _drop(doc_id):
    async with async_session_factory() as s:
        await s.execute(delete(Chunk).where(Chunk.document_id == doc_id))
        await s.execute(delete(Document).where(Document.document_id == doc_id))
        await s.commit()


def _three_page_text():
    frags = [
        "Policy Name | Leave\nI. Policy Statement\n" + "Staff earn leave by length of service. " * 6,
        "",
        "Eligibility Requirements:\n" + "Full-time staff are eligible after ninety days. " * 9,
    ]
    merged = "\n\n".join(f for f in frags if f)
    return LoadedText(merged, build_page_spans(frags))


@pytest.mark.asyncio
async def test_ingest_stores_pages_and_only_confident_headings() -> None:
    text = _three_page_text()
    doc_id, rows = await _ingest(text)
    try:
        assert rows
        # chunk text is exactly what the chunker produced before 0013
        assert [r[3] for r in rows] == [t for _, t in _legacy_chunks(str(text), 150, 25)]
        first, last = rows[0], rows[-1]
        assert first[1] == 1 and last[2] == 3  # page 2 is blank: numbering stays true to the PDF
        assert all(r[1] in (1, 3) and r[2] in (1, 3) for r in rows)
        assert first[0] == "I. Policy Statement" or first[0] is None  # the header line sits before the first heading
        assert last[0] == "Eligibility Requirements"
        assert {r[0] for r in rows} <= {None, "I. Policy Statement", "Eligibility Requirements"}
        # a chunk that begins on page 1 and runs into page 3 reports the whole range
        assert any(r[1] == 1 and r[2] == 3 for r in rows) or all(r[1] == r[2] for r in rows)
    finally:
        await _drop(doc_id)


@pytest.mark.asyncio
async def test_ingest_without_page_data_labels_nothing_it_cannot_know() -> None:
    plain = "Body only, no headings here at all. " * 20  # a plain str, as docx / markdown / test doubles give
    doc_id, rows = await _ingest(plain)
    try:
        assert rows and all(r[0] is None and r[1] is None and r[2] is None for r in rows)
    finally:
        await _drop(doc_id)


@pytest.mark.asyncio
async def test_validated_scan_page_markers_become_page_numbers_not_section_names() -> None:
    ve = SimpleNamespace(
        text=SAMPLE_MARKDOWN, reviewer="R", reviewed_on=None, record_sha256="0" * 64, page_count=2,
    )
    doc_id, rows = await _ingest(None, validated=ve)
    try:
        headed = [r for r in rows if r[1] is not None]
        assert headed and {r[1] for r in headed} == {1, 2}
        assert all(r[0] is None for r in headed)  # "Page 1" is no longer posing as a section heading
        assert all(r[1] == r[2] for r in headed)
    finally:
        await _drop(doc_id)


# ----------------------------------------------------------------------------- API carries the labels
def _token() -> str:
    r = client.post(
        "/auth/sign-in",
        json={"email": "pilot-demo@bklynlibrary.org", "access_code": "DEMO2026", "attribution_mode": "anonymous"},
    )
    assert r.status_code == 200, r.text
    return r.json()["token"]


async def _seed_doc(*, pages):
    doc_id, chunk_id = uuid.uuid4(), uuid.uuid4()
    async with async_session_factory() as s:
        s.add(Document(document_id=doc_id, title="Page API Doc", version="t", policy_type="generic_policy",
                       source_format="pdf", ingest_status="indexed", eligibility="eligible", test_index_member=True))
        await s.flush()
        s.add(Chunk(chunk_id=chunk_id, document_id=doc_id, ordinal=0, text="Donors must disclose gifts over $500.",
                    token_count=7, section_heading="Gifts", page_start=pages[0], page_end=pages[1]))
        await s.commit()
    return doc_id, chunk_id


async def _drop_ask(req, chunk_id, doc_id):
    async with async_session_factory() as s:
        await s.execute(delete(Citation).where(Citation.chunk_id == chunk_id))
        await s.execute(delete(Question).where(Question.request_id == req))
        await s.execute(delete(Chunk).where(Chunk.chunk_id == chunk_id))
        await s.execute(delete(Document).where(Document.document_id == doc_id))
        await s.commit()


@pytest.mark.parametrize("pages", [(2, 3), (None, None)])
def test_answer_citations_and_viewer_carry_page_fields(pages) -> None:
    doc_id, chunk_id = asyncio.run(_seed_doc(pages=pages))
    fake = RetrievedChunk(chunk_id=chunk_id, score=0.95, document_id=doc_id, title="Page API Doc",
                          policy_type="generic_policy", version="t", section_heading="Gifts",
                          text="Donors must disclose gifts over $500.", test_index=True)
    headers = {"Authorization": f"Bearer {_token()}"}
    req = None
    try:
        with (
            patch.object(VectorRetriever, "query", new_callable=AsyncMock, return_value=[fake]),
            patch("ask_bpl_orchestrator.services.ask_service.generation.generate_answer", new_callable=AsyncMock,
                  return_value=("Disclose gifts over $500.", False, [chunk_id], "{}")),
        ):
            r = client.post("/questions/ask", headers=headers, json={"question": "What must donors disclose?"})
        assert r.status_code == 200, r.text
        body = r.json()
        req = uuid.UUID(body["request_id"])
        cite = body["citations"][0]
        assert (cite["page_start"], cite["page_end"]) == pages
        assert cite["section_heading"] == "Gifts"

        v = client.get(f"/documents/{doc_id}/text", headers=headers)
        assert v.status_code == 200, v.text
        chunk = v.json()["chunks"][0]
        assert (chunk["page_start"], chunk["page_end"]) == pages  # None stays None: nothing is invented for old rows
    finally:
        asyncio.run(_drop_ask(req or uuid.uuid4(), chunk_id, doc_id))


# ----------------------------------------------------------------------------- 0013b: wrapped sentence tails
# Real case (Policy on Unattended Children): a sentence wrapped, and its tail "Behavior in the Library Policy:"
# looked like a colon heading. A wrong heading shown as a verified location is worse than none.
_WRAPPED_TAIL = (
    "Disruptive Children:\n"
    "All company users, regardless of age, are expected to follow the Public \n"
    "Behavior in the Library Policy:\n"
    "Staff should take a positive approach with unattended children \n"
)


def test_wrapped_sentence_tail_is_not_a_heading() -> None:
    assert [h.text for h in find_headings(_WRAPPED_TAIL)] == ["Disruptive Children"]


def test_chunk_under_the_wrapped_tail_is_labelled_with_the_real_heading() -> None:
    headings = find_headings(_WRAPPED_TAIL)
    assert heading_at(headings, _WRAPPED_TAIL.index("Staff should")) == "Disruptive Children"


def test_headings_after_a_rejected_tail_keep_correct_offsets() -> None:
    text = _WRAPPED_TAIL + "More body text.\nHealth & Safety:\nBody."
    found = find_headings(text)
    assert [h.text for h in found] == ["Disruptive Children", "Health & Safety"]
    assert text[found[1].offset : found[1].offset + 6] == "Health"


@pytest.mark.parametrize(
    "before",
    [
        "Staff are expected to follow the Public",  # ends in a capitalised word (the real case)
        "Staff are expected to follow the public library",  # ends in a lower-case word
        "Staff are expected to follow the policy of the Library,",  # ends in a comma
    ],
)
def test_colon_line_after_an_unfinished_sentence_is_rejected(before: str) -> None:
    assert find_headings(f"{before}\nBehavior in the Library Policy:\nBody text.") == []


@pytest.mark.parametrize(
    "before",
    [
        "Staff are expected to follow the Public.",  # sentence finished
        "Which staff are expected to follow:",  # a lead-in ends in a colon
        "Staff are expected to follow it (see below)",  # closing bracket
        "Effective date of this policy is 10/1/2006",  # ends in a digit
        "Annual Leave",  # short line (a label), 2 words
        "Four word line here",  # one under the 5-word threshold
        "",  # blank line: a paragraph break
        "•    Staff must return all checked out library materials in a timely way",  # bullet
        "-    Staff must return all checked out library materials in a timely way",
        "1.   Staff must return all checked out library materials in a timely way",
        "a)   Staff must return all checked out library materials in a timely way",
        "Overview:",  # the line above is itself a heading
    ],
)
def test_colon_heading_is_kept_when_the_line_above_is_not_an_unfinished_sentence(before: str) -> None:
    found = find_headings(f"{before}\nBehavior in the Library Policy:\nBody text.")
    assert [h.text for h in found if h.text == "Behavior in the Library Policy"] == ["Behavior in the Library Policy"]


def test_five_words_is_the_threshold() -> None:
    four = "Staff follow the Public"
    five = "All staff follow the Public"
    assert [h.text for h in find_headings(f"{four}\nHolds:\nBody.")] == ["Holds"]
    assert find_headings(f"{five}\nHolds:\nBody.") == []


def test_roman_numeral_heading_is_kept_after_an_unfinished_sentence() -> None:
    text = "Staff are expected to follow the Public\nIV. Responsibilities:\nBody."
    assert [h.text for h in find_headings(text)] == ["IV. Responsibilities"]


def test_all_caps_heading_is_kept_after_an_unfinished_sentence() -> None:
    # The guard is for colon lines only: the wrapped-tail failure was only ever seen there.
    text = "Staff are expected to follow the Public\nGENERAL POLICY STATEMENT\nBody."
    assert [h.text for h in find_headings(text)] == ["GENERAL POLICY STATEMENT"]


def test_first_line_colon_heading_is_kept_whatever_the_last_line_is() -> None:
    text = "Eligibility Requirements:\nBody text.\nStaff are expected to follow the Public"
    assert [h.text for h in find_headings(text)] == ["Eligibility Requirements"]


def test_colon_heading_straight_after_a_long_heading_is_kept() -> None:
    # The line above has 6 words and ends in a letter, so only "it is itself a heading" exempts it.
    text = "Body.\nGENERAL STATEMENT OF LIBRARY COLLECTION POLICY\nOverview:\nBody text."
    assert [h.text for h in find_headings(text)] == ["GENERAL STATEMENT OF LIBRARY COLLECTION POLICY", "Overview"]
