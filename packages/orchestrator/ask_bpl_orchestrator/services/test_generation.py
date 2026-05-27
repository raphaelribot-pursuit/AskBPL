"""
Ask BPL — Generation Module Tests
===================================
Engineer : Denward Lee Aulder
Aligned  : TRD-GEN-2, GEN-3, GEN-4, GEN-5, GEN-6, TRD-RTG-1 through RTG-6

Run with:  pytest test_generation.py -v

These tests cover:
  1. System prompt constraints (length, tone, routing table, ED removal)
  2. Citation verifier (pass / fail / no-citation cases)
  3. Response parser — answer, refusal + ROUTE extraction
  4. GenerationResult.to_client_dict routing card output
  5. generate() integration via mocked Anthropic client
     — happy path, refusal + route, verification-fail, empty chunks, API error
"""

import pytest
from unittest.mock import MagicMock
from generation import (
    SYSTEM_PROMPT,
    MAX_TOKENS,
    RetrievedChunk,
    Citation,
    GenerationResult,
    _build_user_message,
    _verify_citations,
    _parse_response,
    generate,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def make_chunk(
    doc="Annual Leave Policy",
    section="Section 3 — Accrual",
    text="Staff accrue annual leave at a rate of 1.25 days per month.",
    score=0.91,
    chunk_id="chunk-001",
) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=chunk_id,
        document_name=doc,
        section=section,
        text=text,
        score=score,
    )


def make_claude_response(text: str):
    content_block = MagicMock()
    content_block.text = text
    response = MagicMock()
    response.content = [content_block]
    return response


# ---------------------------------------------------------------------------
# 1. System prompt content checks  (v2)
# ---------------------------------------------------------------------------

class TestSystemPrompt:
    def test_absolute_rules_present(self):
        assert "ABSOLUTE RULES" in SYSTEM_PROMPT

    def test_only_use_context_rule(self):
        assert "ONLY answer from the policy documents" in SYSTEM_PROMPT

    def test_no_long_passages_rule(self):
        assert "NEVER reproduce long passages" in SYSTEM_PROMPT

    def test_no_legal_advice_rule(self):
        assert "NEVER give legal advice" in SYSTEM_PROMPT

    def test_ed_removal_rule(self):
        """Executive Director must be explicitly excluded (Selvon, May 26)."""
        assert "Executive Director" in SYSTEM_PROMPT
        assert "not part of the routing hierarchy" in SYSTEM_PROMPT

    def test_sentence_cap_stated(self):
        assert "2–4 sentences" in SYSTEM_PROMPT or "2 to 4 sentences" in SYSTEM_PROMPT

    def test_colleague_voice_stated(self):
        assert "knowledgeable colleague" in SYSTEM_PROMPT

    def test_no_legal_hedging_examples(self):
        assert "pursuant to" in SYSTEM_PROMPT

    def test_unified_answer_rule(self):
        """Multi-policy questions must produce one answer, not one section per source."""
        assert "One unified answer" in SYSTEM_PROMPT or "unified" in SYSTEM_PROMPT

    def test_routing_table_present(self):
        """Policy routing table must be embedded in prompt (TRD-RTG-1)."""
        assert "POLICY ROUTING TABLE" in SYSTEM_PROMPT

    def test_routing_table_covers_all_policy_types(self):
        """All 8 policy areas from routing_config.yaml must be represented."""
        required = [
            "Materials selection",
            "Unattended children",
            "Annual leave",
            "Conflict of interest",
            "Gift acceptance",
            "Volunteer management",
            "Technology use",
            "Data retention",
        ]
        for area in required:
            assert area in SYSTEM_PROMPT, f"Missing policy area: {area}"

    def test_fallback_route_to_hr(self):
        """Unmatched questions must route to HR / supervisor (TRD-RTG-5)."""
        assert "Human Resources" in SYSTEM_PROMPT
        assert "direct supervisor" in SYSTEM_PROMPT

    def test_no_vague_routing(self):
        """Prompt must prohibit generic routing deflections."""
        assert "contact management" in SYSTEM_PROMPT  # appears in the DO NOT list

    def test_refusal_route_format_documented(self):
        assert "ROUTE:" in SYSTEM_PROMPT

    def test_source_format_described(self):
        assert "SOURCE:" in SYSTEM_PROMPT

    def test_answer_format_described(self):
        assert "ANSWER:" in SYSTEM_PROMPT

    def test_max_tokens_ceiling(self):
        assert MAX_TOKENS == 300


# ---------------------------------------------------------------------------
# 2. Citation verifier
# ---------------------------------------------------------------------------

