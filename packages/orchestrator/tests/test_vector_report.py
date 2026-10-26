"""Patch 0022: `askbpl-vector-report` (PRD ING-13, ING-7, NFR-6; closes the "Pinecone was not asked" gap of patches 0020/0021).

The report is read-only evidence about the vector index. These tests exist to stop it from (a) writing or querying
anything, (b) calling it clean when it could not look, (c) mixing up which side is missing what, and (d) printing a secret.
Pinecone is always a fake here; the database is the real test Postgres, scoped to the rows each test creates.
"""

from __future__ import annotations

import asyncio
import csv
import re
import sys
import uuid
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, Iterable, List, Optional

import pytest
from sqlalchemy import delete, func, select

from ask_bpl_orchestrator import corpus_report as cr
from ask_bpl_orchestrator import vector_report as vr
from ask_bpl_orchestrator.config import Settings, get_settings
from ask_bpl_orchestrator.db.models import Chunk, Document, Eligibility, ExtractionStatus, IngestStatus, SourceFormat
from ask_bpl_orchestrator.db.session import async_session_factory

ORCH = Path(__file__).resolve().parents[1]
REPO = ORCH.parents[1]


# ------------------------------------------------------------------------------------------------ fakes
class FakeIndex:
    """A Pinecone index that holds `vectors` (id -> metadata) and refuses every write and query."""

    def __init__(self, vectors: Dict[str, Dict[str, Any]], *, page_size: int = 100, list_shape: str = "objects",
                 fetch_shape: str = "objects", list_supported: bool = True, namespaces: Optional[Dict[str, int]] = None,
                 stats_total: Optional[int] = None, fail_on: Optional[str] = None, fail_with: Optional[Exception] = None) -> None:
        self.vectors = vectors
        self.page_size, self.list_shape, self.fetch_shape = page_size, list_shape, fetch_shape
        self.list_supported = list_supported
        self.namespaces = namespaces
        self.stats_total = stats_total
        self.fail_on, self.fail_with = fail_on, fail_with or RuntimeError("boom sk-secret-KEY host=h.example")
        self.calls: List[str] = []
        self.fetch_sizes: List[int] = []

    def _maybe_fail(self, name: str) -> None:
        if self.fail_on == name:
            raise self.fail_with

    def describe_index_stats(self) -> Any:
        self.calls.append("describe_index_stats")
        self._maybe_fail("describe_index_stats")
        total = self.stats_total if self.stats_total is not None else len(self.vectors)
        if self.namespaces is None:
            return SimpleNamespace(total_vector_count=total, namespaces={"": SimpleNamespace(vector_count=len(self.vectors))})
        return SimpleNamespace(total_vector_count=sum(self.namespaces.values()),
                               namespaces={k: SimpleNamespace(vector_count=v) for k, v in self.namespaces.items()})

    def fetch(self, *, ids: List[str], namespace: str = "") -> Any:
        self.calls.append("fetch")
        self._maybe_fail("fetch")
        self.fetch_sizes.append(len(ids))
        got = {i: ({"metadata": self.vectors[i]} if self.fetch_shape == "dicts" else SimpleNamespace(metadata=self.vectors[i]))
               for i in ids if i in self.vectors}
        return {"vectors": got} if self.fetch_shape == "dicts" else SimpleNamespace(vectors=got)

    def list(self, **_k: Any) -> Iterable[Any]:
        self.calls.append("list")
        self._maybe_fail("list")
        if not self.list_supported:
            raise RuntimeError("list is not supported for pod-based indexes")
        ids = list(self.vectors)
        for start in range(0, len(ids), self.page_size):
            chunk = ids[start : start + self.page_size]
            yield chunk if self.list_shape == "lists" else SimpleNamespace(vectors=[SimpleNamespace(id=i) for i in chunk])

    def upsert(self, *a: Any, **k: Any) -> None:
        raise AssertionError("upsert was called")

    def delete(self, *a: Any, **k: Any) -> None:
        raise AssertionError("delete was called")

    def update(self, *a: Any, **k: Any) -> None:
        raise AssertionError("update was called")

    def query(self, *a: Any, **k: Any) -> None:
        raise AssertionError("query was called")


def cid() -> str:
    return str(uuid.uuid4())


def doc(label: str, n: int, *, answerable: bool = True, status: str = "indexed", did: Optional[str] = None) -> vr.DbDocument:
    return vr.DbDocument(document_id=did or str(uuid.uuid4()), title=f"Title {label}", source_id=label, source_path=f"{label}.pdf",
                         ingest_status=status, answerable=answerable, chunk_ids=[cid() for _ in range(n)])


def facts(*docs: vr.DbDocument) -> vr.DbFacts:
    return vr.DbFacts(state="checked", target="localhost/test", docs=list(docs))


