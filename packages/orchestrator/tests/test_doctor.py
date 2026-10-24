"""Patch 0019: `askbpl-doctor` and docs/TESTER_SETUP.md (PRD INT-1, NFR-3, NFR-8, SAF-5).

What these tests protect:
  * no secret ever reaches the screen: not a key, not a database password, and not the text of an error raised by an
    outside service (those messages can echo a partly masked key);
  * the doctor is read-only: its database connection is declared READ ONLY and it issues no write statement;
  * without --live it contacts no outside service, and a service whose key is unset is never called;
  * every problem it can report says what to do, and a problem that blocks testing makes the exit code non-zero;
  * the setup guide names only commands that exist.

No network. The outside services are faked; the database checks use the test Postgres the suite already needs.
"""

from __future__ import annotations

import asyncio
import re
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine

from ask_bpl_orchestrator import doctor as dr
from ask_bpl_orchestrator.config import Settings
from ask_bpl_orchestrator.db.models import Document, Tester
from ask_bpl_orchestrator.db.session import async_session_factory

_REAL_RUN_CHECKS = dr.run_checks  # captured before any test patches it
ORCH = Path(__file__).resolve().parents[1]
REPO = ORCH.parents[1]

# Distinctive, key-shaped values. If any fragment of these appears in output, a safeguard is broken.
OPENAI = "sk-proj-ZZTOPSECRETOPENAI0123456789"
ANTHROPIC = "sk-ant-api03-ZZTOPSECRETANTHROPIC9876"
PINECONE = "pcsk_ZZTOPSECRETPINECONE55555"
JWT = "jwt-ZZTOPSECRETJWTVALUE-abcdefghijklmnop"
ADMIN = "adminZZTOPSECRETpassword"
DBPASS = "dbZZTOPSECRETpass"
SECRETS = [OPENAI, ANTHROPIC, PINECONE, JWT, ADMIN, DBPASS]


def make_settings(**over: Any) -> Settings:
    base = dict(
        database_url=f"postgresql+asyncpg://askbpl:{DBPASS}@localhost:5434/askbpl",
        jwt_secret_key=JWT,
        openai_api_key=OPENAI,
        anthropic_api_key=ANTHROPIC,
        pinecone_api_key=PINECONE,
        pinecone_index_name="askbpl-pilot",
        admin_basic_password=ADMIN,
        allow_test_index=True,
        cors_origins="http://localhost:5173",
    )
    base.update(over)
    return Settings(_env_file=None, **base)


def good_facts(**over: Any) -> dr.DbFacts:
    f = dr.DbFacts(
        reachable=True,
        current_revision="006_chunk_pages",
        head_revision="006_chunk_pages",
        head_known=True,
        demo_tester=True,
        answerable_titles=["Annual Leave Policy", "Technology Use Policy"],
        docs_total=8,
        docs_not_answerable=6,
        chunks=120,
        approved_glossary_entries=0,
    )
    for k, v in over.items():
        setattr(f, k, v)
    return f


def web_dir(tmp_path: Path, *, env_local: str | None = "VITE_API_BASE_URL=http://localhost:8000\n", modules: bool = True) -> Path:
    import shutil

    w = tmp_path / "web-demo"
    w.mkdir(parents=True, exist_ok=True)
    (w / ".env.local").unlink(missing_ok=True)
    shutil.rmtree(w / "node_modules", ignore_errors=True)
    if env_local is not None:
        (w / ".env.local").write_text(env_local)
    if modules:
        (w / "node_modules").mkdir()
    return w


def run(settings: Settings, tmp_path: Path, **kw: Any) -> dr.Report:
    return _run_real(settings, tmp_path, **kw)


def _run_real(settings: Settings, tmp_path: Path, **kw: Any) -> dr.Report:
    kw.setdefault("db_facts", good_facts())
    kw.setdefault("which", lambda _n: "/usr/bin/node")
    if "web_dir" not in kw:
        kw["web_dir"] = web_dir(tmp_path)
    kw.setdefault("cwd", tmp_path)
    return _REAL_RUN_CHECKS(settings, **kw)


def status_of(report: dr.Report, key: str) -> str:
    return next(c.status for c in report.checks if c.key == key)


def assert_no_secret(text: str) -> None:
    for s in SECRETS:
        assert s not in text, "a secret value reached the output"
        assert s[:10] not in text, "the start of a secret reached the output"
    assert "ZZTOP" not in text