class TestCitationVerifier:
    def test_valid_single_source(self):
        raw = (
            "ANSWER: Staff accrue leave monthly.\n\n"
            "SOURCE: Annual Leave Policy | Section 3 — Accrual"
        )
        chunks = [make_chunk(doc="Annual Leave Policy")]
        ok, unverified = _verify_citations(raw, chunks)
        assert ok is True
        assert unverified == []

    def test_invalid_source_not_in_chunks(self):
        raw = (
            "ANSWER: Some answer.\n\n"
            "SOURCE: Made Up Policy | Section 1"
        )
        chunks = [make_chunk(doc="Annual Leave Policy")]
        ok, unverified = _verify_citations(raw, chunks)
        assert ok is False
        assert "Made Up Policy" in unverified

    def test_no_source_line_fails(self):
        raw = "ANSWER: Some answer with no source at all."
        chunks = [make_chunk()]
        ok, unverified = _verify_citations(raw, chunks)
        assert ok is False

    def test_multiple_valid_sources(self):
        raw = (
            "ANSWER: Combined answer.\n\n"
            "SOURCE: Annual Leave Policy | Section 3\n"
            "        Conflict of Interest Policy | Section C"
        )
        chunks = [
            make_chunk(doc="Annual Leave Policy"),
            make_chunk(doc="Conflict of Interest Policy", chunk_id="chunk-002"),
        ]
        ok, unverified = _verify_citations(raw, chunks)
        assert ok is True

    def test_case_insensitive_match(self):
        raw = "ANSWER: Fine.\n\nSOURCE: annual leave policy | Section 3"
        chunks = [make_chunk(doc="Annual Leave Policy")]
        ok, _ = _verify_citations(raw, chunks)
        assert ok is True


# ---------------------------------------------------------------------------
# 3. Response parser — v2 (3-tuple including route)
# ---------------------------------------------------------------------------

class TestParseResponse:
    def test_parses_answer_and_source(self):
        raw = (
            "ANSWER: New staff can use annual leave after a 90-day waiting period.\n\n"
            "SOURCE: Annual Leave Policy | Section 2 — Eligibility"
        )
        answer, citations, route = _parse_response(raw)
        assert "90-day" in answer
        assert len(citations) == 1
        assert citations[0].document == "Annual Leave Policy"
        assert "Eligibility" in citations[0].section
        assert route is None

    def test_parses_refusal_with_route(self):
        raw = (
            "REFUSAL: This leave scenario isn't addressed in the loaded policies.\n"
            "ROUTE: Human Resources | Contact HR directly for guidance on your situation."
        )
        answer, citations, route = _parse_response(raw)
        assert "leave scenario" in answer
        assert citations == []
        assert route is not None
        assert "Human Resources" in route
        assert "Contact HR" in route

    def test_parses_refusal_without_route(self):
        """Graceful handling if model omits ROUTE line."""
        raw = "REFUSAL: I can only answer from BPL's loaded policies."
        answer, citations, route = _parse_response(raw)
        assert "BPL" in answer
        assert citations == []
        assert route is None

    def test_parses_multiple_citations(self):
        raw = (
            "ANSWER: Small gifts from vendors are generally okay; cash never is.\n\n"
            "SOURCE: Conflict of Interest Policy | Section C — Gifts\n"
            "        Gift Acceptance Policy | Section 3 — Donor Vetting"
        )
        _, citations, route = _parse_response(raw)
        assert len(citations) == 2
        docs = [c.document for c in citations]
        assert "Conflict of Interest Policy" in docs
        assert "Gift Acceptance Policy" in docs
        assert route is None

    def test_refusal_route_split_into_team_and_contact(self):
        """to_client_dict must split ROUTE into team + contact_guidance."""
        result = GenerationResult(
            answered=False,
            refusal_reason="Not in corpus.",
            route="Collection Services or Materials Review Committee | Contact them directly.",
        )
        d = result.to_client_dict()
        assert d["answered"] is False
        assert d["routing"] is not None
        assert "Collection Services" in d["routing"]["team"]
        assert "Contact them directly" in d["routing"]["contact_guidance"]

    def test_to_client_dict_answered_excludes_routing(self):
        result = GenerationResult(
            answered=True,
            answer_text="Staff accrue leave monthly.",
            citations=[Citation(document="Annual Leave Policy", section="Section 3")],
        )
        d = result.to_client_dict()
        assert d["answered"] is True
        assert "answer" in d
        assert "_raw_response" not in d   # TRD-LOG-3
        assert "routing" not in d

    def test_to_client_dict_refusal_no_route(self):
        """Refusal without a route should return routing: None."""
        result = GenerationResult(
            answered=False,
            refusal_reason="Not in corpus.",
            route=None,
        )
        d = result.to_client_dict()
        assert d["routing"] is None