def vectors_for(*docs: vr.DbDocument, skip: Iterable[str] = ()) -> Dict[str, Dict[str, Any]]:
    skip = set(skip)
    return {c: {"document_id": d.document_id, "title": d.title, "chunk_id": c} for d in docs for c in d.chunk_ids if c not in skip}


def run(db: vr.DbFacts, index: FakeIndex) -> vr.VectorReport:
    return vr.build_report(db, vr.gather_pinecone_facts(vr.ReadOnlyIndex(index), db))


def codes(rep: vr.VectorReport, severity: Optional[str] = None) -> List[str]:
    return [f.code for f in rep.findings if severity is None or f.severity == severity]


# ------------------------------------------------------------------------------------------------ A: database -> Pinecone
def test_a_clean_index_gives_no_finding_and_a_plain_headline() -> None:
    a, b = doc("S1", 3), doc("S2", 2)
    rep = run(facts(a, b), FakeIndex(vectors_for(a, b)))
    assert rep.findings == []
    assert rep.headline.startswith("5 chunks are stored in the database; 5 have a vector in Pinecone and 0 do not. 0 vectors")
    assert "NOTHING TO FIX" in vr.render(rep)


def test_a_missing_vector_on_an_answerable_document_is_urgent_and_names_the_document() -> None:
    a = doc("S1", 4)
    rep = run(facts(a), FakeIndex(vectors_for(a, skip=[a.chunk_ids[1]])))
    assert codes(rep, vr.URGENT) == ["answerable_missing_vectors"]
    f = rep.findings[0]
    assert f.subject == "S1" and "1 of 4" in f.text and "askbpl-ingest-batch" in f.todo
    assert "3 have a vector in Pinecone and 1 do not" in rep.headline


def test_a_missing_vector_on_a_document_that_cannot_answer_is_not_a_finding_but_is_counted() -> None:
    a = doc("S1", 2, answerable=False)
    rep = run(facts(a), FakeIndex({}))
    assert rep.findings == []
    assert rep.rows[0].missing and "0 have a vector in Pinecone and 2 do not" in rep.headline


def test_each_document_is_reported_separately() -> None:
    a, b, c = doc("S1", 2), doc("S2", 2), doc("S3", 2)
    rep = run(facts(a, b, c), FakeIndex(vectors_for(a, b, c, skip=[b.chunk_ids[0], c.chunk_ids[0], c.chunk_ids[1]])))
    urgent = {f.subject: f.text for f in rep.findings if f.severity == vr.URGENT}
    assert set(urgent) == {"S2", "S3"} and "1 of 2" in urgent["S2"] and "2 of 2" in urgent["S3"]


def test_one_missing_and_one_extra_cannot_cancel_out() -> None:
    """The old doctor check compared totals; equal totals hid a missing vector behind an extra one."""
    a = doc("S1", 3)
    v = vectors_for(a, skip=[a.chunk_ids[0]])
    v[cid()] = {"document_id": a.document_id, "title": a.title}
    idx = FakeIndex(v)
    assert idx.describe_index_stats().total_vector_count == 3 == len(a.chunk_ids)
    rep = run(facts(a), idx)
    assert "answerable_missing_vectors" in codes(rep) and "stale_vectors_for_stored_document" in codes(rep)


@pytest.mark.parametrize("n", [0, 1, 99, 100, 101, 250])
def test_fetch_batches_never_exceed_100_ids_and_cover_every_chunk(n: int) -> None:
    a = doc("S1", n)
    idx = FakeIndex(vectors_for(a))
    rep = run(facts(a), idx)
    assert sum(idx.fetch_sizes) == n and all(s <= 100 for s in idx.fetch_sizes)
    assert rep.rows[0].found == n and rep.rows[0].missing == []


def test_the_missing_one_is_found_at_a_batch_boundary() -> None:
    a = doc("S1", 201)
    for position in (0, 99, 100, 199, 200):
        rep = run(facts(a), FakeIndex(vectors_for(a, skip=[a.chunk_ids[position]])))
        assert len(rep.rows[0].missing) == 1, position


def test_no_chunks_at_all_makes_no_fetch_and_finds_nothing() -> None:
    idx = FakeIndex({})
    rep = run(facts(), idx)
    assert rep.findings == [] and "fetch" not in idx.calls and "0 chunks are stored" in rep.headline


def test_fetch_response_shapes_both_work() -> None:
    a = doc("S1", 2)
    for shape in ("objects", "dicts"):
        rep = run(facts(a), FakeIndex(vectors_for(a), fetch_shape=shape))
        assert rep.findings == [], shape