# ------------------------------------------------------------------------------------------ secrets never printed
def test_full_report_never_contains_a_secret(tmp_path: Path) -> None:
    settings = make_settings()
    (tmp_path / ".env").write_text("x=1")
    report = run(settings, tmp_path)
    assert_no_secret(dr.render(report, settings))


def test_no_check_holds_a_secret_before_rendering(tmp_path: Path) -> None:
    """Each layer must be clean on its own: the final scrub in render() is only a last line of defence."""
    report = run(make_settings(), tmp_path)
    for c in report.checks:
        assert_no_secret(f"{c.title}\n{c.detail}\n{c.todo}")


def test_probe_error_text_is_dropped_before_it_reaches_any_check(tmp_path: Path) -> None:
    leaky = f"401 Incorrect API key provided: {OPENAI}"

    async def bad(_s: Settings) -> dict[str, Any]:
        return {"status": "error", "detail": leaky}

    r = run(make_settings(), tmp_path, live=True, probes={"openai": bad, "anthropic": bad, "pinecone": bad})
    for c in r.checks:
        assert_no_secret(f"{c.title}\n{c.detail}\n{c.todo}")
        assert "Incorrect API key" not in f"{c.title}{c.detail}{c.todo}"
    res = asyncio.run(dr._run_probe(bad, make_settings()))
    assert "detail" not in res or res["detail"] == "index_empty"
    assert OPENAI not in repr(res)


def test_render_scrubs_a_secret_that_somehow_reached_a_check() -> None:
    """Last line of defence: even a careless future check cannot print a configured secret."""
    settings = make_settings()
    rep = dr.Report()
    rep.add("x", dr.FIX, f"oops {OPENAI}", f"also {PINECONE}", f"and postgresql://u:{DBPASS}@h/db")
    assert_no_secret(dr.render(rep, settings))


def test_database_address_is_shown_without_user_or_password() -> None:
    shown = dr.describe_database_target(f"postgresql+asyncpg://askbpl:{DBPASS}@db.example:5434/askbpl")
    assert shown == "db.example:5434/askbpl"
    assert "askbpl:" not in shown and DBPASS not in shown


def test_scrub_removes_configured_secrets_and_key_shapes_and_url_passwords() -> None:
    settings = make_settings()
    dirty = f"x {OPENAI} y {PINECONE} z postgresql://u:{DBPASS}@h/db and sk-live-abcdef123456 {ADMIN}"
    clean = dr.scrub(dirty, settings)
    assert_no_secret(clean)
    assert "sk-live-abcdef123456" not in clean
    assert "[hidden]" in clean


def test_error_text_from_outside_services_is_never_printed(tmp_path: Path) -> None:
    """The real OpenAI 401 message echoes a masked key; Pinecone and Anthropic can echo parts of one too."""
    leaky = f"Error code: 401 - Incorrect API key provided: {OPENAI[:12]}***{OPENAI[-4:]}. Full: {OPENAI}"

    async def bad(_s: Settings) -> dict[str, Any]:
        return {"status": "error", "detail": leaky}

    async def boom(_s: Settings) -> dict[str, Any]:
        raise RuntimeError(leaky)

    settings = make_settings()
    report = run(settings, tmp_path, live=True, probes={"openai": bad, "anthropic": boom, "pinecone": bad})
    out = dr.render(report, settings)
    assert_no_secret(out)
    assert "Incorrect API key" not in out
    assert "Error code" not in out
    # but the person is still told what happened, in fixed words
    assert status_of(report, "live:openai") == dr.FIX
    assert "refused the key" in out


def test_database_error_text_is_never_printed(tmp_path: Path) -> None:
    settings = make_settings()
    facts = dr.DbFacts(reachable=False, error_kind="cannot_connect")
    out = dr.render(run(settings, tmp_path, db_facts=facts), settings)
    assert_no_secret(out)
    assert "localhost:5434/askbpl" in out


# ------------------------------------------------------------------------------------------ settings checks
@pytest.mark.parametrize(
    "attr,name",
    [
        ("jwt_secret_key", "JWT_SECRET_KEY"),
        ("openai_api_key", "OPENAI_API_KEY"),
        ("anthropic_api_key", "ANTHROPIC_API_KEY"),
        ("pinecone_api_key", "PINECONE_API_KEY"),
    ],
)
def test_each_missing_key_is_a_fix_that_names_the_variable(tmp_path: Path, attr: str, name: str) -> None:
    report = run(make_settings(**{attr: "  "}), tmp_path)
    assert status_of(report, f"secret:{name}") == dr.FIX
    c = next(c for c in report.checks if c.key == f"secret:{name}")
    assert name in c.title and name in c.todo
    assert report.blockers >= 1