# ---------------------------------------------------------------------------
# 4. generate() integration (mocked Anthropic client)
# ---------------------------------------------------------------------------

class TestGenerate:
    def _make_client(self, response_text: str) -> MagicMock:
        client = MagicMock()
        client.messages.create.return_value = make_claude_response(response_text)
        return client

    def test_happy_path(self):
        claude_output = (
            "ANSWER: New staff must wait 90 days before using annual leave.\n\n"
            "SOURCE: Annual Leave Policy | Section 2 — Eligibility"
        )
        client = self._make_client(claude_output)
        chunks = [make_chunk(doc="Annual Leave Policy")]
        result = generate("When can new hires use annual leave?", chunks, client)

        assert result.answered is True
        assert "90 days" in result.answer_text
        assert len(result.citations) == 1
        assert result.route is None

    def test_refusal_with_route(self):
        """Refusal response should populate route on the result."""
        claude_output = (
            "REFUSAL: This materials question isn't covered in the loaded policies.\n"
            "ROUTE: Collection Services or Materials Review Committee | Contact them directly."
        )
        client = self._make_client(claude_output)
        chunks = [make_chunk()]
        result = generate("Can we stock graphic novels?", chunks, client)

        assert result.answered is False
        assert result.route is not None
        assert "Collection Services" in result.route

    def test_route_surfaces_in_client_dict(self):
        """Route must appear in the client-facing dict for the routing card."""
        claude_output = (
            "REFUSAL: Annual leave edge case not in loaded policies.\n"
            "ROUTE: Human Resources | Contact HR directly."
        )
        client = self._make_client(claude_output)
        chunks = [make_chunk()]
        result = generate("Can I carry over 40 days of leave?", chunks, client)
        d = result.to_client_dict()

        assert d["routing"] is not None
        assert "Human Resources" in d["routing"]["team"]

    def test_ed_not_in_routing(self):
        """Executive Director must never appear in a route from generate()."""
        claude_output = (
            "REFUSAL: Not in corpus.\n"
            "ROUTE: Human Resources | Contact HR."
        )
        client = self._make_client(claude_output)
        chunks = [make_chunk()]
        result = generate("Some question?", chunks, client)
        d = result.to_client_dict()

        if d["routing"]:
            assert "Executive Director" not in d["routing"].get("team", "")
            assert "Executive Director" not in d["routing"].get("contact_guidance", "")

    def test_citation_verification_failure_returns_refusal(self):
        claude_output = (
            "ANSWER: Some plausible-sounding answer.\n\n"
            "SOURCE: Hallucinated Policy Name | Section 99"
        )
        client = self._make_client(claude_output)
        chunks = [make_chunk(doc="Annual Leave Policy")]
        result = generate("Some question?", chunks, client)

        assert result.answered is False
        assert result.answer_text == ""

    def test_empty_chunks_returns_refusal(self):
        client = MagicMock()
        result = generate("What is the leave policy?", [], client)
        assert result.answered is False
        client.messages.create.assert_not_called()

    def test_api_error_returns_safe_refusal(self):
        import anthropic as anthropic_module
        client = MagicMock()
        client.messages.create.side_effect = anthropic_module.APIError(
            message="Service unavailable", request=MagicMock(), body=None
        )
        chunks = [make_chunk()]
        result = generate("What is the leave policy?", chunks, client)

        assert result.answered is False
        assert "Service unavailable" not in result.refusal_reason  # TRD-LOG-3

    def test_raw_response_not_in_client_dict(self):
        claude_output = (
            "ANSWER: Annual leave accrues at 1.25 days per month.\n\n"
            "SOURCE: Annual Leave Policy | Section 3"
        )
        client = self._make_client(claude_output)
        chunks = [make_chunk(doc="Annual Leave Policy")]
        result = generate("How does leave accrue?", chunks, client)
        d = result.to_client_dict()
        assert "_raw_response" not in d

    def test_chunks_sorted_by_score(self):
        chunks = [
            make_chunk(doc="Low Score Doc", score=0.55, chunk_id="c1"),
            make_chunk(doc="High Score Doc", score=0.95, chunk_id="c2"),
        ]
        message = _build_user_message("test question", chunks)
        high_pos = message.find("High Score Doc")
        low_pos = message.find("Low Score Doc")
        assert high_pos < low_pos