# ------------------------------------------------------------------------------------------------ B: Pinecone -> database
def test_orphans_of_a_document_this_database_holds_are_a_warning_with_titles() -> None:
    a = doc("S1", 2)
    v = vectors_for(a)
    v[cid()] = {"document_id": a.document_id, "title": a.title}
    rep = run(facts(a), FakeIndex(v))
    assert codes(rep, vr.WARN) == ["stale_vectors_for_stored_document"]
    f = rep.findings[0]
    assert f.subject == "1 vectors" and a.title in f.text and "retrieval slots" in f.text and "Do not delete anything" in f.todo


def test_orphans_of_a_document_this_database_does_not_know_are_only_a_note_because_the_index_is_shared() -> None:
    a = doc("S1", 2)
    v = vectors_for(a)
    other = str(uuid.uuid4())
    for _ in range(3):
        v[cid()] = {"document_id": other, "title": "Other Machine Policy"}
    rep = run(facts(a), FakeIndex(v))
    assert codes(rep, vr.WARN) == [] and codes(rep, vr.URGENT) == []
    assert codes(rep) == ["vectors_for_unknown_document"]
    assert "Other Machine Policy: 3" in rep.findings[0].text and "several machines" in rep.findings[0].text
    assert "NOTHING TO FIX" in vr.render(rep)


def test_an_orphan_with_no_metadata_is_still_reported_by_id_count() -> None:
    a = doc("S1", 1)
    v = vectors_for(a)
    v[cid()] = {}
    rep = run(facts(a), FakeIndex(v))
    assert codes(rep) == ["vectors_for_unknown_document"] and "no metadata: 1" in rep.findings[0].text


def test_the_subtraction_runs_the_right_way_round() -> None:
    """A stored chunk without a vector is NOT an orphan, and a vector without a stored chunk is NOT a missing vector."""
    a = doc("S1", 2)
    missing_one = vectors_for(a, skip=[a.chunk_ids[0]])
    rep = run(facts(a), FakeIndex(missing_one))
    assert codes(rep) == ["answerable_missing_vectors"] and rep.pine.orphans == []
    extra = vectors_for(a)
    extra[cid()] = {}
    rep = run(facts(a), FakeIndex(extra))
    assert "answerable_missing_vectors" not in codes(rep) and len(rep.pine.orphans) == 1


@pytest.mark.parametrize("shape", ["lists", "objects"])
@pytest.mark.parametrize("page", [1, 7, 100, 1000])
def test_listing_follows_every_page_in_both_sdk_shapes(shape: str, page: int) -> None:
    a = doc("S1", 5)
    v = vectors_for(a)
    for _ in range(23):
        v[cid()] = {"document_id": "x", "title": "T"}
    rep = run(facts(a), FakeIndex(v, page_size=page, list_shape=shape))
    assert rep.pine.listed == 28 and len(rep.pine.orphans) == 23 and rep.pine.list_state == "ok"