@pytest.mark.parametrize("bad", ['"sk-abc1234567890"', "'sk-abc1234567890'", "your-key-here", "changeme", "<paste key>"])
def test_placeholders_and_quoted_values_are_a_fix_without_echoing_them(tmp_path: Path, bad: str) -> None:
    settings = make_settings(openai_api_key=bad)
    report = run(settings, tmp_path)
    assert status_of(report, "secret:OPENAI_API_KEY") == dr.FIX
    assert bad not in dr.render(report, settings)


def test_all_keys_set_gives_ok_and_no_blockers(tmp_path: Path) -> None:
    report = run(make_settings(), tmp_path)
    assert report.blockers == 0
    assert all(status_of(report, f"secret:{n}") == dr.OK for n in dr.SERVICE_NAME)


def test_test_mode_off_is_flagged_and_outside_services_notice_always_present(tmp_path: Path) -> None:
    on = run(make_settings(), tmp_path)
    off = run(make_settings(allow_test_index=False), tmp_path)
    assert status_of(on, "test_index") == dr.INFO
    assert status_of(off, "test_index") == dr.WARN
    for r in (on, off):
        c = next(c for c in r.checks if c.key == "outside_services")
        assert "not yet answered" in c.detail and "SAF-5" in c.detail


def test_missing_settings_file_is_a_warning_not_a_blocker(tmp_path: Path) -> None:
    report = run(make_settings(), tmp_path)  # no .env written
    assert status_of(report, "env_file") == dr.WARN
    assert report.blockers == 0


# ------------------------------------------------------------------------------------------ database checks
def test_database_unreachable_is_a_fix_with_docker_instruction(tmp_path: Path) -> None:
    report = run(make_settings(), tmp_path, db_facts=dr.DbFacts(reachable=False, error_kind="cannot_connect"))
    c = next(c for c in report.checks if c.key == "db_reachable")
    assert c.status == dr.FIX and "docker compose" in c.todo and "probably not started" in c.detail
    assert not any(c.key in ("db_migrated", "demo_tester", "answerable_docs") for c in report.checks)


def test_empty_database_out_of_date_database_and_missing_tester_each_say_the_command(tmp_path: Path) -> None:
    s = make_settings()
    empty = run(s, tmp_path, db_facts=good_facts(current_revision=None))
    assert status_of(empty, "db_migrated") == dr.FIX
    assert "alembic upgrade head" in next(c for c in empty.checks if c.key == "db_migrated").todo
    old = run(s, tmp_path, db_facts=good_facts(current_revision="004_document_eligibility"))
    c = next(c for c in old.checks if c.key == "db_migrated")
    assert c.status == dr.FIX and "004_document_eligibility" in c.detail
    no_tester = run(s, tmp_path, db_facts=good_facts(demo_tester=False))
    assert status_of(no_tester, "demo_tester") == dr.FIX
    assert "askbpl-seed" in next(c for c in no_tester.checks if c.key == "demo_tester").todo


def test_no_answerable_documents_is_a_blocker_and_names_what_is_available(tmp_path: Path) -> None:
    s = make_settings()
    none = run(s, tmp_path, db_facts=good_facts(answerable_titles=[], docs_total=8))
    assert status_of(none, "answerable_docs") == dr.FIX
    ok = run(s, tmp_path, db_facts=good_facts())
    c = next(c for c in ok.checks if c.key == "answerable_docs")
    assert c.status == dr.OK and "2 policy documents" in c.title and "of the 88" in c.title
    assert "None of these is confirmed current by BPL" in c.detail


def test_empty_glossary_is_expected_not_a_problem(tmp_path: Path) -> None:
    report = run(make_settings(), tmp_path)
    assert status_of(report, "glossary") == dr.INFO


# ------------------------------------------------------------------------------------------ web demo checks
def test_web_demo_in_pretend_mode_is_a_blocker(tmp_path: Path) -> None:
    w = web_dir(tmp_path, env_local="VITE_API_BASE_URL=http://localhost:8000\nVITE_MOCK_ASK=true\n")
    report = run(make_settings(), tmp_path, web_dir=w)
    c = next(c for c in report.checks if c.key == "web_mock")
    assert c.status == dr.FIX and "canned answers" in c.detail


