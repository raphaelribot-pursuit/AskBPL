"""Sentence-aware chunk boundaries (patch 0014; PRD ING-11, GRD-4).

Hermetic like test_provenance.py: a REAL tiktoken ``Encoding`` with a toy byte-level vocabulary (one token per
byte), so the size limit is exact and easy to reason about. Sample text is modelled on the indexed policies.
"""

from __future__ import annotations

import re
from pathlib import Path
from unittest.mock import patch

import pytest
from sqlalchemy import select

from ask_bpl_orchestrator.config import Settings
from ask_bpl_orchestrator.db.models import Chunk
from ask_bpl_orchestrator.ingest import provenance_report
from ask_bpl_orchestrator.ingest.chunking import split_text_with_sections
from ask_bpl_orchestrator.ingest.loaders import LoadedText
from ask_bpl_orchestrator.ingest.provenance import build_page_spans, find_headings
from tests.test_provenance import ENC, _drop, _ingest

POLICY = (
    "Policy #: IV. Public 2\nDate Issued: 9/20/05\n\n"
    "POLICY\n"
    "The Organization welcomes and encourages children to use the Library. Staff should treat every child with "
    "courtesy. An unattended child is a child who is left alone in a Library building for a long period of time. "
    "Dr. Lee of Public Services says staff should e.g. call the supervisor first. See No. 5 on the form.\n"
    "Disruptive Children:\n"
    "All Library users, regardless of age, are expected to follow the Rules of Behavior. Staff will first speak to "
    "the child. If the behavior continues, staff will speak to the parent or guardian. Repeated problems go to "
    "the Branch Manager. A written report is filed the same day.\n"
    "Health & Safety:\n"
    "If an unattended child appears ill or is in danger, call 911 at once. Do not leave the child alone. "
    "Notify the Branch Manager as soon as it is safe to do so. First aid kits are kept at the desk.\n"
)


def chunk(text, size=160, overlap=40, **kw):
    return split_text_with_sections(text, model_name="x", chunk_size=size, overlap=overlap, encoder=ENC, **kw)


def headings_of(text):
    return [h.offset for h in find_headings(text.strip())]


def tokens(text: str) -> int:
    return len(ENC.encode(text))


def covered(segments, stripped: str) -> bool:
    seen = bytearray(len(stripped))
    for seg in segments:
        for k in range(seg.start_char, seg.end_char):
            seen[k] = 1
    return all(seen[k] for k, ch in enumerate(stripped) if not ch.isspace())


# ----------------------------------------------------------------------------- the three guarantees
def test_every_chunk_starts_where_a_sentence_starts() -> None:
    stripped = POLICY.strip()
    heads = set(headings_of(POLICY))
    for seg in chunk(POLICY, boundaries=sorted(heads)):
        before = stripped[: seg.start_char].rstrip()
        clean = not before or before[-1] in ".!?:" or seg.start_char in heads
        assert clean, f"chunk starts mid-sentence: {seg.text[:40]!r}"


def test_chunk_text_is_the_exact_slice_of_the_document_it_claims() -> None:
    stripped = POLICY.strip()
    segments = chunk(POLICY, boundaries=headings_of(POLICY))
    assert len(segments) > 3
    assert all(stripped[s.start_char : s.end_char] == s.text for s in segments)