def test_orphan_titles_are_read_for_at_most_the_detail_limit_and_the_rest_are_still_counted(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(vr, "ORPHAN_DETAIL_LIMIT", 120)
    a = doc("S1", 1)
    v = vectors_for(a)
    for _ in range(130):
        v[cid()] = {"document_id": "x", "title": "Far Away Policy"}
    idx = FakeIndex(v)
    rep = run(facts(a), idx)
    assert len(rep.pine.orphans) == 130 and rep.pine.orphan_detail_read == 120
    assert "first 120 only" in rep.findings[0].text
    assert sum(1 for o in rep.pine.orphans if o.title) == 120


def test_listing_that_hits_the_limit_says_the_check_is_incomplete(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(vr, "LIST_LIMIT", 10)
    a = doc("S1", 2)
    v = vectors_for(a)
    for _ in range(40):
        v[cid()] = {}
    rep = run(facts(a), FakeIndex(v, page_size=4))
    assert rep.pine.list_state == "truncated" and "list_truncated" in codes(rep)


# ------------------------------------------------------------------------------------------------ pod-based fallback
def test_when_listing_is_unsupported_the_orphan_check_says_unavailable_not_none_found() -> None:
    a = doc("S1", 2)
    rep = run(facts(a), FakeIndex(vectors_for(a), list_supported=False))
    assert rep.pine.list_state == "unavailable" and rep.pine.orphans == []
    assert "orphan_check_unavailable" in codes(rep)
    text = vr.render(rep)
    assert "could not be listed" in rep.headline and "0 vectors in the index are not accounted" not in rep.headline
    assert "serverless" in text


def test_the_fallback_shows_a_count_surplus_labelled_as_a_count() -> None:
    a = doc("S1", 2)
    v = vectors_for(a)
    for _ in range(4):
        v[cid()] = {}
    rep = run(facts(a), FakeIndex(v, list_supported=False))
    f = next(f for f in rep.findings if f.code == "count_surplus")
    assert "4 more vectors" in f.text and "a count, not a list" in f.text and f.severity == vr.NOTE


def test_no_surplus_no_count_note() -> None:
    a = doc("S1", 2)
    rep = run(facts(a), FakeIndex(vectors_for(a), list_supported=False))
    assert "count_surplus" not in codes(rep)


def test_unsupported_listing_still_runs_check_a() -> None:
    a = doc("S1", 3)
    rep = run(facts(a), FakeIndex(vectors_for(a, skip=[a.chunk_ids[2]]), list_supported=False))
    assert "answerable_missing_vectors" in codes(rep, vr.URGENT)


# ------------------------------------------------------------------------------------------------ C: non-answerable documents with vectors
def test_a_document_that_cannot_answer_but_holds_vectors_is_a_note_that_names_the_purge_step() -> None:
    a, b = doc("S1", 2), doc("S2", 3, answerable=False)
    rep = run(facts(a, b), FakeIndex(vectors_for(a, b)))
    assert codes(rep) == ["vectors_on_document_that_cannot_answer"]
    f = rep.findings[0]
    assert f.severity == vr.NOTE and f.subject == "S2" and "3 of its vectors" in f.text and "--purge-vectors" in f.todo


def test_answerable_documents_with_vectors_get_no_such_note() -> None:
    a = doc("S1", 2)
    assert run(facts(a), FakeIndex(vectors_for(a))).findings == []


# ------------------------------------------------------------------------------------------------ D: metadata agreement
def test_a_vector_that_records_another_document_is_a_warning() -> None:
    a, b = doc("S1", 2), doc("S2", 2)
    v = vectors_for(a, b)
    v[a.chunk_ids[0]]["document_id"] = b.document_id
    rep = run(facts(a, b), FakeIndex(v))
    assert codes(rep, vr.WARN) == ["metadata_mismatch"] and rep.findings[0].subject == "S1"


def test_a_vector_with_no_recorded_document_counts_as_a_mismatch() -> None:
    a = doc("S1", 1)
    rep = run(facts(a), FakeIndex({a.chunk_ids[0]: {}}))
    assert codes(rep, vr.WARN) == ["metadata_mismatch"]


def test_a_mismatch_is_not_also_a_missing_vector() -> None:
    a = doc("S1", 1)
    rep = run(facts(a), FakeIndex({a.chunk_ids[0]: {"document_id": "other"}}))
    assert rep.rows[0].found == 1 and rep.rows[0].missing == [] and "answerable_missing_vectors" not in codes(rep)


# ------------------------------------------------------------------------------------------------ E: namespaces
def test_other_namespaces_are_reported_and_never_read() -> None:
    a = doc("S1", 2)
    idx = FakeIndex(vectors_for(a), namespaces={"": 2, "scratch": 40})
    rep = run(facts(a), idx)
    text = vr.render(rep)
    assert rep.pine.other_namespaces == {"scratch": 40} and "scratch" in text and "does not query it" in text
    assert rep.pine.default_count == 2


@pytest.mark.parametrize("stats,expected", [
    (SimpleNamespace(total_vector_count=7, namespaces={}), (7, {})),
    (SimpleNamespace(total_vector_count=7, namespaces={"": SimpleNamespace(vector_count=7)}), (7, {})),
    (SimpleNamespace(total_vector_count=9, namespaces={"__default__": {"vector_count": 4}, "x": {"vector_count": 5}}), (4, {"x": 5})),
    (SimpleNamespace(total_vector_count=5, namespaces={"x": SimpleNamespace(vector_count=5)}), (0, {"x": 5})),
    ({"total_vector_count": 3, "namespaces": {}}, (3, {})),
    (SimpleNamespace(), (None, {})),
])
def test_namespace_counts_shapes(stats: Any, expected: Any) -> None:
    assert vr.namespace_counts(stats) == expected


# ------------------------------------------------------------------------------------------------ could not look
def test_a_failed_pinecone_call_is_not_a_clean_report_and_prints_none_of_the_error() -> None:
    a = doc("S1", 2)
    for name in ("describe_index_stats", "fetch"):
        idx = FakeIndex(vectors_for(a), fail_on=name)
        rep = run(facts(a), idx)
        text = vr.render(rep)
        assert rep.pine.state == "unreachable" and rep.findings == []
        assert "could not be read" in rep.headline and "NOTHING TO FIX" not in text
        assert "sk-secret" not in text and "h.example" not in text and "boom" not in text


def test_a_rejected_key_gets_the_fixed_sentence() -> None:
    class Rejected(Exception):
        status_code = 401

    rep = run(facts(doc("S1", 1)), FakeIndex({}, fail_on="describe_index_stats", fail_with=Rejected("Unauthorized: sk-live-123")))
    text = vr.render(rep)
    assert "refused the key" in text and "sk-live-123" not in text


def test_a_failed_list_is_a_degraded_result_not_a_failed_report() -> None:
    a = doc("S1", 2)
    rep = run(facts(a), FakeIndex(vectors_for(a), fail_on="list"))
    assert rep.pine.state == "checked" and rep.pine.list_state == "unavailable"


def test_a_failed_metadata_fetch_for_orphans_keeps_the_ids(monkeypatch: pytest.MonkeyPatch) -> None:
    a = doc("S1", 1)
    v = vectors_for(a)
    v[cid()] = {"document_id": "x", "title": "T"}
    idx = FakeIndex(v)
    real = idx.fetch
    state = {"n": 0}

    def flaky(**k: Any) -> Any:
        state["n"] += 1
        if state["n"] > 1:
            raise RuntimeError("second fetch fails")
        return real(**k)

    idx.fetch = flaky  # type: ignore[method-assign]
    rep = run(facts(a), idx)
    assert len(rep.pine.orphans) == 1 and rep.pine.orphans[0].title == "" and rep.pine.state == "checked"


def test_a_call_that_never_returns_times_out_instead_of_hanging(monkeypatch: pytest.MonkeyPatch) -> None:
    import threading

    monkeypatch.setattr(vr, "CALL_TIMEOUT_SECONDS", 0.2)
    gate = threading.Event()
    idx = FakeIndex({})
    idx.describe_index_stats = lambda: gate.wait(5)  # type: ignore[method-assign]
    rep = run(facts(doc("S1", 1)), idx)
    gate.set()
    assert rep.pine.state == "unreachable" and rep.pine.error_kind == "timeout"


def test_when_the_database_cannot_be_read_nothing_is_compared_and_pinecone_is_not_asked() -> None:
    db = vr.DbFacts(state="unreachable", error_kind="cannot_connect")
    rep = vr.build_report(db, vr.PineFacts())
    text = vr.render(rep)
    assert "could not be reached" in rep.headline and rep.findings == [] and "NOTHING TO FIX" not in text


def test_without_a_pinecone_key_the_report_says_pinecone_was_not_asked() -> None:
    rep = vr.build_report(facts(doc("S1", 2)), vr.PineFacts(state="no_key"))
    text = vr.render(rep)
    assert "no Pinecone key is set" in rep.headline and "not asked" in text and "NOTHING TO FIX" not in text


# ------------------------------------------------------------------------------------------------ read-only guarantees
@pytest.mark.parametrize("name", ["upsert", "delete", "update", "query", "fetch_by_metadata", "create_namespace", "start_import", "describe_namespace"])
def test_the_read_only_handle_refuses_everything_but_three_reads(name: str) -> None:
    idx = vr.ReadOnlyIndex(FakeIndex({}))
    with pytest.raises(PermissionError):
        getattr(idx, name)
    with pytest.raises(PermissionError):
        idx.anything = 1  # type: ignore[attr-defined]


def test_the_three_reads_pass_through() -> None:
    idx = vr.ReadOnlyIndex(FakeIndex({"a": {}}))
    assert idx.describe_index_stats().total_vector_count == 1
    assert list(idx.fetch(ids=["a"]).vectors) == ["a"]
    assert len(list(idx.list())) == 1


def test_a_full_run_makes_only_read_calls_and_never_a_write() -> None:
    a = doc("S1", 3)
    v = vectors_for(a)
    v[cid()] = {"document_id": "x", "title": "T"}
    idx = FakeIndex(v)
    run(facts(a), idx)
    assert set(idx.calls) <= {"describe_index_stats", "fetch", "list"} and idx.calls


def test_source_names_no_write_or_query_call_and_no_embedding_or_openai() -> None:
    src = (ORCH / "ask_bpl_orchestrator" / "vector_report.py").read_text()
    code = re.sub(r'"""(.*?)"""', "", src, flags=re.S)
    code = "\n".join(line for line in code.splitlines() if not line.lstrip().startswith("#"))
    assert not re.search(r"\.(upsert|delete|update|query|delete_all|start_import|set_metadata)\(", code)
    assert not re.search(r"\b(embed_query|embed_snippet|OpenAI|openai|anthropic)\b", code)
    assert not re.search(r"\b(INSERT INTO|DELETE FROM|UPDATE \w+ SET|DROP TABLE|ALTER TABLE|TRUNCATE)\b", code)
    assert ".commit(" not in code and "session.add(" not in code and "async_session_factory" not in code
    assert "str(exc)" not in code and "{exc}" not in code and "repr(exc)" not in code


def test_main_hands_pinecone_only_the_wrapped_index(monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    seen: List[Any] = []
    a = doc("S1", 1)

    async def fake_db(*_a: Any, **_k: Any) -> vr.DbFacts:
        return facts(a)

    real = vr.gather_pinecone_facts

    def spy(index: Any, db: vr.DbFacts) -> vr.PineFacts:
        seen.append(index)
        return real(index, db)

    monkeypatch.setattr(vr, "gather_db_facts", fake_db)
    monkeypatch.setattr(vr, "gather_pinecone_facts", spy)
    monkeypatch.setattr("ask_bpl_orchestrator.services.pinecone_client.get_pinecone_index", lambda: FakeIndex(vectors_for(a)))
    monkeypatch.setenv("PINECONE_API_KEY", "pcsk_test_value_1234567890")
    get_settings.cache_clear()
    try:
        assert vr.main([]) == 0
    finally:
        get_settings.cache_clear()
    assert len(seen) == 1 and isinstance(seen[0], vr.ReadOnlyIndex)
    capsys.readouterr()


# ------------------------------------------------------------------------------------------------ command line
def _patch_main(monkeypatch: pytest.MonkeyPatch, db: vr.DbFacts, index: Optional[FakeIndex], key: str = "pcsk_test_value_1234567890") -> None:
    async def fake_db(*_a: Any, **_k: Any) -> vr.DbFacts:
        return db

    monkeypatch.setattr(vr, "gather_db_facts", fake_db)
    monkeypatch.setenv("PINECONE_API_KEY", key)
    get_settings.cache_clear()
    if index is None:
        def boom() -> Any:
            raise RuntimeError("cannot build index sk-secret-KEY")
        monkeypatch.setattr("ask_bpl_orchestrator.services.pinecone_client.get_pinecone_index", boom)
    else:
        monkeypatch.setattr("ask_bpl_orchestrator.services.pinecone_client.get_pinecone_index", lambda: index)


@pytest.fixture(autouse=True)
def _reset_settings() -> Any:
    yield
    get_settings.cache_clear()


def test_exit_codes(monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    a = doc("S1", 2)
    _patch_main(monkeypatch, facts(a), FakeIndex(vectors_for(a)))
    assert vr.main(["--strict"]) == 0
    _patch_main(monkeypatch, facts(a), FakeIndex(vectors_for(a, skip=[a.chunk_ids[0]])))
    assert vr.main([]) == 0           # findings are not errors...
    assert vr.main(["--strict"]) == 1  # ...unless --strict
    out = capsys.readouterr().out
    assert "URGENT (1)" in out


def test_strict_fails_on_a_warning_but_not_on_a_note(monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    a = doc("S1", 1)
    other = vectors_for(a)
    other[cid()] = {"document_id": "elsewhere", "title": "T"}
    _patch_main(monkeypatch, facts(a), FakeIndex(other))
    assert vr.main(["--strict"]) == 0   # a note only
    stale = vectors_for(a)
    stale[cid()] = {"document_id": a.document_id, "title": a.title}
    _patch_main(monkeypatch, facts(a), FakeIndex(stale))
    assert vr.main(["--strict"]) == 1
    capsys.readouterr()


def test_strict_fails_when_either_side_could_not_be_read(monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    a = doc("S1", 1)
    _patch_main(monkeypatch, vr.DbFacts(state="unreachable", error_kind="cannot_connect"), FakeIndex({}))
    assert vr.main([]) == 0 and vr.main(["--strict"]) == 1
    _patch_main(monkeypatch, facts(a), FakeIndex({}, fail_on="describe_index_stats"))
    assert vr.main([]) == 0 and vr.main(["--strict"]) == 1
    _patch_main(monkeypatch, facts(a), None)
    assert vr.main(["--strict"]) == 1
    out = capsys.readouterr().out
    assert "sk-secret" not in out and "cannot build index" not in out


def test_without_a_key_nothing_is_called_and_strict_fails(monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    called: List[int] = []
    _patch_main(monkeypatch, facts(doc("S1", 1)), FakeIndex({}), key="")
    monkeypatch.setattr("ask_bpl_orchestrator.services.pinecone_client.get_pinecone_index", lambda: called.append(1))
    assert vr.main([]) == 0 and vr.main(["--strict"]) == 1 and called == []
    assert "not set" in capsys.readouterr().out


def test_csv_is_the_only_file_written_and_neutralises_formulas(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    monkeypatch.chdir(tmp_path)
    a = doc("=S1", 1)
    a.title = "+Evil Title"
    v = vectors_for(a)
    v[cid()] = {"document_id": "elsewhere", "title": "@Bad"}
    _patch_main(monkeypatch, facts(a), FakeIndex(v))
    before = set(tmp_path.iterdir())
    assert vr.main([]) == 0 and set(tmp_path.iterdir()) == before          # no file without --csv
    assert vr.main(["--csv", str(tmp_path / "o.csv")]) == 0
    assert set(tmp_path.iterdir()) - before == {tmp_path / "o.csv"}
    rows = list(csv.reader((tmp_path / "o.csv").open()))
    assert rows[0][0] == "row_type" and rows[1][0] == "document" and rows[1][1] == "'=S1" and rows[1][8] == "'+Evil Title"
    assert rows[2][0] == "orphan_vector" and rows[2][8] == "'@Bad"
    capsys.readouterr()


def test_the_report_never_prints_the_database_password(monkeypatch: pytest.MonkeyPatch) -> None:
    pw = "ZZTOPdbpass9999"
    s = Settings(_env_file=None, database_url=f"postgresql+asyncpg://askbpl:{pw}@127.0.0.1:1/none", jwt_secret_key="x" * 40,
                 openai_api_key="a", anthropic_api_key="b", pinecone_api_key="c", pinecone_index_name="i")
    db = asyncio.run(vr.gather_db_facts(s, None))
    text = vr.render(vr.build_report(db, vr.PineFacts()))
    assert db.state == "unreachable" and db.docs == []
    assert pw not in text and "ZZTOP" not in text and "askbpl:" not in text and "could not be reached" in text


def test_command_is_registered() -> None:
    assert 'askbpl-vector-report = "ask_bpl_orchestrator.vector_report:main"' in (ORCH / "pyproject.toml").read_text()


def test_the_report_always_says_what_it_cannot_tell_you() -> None:
    for rep in (run(facts(doc("S1", 1)), FakeIndex({})), vr.build_report(vr.DbFacts(state="unreachable"), vr.PineFacts())):
        text = vr.render(rep, summary_only=True)
        assert "WHAT THIS REPORT CANNOT TELL YOU" in text and "does not confirm that a vector encodes the right text" in text
        assert "not an approval" not in text and "approved" not in text.replace("BPL has approved it", "")


# ------------------------------------------------------------------------------------------------ database (real Postgres, scoped)
def _pinned() -> Settings:
    return get_settings()


async def _make_docs(specs: List[Dict[str, Any]]) -> List[uuid.UUID]:
    ids: List[uuid.UUID] = []
    async with async_session_factory() as s:
        for sp in specs:
            did = sp.get("id") or uuid.uuid4()
            s.add(Document(
                document_id=did, title="t", version="t", policy_type="generic_policy", source_format=SourceFormat.md,
                ingest_status=sp.get("status", IngestStatus.indexed), eligibility=sp.get("elig", Eligibility.authority_pending),
                test_index_member=sp.get("member", True), source_path=sp["path"], source_id=sp.get("sid"),
                superseded_by_document_id=sp.get("sup"), extraction_status=sp.get("extraction", ExtractionStatus.standard),
                # An eligible document is approved for its stored file unless a test says otherwise (patch 0023).
                source_sha256=sp.get("file_hash", "a" * 64 if sp.get("elig") == Eligibility.eligible else None),
                approved_sha256=sp.get("approved_hash", "a" * 64 if sp.get("elig") == Eligibility.eligible else None),
            ))
            ids.append(did)
            await s.flush()
        for sp, did in zip(specs, ids):
            for i in range(sp.get("chunks", 1)):
                s.add(Chunk(chunk_id=uuid.uuid4(), document_id=did, ordinal=i, text="Staff must record gifts.", token_count=4))
        await s.commit()
    return ids


async def _cleanup(ids: List[uuid.UUID]) -> None:
    async with async_session_factory() as s:
        await s.execute(delete(Chunk).where(Chunk.document_id.in_(ids)))
        await s.execute(delete(Document).where(Document.document_id.in_(ids)))
        await s.commit()


def _gather(ids: List[uuid.UUID], settings: Optional[Settings] = None) -> vr.DbFacts:
    return asyncio.run(vr.gather_db_facts(settings or _pinned(), vr.alembic_head(), scope=ids))


def test_the_database_side_returns_each_documents_real_chunk_ids() -> None:
    t = uuid.uuid4().hex[:8]
    ids = asyncio.run(_make_docs([dict(path=f"zz{t}-a.pdf", chunks=3, sid=f"T{t}-a"), dict(path=f"zz{t}-b.pdf", chunks=0)]))
    try:
        db = _gather(ids)
        assert db.checked and len(db.docs) == 2
        by_path = {d.source_path: d for d in db.docs}
        assert len(by_path[f"zz{t}-a.pdf"].chunk_ids) == 3 and by_path[f"zz{t}-b.pdf"].chunk_ids == []

        async def real_ids() -> set[str]:
            async with async_session_factory() as s:
                return {str(c) for c in (await s.execute(select(Chunk.chunk_id).where(Chunk.document_id.in_(ids)))).scalars().all()}

        assert {c for d in db.docs for c in d.chunk_ids} == asyncio.run(real_ids())
        assert by_path[f"zz{t}-a.pdf"].source_id == f"T{t}-a"
    finally:
        asyncio.run(_cleanup(ids))


def test_end_to_end_against_the_real_database_finds_the_missing_vector_and_the_stale_one() -> None:
    t = uuid.uuid4().hex[:8]
    ids = asyncio.run(_make_docs([dict(path=f"zz{t}-a.pdf", chunks=3), dict(path=f"zz{t}-b.pdf", chunks=2, member=False)]))
    try:
        db = _gather(ids)
        a = next(d for d in db.docs if d.source_path == f"zz{t}-a.pdf")
        b = next(d for d in db.docs if d.source_path == f"zz{t}-b.pdf")
        v = vectors_for(a, b, skip=[a.chunk_ids[0]])
        v[cid()] = {"document_id": a.document_id, "title": "t"}
        rep = run(db, FakeIndex(v))
        assert a.answerable and not b.answerable
        assert codes(rep, vr.URGENT) == ["answerable_missing_vectors"] and rep.findings[0].subject == f"zz{t}-a.pdf"
        assert "stale_vectors_for_stored_document" in codes(rep) and "vectors_on_document_that_cannot_answer" in codes(rep)
    finally:
        asyncio.run(_cleanup(ids))


@pytest.mark.parametrize("elig", list(Eligibility))
@pytest.mark.parametrize("member", [False, True])
@pytest.mark.parametrize("extraction", [ExtractionStatus.standard, ExtractionStatus.validated, ExtractionStatus.review_required])
@pytest.mark.parametrize("status", [IngestStatus.indexed, IngestStatus.failed])
@pytest.mark.parametrize("superseded", [False, True])
def test_answerable_agrees_with_the_corpus_report_for_every_combination(elig, member, extraction, status, superseded) -> None:
    """URGENT must fire for exactly the documents the corpus report calls answerable. If these drift, one report lies."""
    t = uuid.uuid4().hex[:8]
    successor = uuid.uuid4()
    specs = [dict(id=successor, path=f"zz{t}-s.pdf", member=False)] if superseded else []
    specs.append(dict(path=f"zz{t}-m.pdf", elig=elig, member=member, extraction=extraction, status=status, sup=successor if superseded else None))
    ids = asyncio.run(_make_docs(specs))
    try:
        mine = next(d for d in _gather(ids).docs if d.source_path == f"zz{t}-m.pdf")
        theirs = next(d for d in asyncio.run(cr.gather_corpus_facts(_pinned(), cr.alembic_head(), scope=ids)).docs if d.source_path == f"zz{t}-m.pdf")
        assert mine.answerable == theirs.answerable
    finally:
        asyncio.run(_cleanup(ids))


def test_the_database_connection_is_declared_read_only_and_issues_no_write(monkeypatch: pytest.MonkeyPatch) -> None:
    import sqlalchemy.ext.asyncio as sa_asyncio
    from sqlalchemy import event

    seen: List[str] = []
    real = sa_asyncio.create_async_engine

    def spying(*a: Any, **k: Any):
        eng = real(*a, **k)

        @event.listens_for(eng.sync_engine, "before_cursor_execute")
        def _rec(_c, _cur, statement, *_rest) -> None:  # noqa: ANN001
            seen.append(statement.strip())

        return eng

    monkeypatch.setattr(sa_asyncio, "create_async_engine", spying)
    db = asyncio.run(vr.gather_db_facts(_pinned(), vr.alembic_head(), scope=[uuid.uuid4()]))
    assert db.checked and seen and seen[0].upper().startswith("SET TRANSACTION READ ONLY")
    for stmt in seen:
        assert not re.match(r"(?is)\s*(insert|update|delete|alter|drop|create|truncate|grant)\b", stmt), stmt


def test_gathering_changes_no_rows() -> None:
    async def counts() -> tuple[int, int]:
        async with async_session_factory() as s:
            return ((await s.execute(select(func.count()).select_from(Document))).scalar_one(),
                    (await s.execute(select(func.count()).select_from(Chunk))).scalar_one())

    before = asyncio.run(counts())
    assert asyncio.run(vr.gather_db_facts(_pinned(), vr.alembic_head())).checked
    assert asyncio.run(counts()) == before


def test_an_out_of_date_database_is_reported_not_queried() -> None:
    db = asyncio.run(vr.gather_db_facts(_pinned(), "not-the-real-head"))
    assert db.state == "out_of_date" and db.docs == [] and "older than this code" in vr.render(vr.build_report(db, vr.PineFacts()))