def test_web_demo_missing_settings_modules_node_and_api_url(tmp_path: Path) -> None:
    s = make_settings()
    w = web_dir(tmp_path, env_local=None, modules=False)
    r = run(s, tmp_path, web_dir=w, which=lambda _n: None)
    for key in ("web_env", "web_modules", "node"):
        assert status_of(r, key) == dr.FIX, key
    (tmp_path / "w2").mkdir()
    w2 = web_dir(tmp_path / "w2", env_local="VITE_FOO=1\n")
    r2 = run(s, tmp_path, web_dir=w2)
    assert status_of(r2, "web_api") == dr.FIX


def test_access_code_baked_into_web_settings_is_warned_without_echoing_it(tmp_path: Path) -> None:
    w = web_dir(tmp_path, env_local="VITE_API_BASE_URL=http://localhost:8000\nVITE_PILOT_DEMO_ACCESS_CODE=REALCODE9\n")
    s = make_settings()
    r = run(s, tmp_path, web_dir=w)
    assert status_of(r, "web_code") == dr.WARN
    assert "REALCODE9" not in dr.render(r, s)


def test_cors_warning_only_when_page_origin_missing(tmp_path: Path) -> None:
    ok = run(make_settings(cors_origins="http://localhost:5173"), tmp_path)
    assert not any(c.key == "cors" for c in ok.checks)
    bad = run(make_settings(cors_origins="https://example.org"), tmp_path)
    assert status_of(bad, "cors") == dr.WARN


def test_web_folder_not_found_is_only_a_note(tmp_path: Path) -> None:
    r = run(make_settings(), tmp_path, web_dir=tmp_path / "nope")
    assert status_of(r, "web_dir") == dr.INFO


# ------------------------------------------------------------------------------------------ live and server checks
def test_without_live_no_outside_service_is_called(tmp_path: Path) -> None:
    calls: list[str] = []

    async def spy(_s: Settings) -> dict[str, Any]:
        calls.append("called")
        return {"status": "ok"}

    r = run(make_settings(), tmp_path, live=False, probes={"openai": spy, "anthropic": spy, "pinecone": spy})
    assert calls == []
    assert status_of(r, "live_skipped") == dr.INFO


def test_a_service_with_no_key_is_never_called_and_is_reported_as_skipped(tmp_path: Path) -> None:
    calls: list[str] = []

    def probe(name: str):
        async def _p(_s: Settings) -> dict[str, Any]:
            calls.append(name)
            return {"status": "ok", "vectors": 10}

        return _p

    r = run(
        make_settings(openai_api_key=""),
        tmp_path,
        live=True,
        probes={n: probe(n) for n in ("openai", "anthropic", "pinecone")},
    )
    assert "openai" not in calls and sorted(calls) == ["anthropic", "pinecone"]
    assert status_of(r, "live:openai") == dr.SKIP


def test_live_results_ok_empty_index_and_vector_gap(tmp_path: Path) -> None:
    async def ok(_s: Settings) -> dict[str, Any]:
        return {"status": "ok"}

    async def pc(_s: Settings) -> dict[str, Any]:
        return {"status": "ok", "vectors": 40}

    async def empty(_s: Settings) -> dict[str, Any]:
        return {"status": "error", "detail": "index_empty", "vectors": 0}

    s = make_settings()
    good = run(s, tmp_path, live=True, probes={"openai": ok, "anthropic": ok, "pinecone": pc}, db_facts=good_facts(chunks=120))
    assert status_of(good, "live:pinecone") == dr.OK
    assert status_of(good, "live:pinecone_gap") == dr.WARN  # 40 stored, 120 listed
    assert status_of(good, "live:openai") == dr.OK
    none = run(s, tmp_path, live=True, probes={"openai": ok, "anthropic": ok, "pinecone": empty})
    assert status_of(none, "live:pinecone") == dr.FIX
    assert none.blockers >= 1


def test_live_probe_failure_kinds_are_classified_in_fixed_words(tmp_path: Path) -> None:
    async def timeout(_s: Settings) -> dict[str, Any]:
        return {"status": "error", "detail": "Request timed out."}

    async def quota(_s: Settings) -> dict[str, Any]:
        return {"status": "error", "detail": "429 insufficient_quota: You exceeded your current quota"}

    async def ok(_s: Settings) -> dict[str, Any]:
        return {"status": "ok"}

    s = make_settings()
    r = run(s, tmp_path, live=True, probes={"openai": timeout, "anthropic": quota, "pinecone": ok})
    out = dr.render(r, s)
    assert "did not answer in time" in out
    assert "usage limit or billing" in out
    assert "exceeded your current quota" not in out