@pytest.mark.parametrize("size", [90, 160, 400])
def test_no_chunk_exceeds_the_token_limit(size: int) -> None:
    segments = chunk(POLICY, size=size, overlap=size // 4, boundaries=headings_of(POLICY))
    assert all(tokens(s.text) <= size for s in segments)


@pytest.mark.parametrize("size", [90, 160, 400])
def test_no_text_of_the_document_is_dropped(size: int) -> None:
    segments = chunk(POLICY, size=size, overlap=size // 4, boundaries=headings_of(POLICY))
    assert covered(segments, POLICY.strip())


# ----------------------------------------------------------------------------- sentence detection
@pytest.mark.parametrize(
    "lead, abbreviation_tail",
    [
        ("Please ask Dr.", "Smith about the matter."),
        ("Call a supervisor, e.g.", "The Branch Manager, if one is on duty."),
        ("Fill in form No.", "5 before the end of the day."),
        ("The form is signed by J.", "Smith and filed with Human Resources."),
        ("Read this first:\n1.", "Introduction before you begin."),
    ],
)
def test_an_abbreviation_or_list_marker_is_not_the_end_of_a_sentence(lead: str, abbreviation_tail: str) -> None:
    text = f"Staff report each incident to a supervisor. {lead} {abbreviation_tail} Keep a copy of every report."
    first_sentence = "Staff report each incident to a supervisor."
    segments = chunk(text, size=len(first_sentence) + len(lead) + 4, overlap=0)  # room for one sentence, not two
    assert len(segments) >= 2
    assert not any(s.text.endswith(lead.split()[-1]) for s in segments), "cut right after the abbreviation"
    assert not any(s.text.startswith(abbreviation_tail.split()[0]) for s in segments)


def test_a_new_line_that_starts_a_list_item_starts_a_new_unit() -> None:
    text = "Staff may not:\n\u2022 Share passwords with anyone at all\n\u2022 Install unapproved software on library computers\n\u2022 Leave a logged-in session unattended"
    segments = chunk(text, size=70, overlap=0)
    assert len(segments) >= 2
    assert all(s.text.startswith(("Staff", "\u2022")) for s in segments)


def test_a_chunk_can_fill_up_through_list_items_and_cut_between_two_of_them() -> None:
    text = (
        "Do this first. Staff may not:\n\u2022 Share passwords with anyone\n\u2022 Install unapproved software here\n"
        "\u2022 Leave a session open overnight. Report breaches at once."
    )
    segments = chunk(text, size=75, overlap=0)
    assert segments[0].text == "Do this first. Staff may not:\n\u2022 Share passwords with anyone"
    assert segments[1].text.startswith("\u2022 Install")


# ----------------------------------------------------------------------------- headings
def test_a_chunk_starts_exactly_at_every_heading_that_has_enough_text_under_it() -> None:
    stripped = POLICY.strip()
    segments = chunk(POLICY, size=400, overlap=40, boundaries=headings_of(POLICY))
    starts = {s.start_char for s in segments}
    for heading in ("Disruptive Children:", "Health & Safety:"):
        assert stripped.index(heading) in starts


def test_chunks_never_straddle_a_heading_with_real_text_under_it() -> None:
    stripped = POLICY.strip()
    bounds = [stripped.index("Disruptive Children:"), stripped.index("Health & Safety:")]
    for seg in chunk(POLICY, size=400, overlap=40, boundaries=bounds):
        assert not any(seg.start_char < b < seg.end_char for b in bounds)


def test_overlap_never_reaches_back_across_a_heading() -> None:
    stripped = POLICY.strip()
    cut = stripped.index("Health & Safety:")
    after = [s for s in chunk(POLICY, size=120, overlap=60, boundaries=[cut]) if s.start_char >= cut]
    assert after and after[0].start_char == cut
    assert all(s.start_char >= cut for s in after)


def test_overlap_repeats_whole_sentences_inside_one_section() -> None:
    body = " ".join(f"Rule number {n} applies to every branch." for n in range(1, 13))
    segments = chunk(body, size=120, overlap=50)
    assert len(segments) >= 3
    for a, b in zip(segments, segments[1:]):
        assert b.start_char < a.end_char, "consecutive chunks should overlap"
        assert b.start_char > a.start_char, "and always move forward"
        assert tokens(body[b.start_char : a.end_char]) <= 50


def test_zero_overlap_means_chunks_do_not_repeat_text() -> None:
    body = " ".join(f"Rule number {n} applies to every branch." for n in range(1, 13))
    segments = chunk(body, size=120, overlap=0)
    assert all(b.start_char >= a.end_char for a, b in zip(segments, segments[1:]))


def test_a_heading_with_almost_nothing_under_it_joins_the_next_section() -> None:
    text = (
        "Procedures or Guidelines:\n"
        "A. PRIVATE FUNDRAISING:\n"
        + "Staff may not solicit gifts on behalf of the Library without approval. " * 4
    )
    stripped = text.strip()
    segments = chunk(text, size=400, overlap=40, boundaries=headings_of(text))
    assert len(segments) == 1 and segments[0].start_char == 0  # no heading-only chunk


def test_a_short_last_section_is_kept_not_dropped() -> None:
    text = "Staff may not solicit gifts without approval. " * 12 + "\nRELATED FORMS\n"
    segments = chunk(text, size=200, overlap=0, boundaries=headings_of(text))
    assert segments[-1].text.endswith("RELATED FORMS") and covered(segments, text.strip())


def test_markdown_section_headings_are_still_carried_on_their_first_chunk() -> None:
    text = "Preamble sentence one. Preamble sentence two.\n\n## Page 1\n\nFirst page body here. More of it follows.\n\n## Page 2\n\nSecond page body here."
    segments = chunk(text, size=400, overlap=0)
    assert [s.section_heading for s in segments] == [None, "Page 1", "Page 2"]
    assert all("##" not in s.text for s in segments)


# ----------------------------------------------------------------------------- long runs with no sentence end
def test_a_long_run_of_lines_is_split_at_line_starts_not_mid_word() -> None:
    lines = [f"Row {n} Annual leave accrual hours" for n in range(1, 30)]
    text = "\n".join(lines)
    segments = chunk(text, size=120, overlap=0)
    assert len(segments) >= 3
    assert all(s.text.startswith("Row ") for s in segments)
    assert all(tokens(s.text) <= 120 for s in segments)


def test_a_long_run_with_no_lines_or_punctuation_is_split_at_word_boundaries() -> None:
    text = " ".join(f"word{n}" for n in range(1, 120))
    stripped = text.strip()
    segments = chunk(text, size=100, overlap=0)
    assert len(segments) >= 3
    assert all(s.start_char == 0 or stripped[s.start_char - 1] == " " for s in segments)
    assert covered(segments, stripped) and all(tokens(s.text) <= 100 for s in segments)


def test_a_single_word_longer_than_a_chunk_still_terminates_and_is_covered() -> None:
    text = "See " + "x" * 500 + " for details."
    segments = chunk(text, size=100, overlap=10)
    assert covered(segments, text.strip()) and all(tokens(s.text) <= 100 for s in segments)


# ----------------------------------------------------------------------------- entry point
def test_sentence_is_the_default_strategy() -> None:
    assert [s.text for s in chunk(POLICY)] == [s.text for s in chunk(POLICY, strategy="sentence")]
    assert [s.text for s in chunk(POLICY)] != [s.text for s in chunk(POLICY, strategy="token")]


def test_an_unknown_strategy_is_refused_rather_than_silently_ignored() -> None:
    with pytest.raises(ValueError, match="strategy"):
        chunk(POLICY, strategy="paragraph")


def test_offsets_do_not_depend_on_the_tokenizer_supporting_them() -> None:
    class NoOffsets:
        encode = staticmethod(ENC.encode)
        decode = staticmethod(ENC.decode)

        def decode_with_offsets(self, tokens):
            raise NotImplementedError

    stripped = POLICY.strip()
    got = split_text_with_sections(POLICY, model_name="x", chunk_size=160, overlap=40, encoder=NoOffsets())
    assert got and all(stripped[s.start_char : s.end_char] == s.text for s in got)


def test_empty_text_gives_the_same_single_empty_segment_as_the_token_strategy() -> None:
    assert [(s.section_heading, s.text) for s in chunk("  \n ")] == [(s.section_heading, s.text) for s in chunk("  \n ", strategy="token")]


def test_chunk_strategy_setting_defaults_to_sentence_and_can_be_switched_back(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CHUNK_STRATEGY", raising=False)
    assert Settings(_env_file=None).chunk_strategy == "sentence"
    monkeypatch.setenv("CHUNK_STRATEGY", "token")
    assert Settings(_env_file=None).chunk_strategy == "token"


# ----------------------------------------------------------------------------- ingest writes the new chunks
def _pdf_like():
    frags = [POLICY[: len(POLICY) // 2].strip(), POLICY[len(POLICY) // 2 :].strip()]
    return LoadedText("\n\n".join(frags), build_page_spans(frags))


@pytest.mark.asyncio
async def test_ingest_stores_sentence_chunks_whose_heading_label_covers_the_whole_chunk() -> None:
    text = _pdf_like()
    doc_id, rows = await _ingest(text, strategy="sentence")
    try:
        assert len(rows) > 3
        heads = headings_of(str(text))
        stripped = str(text).strip()
        for heading, page_start, page_end, body in rows:
            start = stripped.index(body)
            assert not any(start < h < start + len(body) for h in heads if h != 0)
            assert page_start is not None and page_end is not None
        assert {"Disruptive Children", "Health & Safety"} <= {r[0] for r in rows}
    finally:
        await _drop(doc_id)


@pytest.mark.asyncio
async def test_ingest_with_the_token_strategy_keeps_the_old_chunks() -> None:
    text = _pdf_like()
    doc_id_a, token_rows = await _ingest(text, strategy="token")
    await _drop(doc_id_a)
    doc_id_b, sentence_rows = await _ingest(text, strategy="sentence")
    try:
        assert [r[3] for r in token_rows] != [r[3] for r in sentence_rows]
        assert " ".join(token_rows[0][3].split()[:3]) == " ".join(sentence_rows[0][3].split()[:3])  # same document start
    finally:
        await _drop(doc_id_b)


# ----------------------------------------------------------------------------- the report
def _report_counts(strategy: str) -> tuple[int, int]:
    body = (POLICY * 3).strip()  # long enough to span several chunks at the report's stand-in size
    text = LoadedText(body, build_page_spans([body]))
    with patch.object(provenance_report, "load_bytes", return_value=text):
        out = provenance_report.report(Path("p.pdf"), stand_in=True, strategy=strategy)
    found = re.search(rf"strategy {strategy}: (\d+) start mid-sentence; (\d+) straddle a heading", out)
    assert found, out
    return int(found.group(1)), int(found.group(2))


def test_report_shows_the_sentence_strategy_removing_mid_sentence_starts_and_heading_straddles() -> None:
    token_mid, token_straddle = _report_counts("token")
    sentence_mid, sentence_straddle = _report_counts("sentence")
    assert token_mid > 0 and token_straddle > 0
    assert sentence_mid == 0 and sentence_straddle < token_straddle


@pytest.mark.parametrize(
    "text, offset, headings, expected",
    [
        ("One sentence. Next sentence.", 14, (), True),
        ("A sentence that wraps onto\nthe next line here.", 27, (), False),  # a line start is not a sentence start
        ("A sentence that runs on and on", 10, (), False),
        ("A sentence that wraps onto\nHEADING:\nBody.", 27, (27,), True),  # ...unless a confident heading starts there
        ("List:\n\u2022 first \u2022 second", 14, (), True),
        ("anything", 0, (), True),
    ],
)
def test_starts_a_sentence_helper(text: str, offset: int, headings: tuple, expected: bool) -> None:
    assert provenance_report.starts_a_sentence(text, offset, set(headings)) is expected