def test_server_not_running_is_a_note_not_a_blocker_and_not_ready_is_a_blocker(tmp_path: Path) -> None:
    async def down(_url: str) -> int:
        raise ConnectionRefusedError("connection refused")

    async def alive_not_ready(url: str) -> int:
        return 200 if url.endswith("/healthz") else 503

    async def all_good(_url: str) -> int:
        return 200

    s = make_settings()
    r = run(s, tmp_path, url="http://localhost:8000", fetch=down)
    assert status_of(r, "server") == dr.INFO and r.blockers == 0
    r2 = run(s, tmp_path, url="http://localhost:8000", fetch=alive_not_ready)
    assert status_of(r2, "server_ready") == dr.FIX
    r3 = run(s, tmp_path, url="http://localhost:8000", fetch=all_good)
    assert status_of(r3, "server") == dr.OK and status_of(r3, "server_ready") == dr.OK


# ------------------------------------------------------------------------------------------ rendering and exit code
def test_every_fix_and_warning_says_what_to_do(tmp_path: Path) -> None:
    s = make_settings(openai_api_key="", jwt_secret_key="", allow_test_index=False, cors_origins="https://x.org")
    w = web_dir(tmp_path, env_local="VITE_MOCK_ASK=true\n", modules=False)
    r = run(s, tmp_path, web_dir=w, which=lambda _n: None, db_facts=dr.DbFacts(reachable=False, error_kind="timeout"))
    bad = [c for c in r.checks if c.status in (dr.FIX, dr.WARN)]
    assert len(bad) >= 6
    for c in bad:
        assert c.todo.strip(), f"{c.key} reports a problem without saying what to do"


def test_exit_code_follows_blockers(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    s = make_settings()
    monkeypatch.setattr("ask_bpl_orchestrator.config.get_settings", lambda: s)
    monkeypatch.setattr(dr, "run_checks", lambda *a, **k: run(make_settings(openai_api_key=""), tmp_path))
    assert dr.main([]) == 1
    monkeypatch.setattr(dr, "run_checks", lambda *a, **k: run(s, tmp_path))
    assert dr.main([]) == 0
    out = capsys.readouterr().out
    assert "Remember: a clean result means the parts are connected" in out
    assert_no_secret(out)


def test_clean_run_still_says_it_does_not_prove_answers_are_right(tmp_path: Path) -> None:
    text = dr.render(run(make_settings(), tmp_path), make_settings())
    assert "does not mean the answers are right" in text and "policies are current" in text


# ------------------------------------------------------------------------------------------ error classification
@pytest.mark.parametrize(
    "exc,kind",
    [
        (RuntimeError("Incorrect API key provided: sk-abc***"), "rejected_key"),
        (RuntimeError("Error 429: rate limit reached"), "limit_or_billing"),
        (type("E", (Exception,), {"status_code": 401})("oops"), "rejected_key"),
        (type("E", (Exception,), {"status_code": 403})("oops"), "rejected_key"),
        (RuntimeError("authentication_error"), "rejected_key"),
        (RuntimeError("invalid x-api-key"), "rejected_key"),
        (TimeoutError("x"), "timeout"),
        (ConnectionRefusedError("[Errno 111] Connect call failed"), "cannot_connect"),
        (RuntimeError("something odd"), "unknown"),
    ],
)
def test_classify_error(exc: BaseException, kind: str) -> None:
    assert dr.classify_error(exc) == kind


# ------------------------------------------------------------------------------------------ read-only guarantees
def _pinned_settings() -> Settings:
    from ask_bpl_orchestrator.config import get_settings

    return get_settings()


def test_database_connection_is_declared_read_only_and_issues_no_write(monkeypatch: pytest.MonkeyPatch) -> None:
    """Record every statement the doctor sends; the first must put the transaction in READ ONLY mode."""
    import sqlalchemy.ext.asyncio as sa_asyncio
    from sqlalchemy import event

    seen: list[str] = []
    real = sa_asyncio.create_async_engine

    def spying(*a: Any, **k: Any) -> AsyncEngine:
        eng = real(*a, **k)

        @event.listens_for(eng.sync_engine, "before_cursor_execute")
        def _rec(_c, _cur, statement, *_rest) -> None:  # noqa: ANN001
            seen.append(statement.strip())

        return eng

    monkeypatch.setattr(sa_asyncio, "create_async_engine", spying)
    facts = asyncio.run(dr.gather_database_facts(_pinned_settings(), dr.alembic_head()))
    assert facts.reachable
    assert seen, "no statements recorded"
    assert seen[0].upper().startswith("SET TRANSACTION READ ONLY")
    for stmt in seen:
        assert not re.match(r"(?is)\s*(insert|update|delete|alter|drop|create|truncate|grant)\b", stmt), stmt


def test_gathering_facts_changes_no_rows() -> None:
    async def counts() -> tuple[int, int]:
        async with async_session_factory() as s:
            return (
                (await s.execute(select(func.count()).select_from(Document))).scalar_one(),
                (await s.execute(select(func.count()).select_from(Tester))).scalar_one(),
            )

    before = asyncio.run(counts())
    facts = asyncio.run(dr.gather_database_facts(_pinned_settings(), dr.alembic_head()))
    after = asyncio.run(counts())
    assert facts.reachable and before == after


def test_against_the_real_test_database_the_tables_and_demo_tester_are_found() -> None:
    facts = asyncio.run(dr.gather_database_facts(_pinned_settings(), dr.alembic_head()))
    assert facts.reachable
    assert facts.head_known and facts.current_revision == facts.head_revision
    assert facts.demo_tester is True


def test_unreachable_database_is_reported_not_raised() -> None:
    s = make_settings(database_url="postgresql+asyncpg://u:p@127.0.0.1:1/none")
    facts = asyncio.run(dr.gather_database_facts(s, None))
    assert facts.reachable is False and facts.error_kind in ("cannot_connect", "timeout", "unknown")


def test_alembic_head_matches_the_newest_migration_file() -> None:
    versions = sorted(p.stem for p in (ORCH / "alembic" / "versions").glob("[0-9]*.py"))
    assert dr.alembic_head() == versions[-1]


def test_doctor_source_contains_no_write_statement_or_commit() -> None:
    src = (ORCH / "ask_bpl_orchestrator" / "doctor.py").read_text()
    code = "\n".join(line for line in src.splitlines() if not line.lstrip().startswith(("#", '"""')))
    assert not re.search(r"\b(INSERT INTO|DELETE FROM|UPDATE \w+ SET|DROP TABLE|ALTER TABLE|TRUNCATE)\b", code)
    assert ".commit(" not in code and "session.add(" not in code and "write_text(" not in code and "open(" not in code


# ------------------------------------------------------------------------------------------ registration and guide
def test_command_is_registered() -> None:
    assert 'askbpl-doctor = "ask_bpl_orchestrator.doctor:main"' in (ORCH / "pyproject.toml").read_text()


def _registered_commands() -> set[str]:
    return set(re.findall(r"^(askbpl-[a-z\-]+) =", (ORCH / "pyproject.toml").read_text(), re.M))


def _guide_commands(guide: str) -> set[str]:
    """Commands a reader would type: first word of lines in fenced blocks, and inline code that has arguments."""
    cmds: set[str] = set()
    for block in re.findall(r"```[a-z]*\n(.*?)```", guide, re.S):
        for line in block.splitlines():
            m = re.match(r"\s*(askbpl-[a-z]+(?:-[a-z]+)*)\b", line)
            if m:
                cmds.add(m.group(1))
    cmds |= set(re.findall(r"`(askbpl-[a-z]+(?:-[a-z]+)*) [^`]+`", guide))
    return cmds


def test_setup_guide_exists_names_only_real_commands_and_holds_no_secret() -> None:
    guide = (REPO / "docs" / "TESTER_SETUP.md").read_text()
    named = _guide_commands(guide)
    assert {"askbpl-doctor", "askbpl-seed", "askbpl-ingest-batch"} <= named
    assert named <= _registered_commands(), f"guide names commands that do not exist: {named - _registered_commands()}"
    assert not re.search(r"sk-[A-Za-z0-9_\-]{8,}|pcsk_[A-Za-z0-9]{8,}", guide)


def test_setup_guide_states_the_open_bpl_decisions_and_the_shared_login() -> None:
    guide = (REPO / "docs" / "TESTER_SETUP.md").read_text().lower()
    for needle in ("outside services", "personal information", "same demo", "not confirmed", "never paste", "spend"):
        assert needle in guide, needle
