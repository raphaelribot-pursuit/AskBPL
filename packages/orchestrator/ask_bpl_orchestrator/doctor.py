"""askbpl-doctor: READ-ONLY preflight check in plain words (patch 0019; PRD INT-1, NFR-3, NFR-8, SAF-5).

    askbpl-doctor                       # offline checks: settings, database, web demo files
    askbpl-doctor --live                # also ask OpenAI, Anthropic and Pinecone whether the keys work
    askbpl-doctor --url http://localhost:8000    # also ask a running Ask BPL server whether it is ready

It tells a person who is not a developer whether this computer is ready to run the Ask BPL test version, and for
every problem it says what to do next. It changes nothing: it never writes to the database (the connection is set to
read-only), the settings file, the glossary or Pinecone.

Safety rules this file keeps (each has a test):

* A secret is never printed: not the value, not its length, not its first characters. Output says only "set" or
  "not set". The database address is shown without the password.
* Text from an error raised by OpenAI, Anthropic, Pinecone or the database is never printed. Those messages can echo a
  partly masked key or a connection string. The check classifies the error (key rejected, timed out, cannot connect)
  and prints its own fixed sentence.
* Without ``--live`` it makes no call to any outside service, so it costs nothing and sends nothing.

What it cannot tell you: whether answers are correct, whether the policies are current, or whether BPL has approved
sending questions to outside AI services. A green result means "the pipes are connected", nothing more.
"""

from __future__ import annotations

import argparse
import asyncio
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping, Optional, Sequence
from urllib.parse import urlsplit

from ask_bpl_orchestrator.config import Settings

OK, FIX, WARN, INFO, SKIP = "ok", "fix", "warn", "info", "skip"
TAGS = {OK: "[OK]   ", FIX: "[FIX]  ", WARN: "[CHECK]", INFO: "[NOTE] ", SKIP: "[SKIP] "}

# Settings that must hold a value before the question pipeline can run. Value = how a person finds it.
REQUIRED_SECRETS: dict[str, str] = {
    "jwt_secret_key": "JWT_SECRET_KEY",
    "openai_api_key": "OPENAI_API_KEY",
    "anthropic_api_key": "ANTHROPIC_API_KEY",
    "pinecone_api_key": "PINECONE_API_KEY",
}
SERVICE_NAME = {
    "OPENAI_API_KEY": "OpenAI (turns questions into searchable numbers)",
    "ANTHROPIC_API_KEY": "Anthropic (writes the answer)",
    "PINECONE_API_KEY": "Pinecone (stores the policy text for searching)",
    "JWT_SECRET_KEY": "the server's own session secret",
}
_PLACEHOLDER = re.compile(r"(your[-_ ]?key|changeme|change[-_ ]me|xxxx|<.*>|\.\.\.|replace|example|todo)", re.I)
# Anything shaped like a key or a URL password that must never reach the screen, even by accident.
_SECRET_SHAPES = re.compile(r"(sk-[A-Za-z0-9_\-]{6,}|pcsk_[A-Za-z0-9_\-]{6,}|://[^/\s:@]+:[^@\s]+@)")


@dataclass
class Check:
    key: str
    status: str
    title: str
    detail: str = ""
    todo: str = ""


@dataclass
class Report:
    checks: list[Check] = field(default_factory=list)

    def add(self, key: str, status: str, title: str, detail: str = "", todo: str = "") -> Check:
        c = Check(key, status, title, detail, todo)
        self.checks.append(c)
        return c

    def count(self, status: str) -> int:
        return sum(1 for c in self.checks if c.status == status)

    @property
    def blockers(self) -> int:
        return self.count(FIX)


# ------------------------------------------------------------------------------------------------ helpers
def scrub(text: str, settings: Optional[Settings] = None) -> str:
    """Remove anything secret-shaped, and every configured secret value, from a string headed for the screen."""
    out = text
    if settings is not None:
        for attr in (*REQUIRED_SECRETS, "admin_basic_password"):
            val = str(getattr(settings, attr, "") or "").strip()
            if len(val) >= 4:
                out = out.replace(val, "[hidden]")
    return _SECRET_SHAPES.sub("[hidden]", out)


def classify_error(exc: BaseException) -> str:
    """Name what went wrong without ever repeating the error's own text."""
    text = f"{type(exc).__name__} {exc}".lower()
    code = getattr(exc, "status_code", None)
    if code in (401, 403) or any(w in text for w in ("authentication", "invalid api key", "incorrect api key", "x-api-key", "unauthorized", "permission")):
        return "rejected_key"
    if code == 429 or "rate limit" in text or "quota" in text or "insufficient" in text:
        return "limit_or_billing"
    if isinstance(exc, (asyncio.TimeoutError, TimeoutError)) or "timed out" in text or "timeout" in text:
        return "timeout"
    if any(w in text for w in ("connect", "refused", "name or service", "network", "resolve", "unreachable", "getaddrinfo")):
        return "cannot_connect"
    if code == 404 or "not found" in text:
        return "not_found"
    return "unknown"


_ERROR_WORDS = {
    "rejected_key": "The service refused the key. It may be mistyped, expired or switched off.",
    "limit_or_billing": "The service answered but says a usage limit or billing problem is in the way.",
    "timeout": "The service did not answer in time. Check the internet connection and try again.",
    "cannot_connect": "Could not reach the service. Check the internet connection.",
    "not_found": "The service said it could not find what was asked for (check the name or address in the settings file).",
    "unknown": "The check failed for a reason this tool cannot name. Ask the build team; do not paste the settings file.",
}


def describe_database_target(url: str) -> str:
    """host:port/name, never the user name or the password."""
    try:
        parts = urlsplit(url.replace("+asyncpg", ""))
        host = parts.hostname or "(socket)"
        port = f":{parts.port}" if parts.port else ""
        name = (parts.path or "").lstrip("/")
        return f"{host}{port}/{name}" if name else f"{host}{port}"
    except Exception:  # noqa: BLE001 - never let a malformed address crash a status page
        return "(address could not be read)"


def _looks_placeholder(value: str) -> bool:
    v = value.strip()
    return bool(_PLACEHOLDER.search(v)) or (len(v) >= 2 and v[0] == v[-1] and v[0] in "'\"")


# ------------------------------------------------------------------------------------------------ settings checks
def check_settings_file(report: Report, cwd: Path) -> None:
    env_file = cwd / ".env"
    if env_file.is_file():
        report.add("env_file", OK, "Settings file (.env) found", f"in {cwd}")
    else:
        report.add(
            "env_file",
            WARN,
            "No settings file named .env in this folder",
            "Settings can also come from the computer's environment, so this is not always a problem.",
            "Run this command from the folder 'packages/orchestrator', where the .env file lives. "
            "If you do not have one, copy '.env.example' to '.env' and fill it in (ask the build team for the keys; never email or paste them).",
        )


def check_secrets(report: Report, settings: Settings) -> None:
    for attr, env_name in REQUIRED_SECRETS.items():
        raw = str(getattr(settings, attr, "") or "")
        who = SERVICE_NAME[env_name]
        if not raw.strip():
            report.add(
                f"secret:{env_name}",
                FIX,
                f"{env_name} is not set",
                f"This is needed for {who}.",
                f"Open the .env file and add a line {env_name}=... with the value the build team gave you. "
                "Do not type spaces or quote marks around it.",
            )
        elif _looks_placeholder(raw):
            report.add(
                f"secret:{env_name}",
                FIX,
                f"{env_name} looks like a placeholder or has quote marks around it",
                f"This is needed for {who}.",
                "Replace it with the real value, with no quote marks and no spaces.",
            )
        else:
            report.add(f"secret:{env_name}", OK, f"{env_name} is set", f"Used for {who}. (The value is never shown.)")
    if not settings.pinecone_index_name.strip():
        report.add(
            "pinecone_index_name",
            FIX,
            "PINECONE_INDEX_NAME is not set",
            "",
            "Add PINECONE_INDEX_NAME=... to the .env file (the build team knows the index name).",
        )
    else:
        report.add("pinecone_index_name", OK, f"Pinecone index name is set ({settings.pinecone_index_name})")
    if not (settings.admin_basic_password or "").strip():
        report.add(
            "admin_password",
            INFO,
            "The build-team admin page has no password set",
            "Testers do not need it. Only the build team uses /admin.",
            "Leave it alone unless you are the build team. Do not leave /admin reachable by other people without a password.",
        )
    else:
        report.add("admin_password", OK, "Admin page password is set")


def check_privacy_flags(report: Report, settings: Settings) -> None:
    if settings.allow_test_index:
        report.add(
            "test_index",
            INFO,
            "Test mode is on: answers are labelled as coming from an unconfirmed test index",
            "This is correct for testing. BPL has not yet confirmed any policy as current.",
            "The build team must switch ALLOW_TEST_INDEX to false before real use.",
        )
    else:
        report.add(
            "test_index",
            WARN,
            "Test mode is off: only policies BPL has marked 'eligible' can answer",
            "If no policy has been confirmed yet, every question will be refused.",
            "For the test version, set ALLOW_TEST_INDEX=true in .env.",
        )
    report.add(
        "outside_services",
        INFO,
        "Each question typed by a tester is sent to outside services",
        "OpenAI (to match the question to policy text), Anthropic (to write the answer) and Pinecone (to store policy text). "
        "BPL has not yet answered whether this is acceptable for staff testing (open BPL decision: SAF-5, SAF-9, NFR-4).",
        "Until BPL answers, testers should not type real names, case details or other personal information.",
    )


# ------------------------------------------------------------------------------------------------ database checks
@dataclass
class DbFacts:
    reachable: bool = False
    error_kind: str = ""
    current_revision: Optional[str] = None
    head_revision: Optional[str] = None
    head_known: bool = False
    demo_tester: Optional[bool] = None  # None = unknown, True = present and active, False = missing or inactive
    answerable_titles: list[str] = field(default_factory=list)
    docs_total: int = 0
    docs_not_answerable: int = 0
    chunks: int = 0
    approved_glossary_entries: Optional[int] = None


def alembic_head(orchestrator_dir: Optional[Path] = None) -> Optional[str]:
    """The newest migration this code knows about, or None when the migration folder cannot be found."""
    base = orchestrator_dir or Path(__file__).resolve().parents[1]
    ini = base / "alembic.ini"
    if not ini.is_file():
        return None
    try:
        from alembic.config import Config
        from alembic.script import ScriptDirectory

        cfg = Config(str(ini))
        cfg.set_main_option("script_location", str(base / "alembic"))
        return ScriptDirectory.from_config(cfg).get_current_head()
    except Exception:  # noqa: BLE001
        return None


async def gather_database_facts(settings: Settings, head: Optional[str]) -> DbFacts:
    """Read-only look at the database. The transaction is declared READ ONLY, so a write would be refused by Postgres."""
    from sqlalchemy import func, select, text
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy.pool import NullPool

    from ask_bpl_orchestrator.db.models import Chunk, Document, Tester
    from ask_bpl_orchestrator.services.eligibility import retrievable_clause

    facts = DbFacts(head_revision=head, head_known=head is not None)
    engine = create_async_engine(settings.database_url, poolclass=NullPool, connect_args={"timeout": 5})
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SET TRANSACTION READ ONLY"))
            await conn.execute(text("SELECT 1"))
            facts.reachable = True
            try:
                row = (await conn.execute(text("SELECT version_num FROM alembic_version"))).first()
                facts.current_revision = row[0] if row else None
            except Exception:  # noqa: BLE001 - table missing means "not migrated"
                await conn.rollback()
                await conn.execute(text("SET TRANSACTION READ ONLY"))
                facts.current_revision = None
            migrated = facts.current_revision is not None and (not facts.head_known or facts.current_revision == head)
            if migrated:
                email = settings.public_demo_tester_email.strip().lower()
                t = (await conn.execute(select(Tester.active).where(Tester.email == email))).first()
                facts.demo_tester = bool(t[0]) if t is not None else False
                facts.docs_total = (await conn.execute(select(func.count()).select_from(Document))).scalar_one()
                titles = (
                    await conn.execute(select(Document.title).where(retrievable_clause(settings)).order_by(Document.title))
                ).scalars().all()
                facts.answerable_titles = list(titles)
                facts.docs_not_answerable = facts.docs_total - len(titles)
                facts.chunks = (await conn.execute(select(func.count()).select_from(Chunk))).scalar_one()
            await conn.rollback()
    except Exception as exc:  # noqa: BLE001
        facts.error_kind = classify_error(exc)
    finally:
        await engine.dispose()
    return facts


def check_database(report: Report, settings: Settings, facts: DbFacts) -> None:
    target = describe_database_target(settings.database_url)
    if not facts.reachable:
        why = _ERROR_WORDS.get(facts.error_kind, _ERROR_WORDS["unknown"])
        if facts.error_kind == "rejected_key":
            why = "The database refused the user name or password in DATABASE_URL."
        elif facts.error_kind == "cannot_connect":
            why = "Nothing answered at that address. The database is probably not started, or the address or port in DATABASE_URL is wrong."
        elif facts.error_kind == "timeout":
            why = "The database did not answer in time. It may still be starting; wait a minute and run this again."
        report.add(
            "db_reachable",
            FIX,
            f"Cannot reach the database at {target}",
            why,
            "Start the database (Docker Desktop must be open, then run: docker compose -f infra/docker-compose.yml up -d) "
            "and check DATABASE_URL in .env. See docs/TESTER_SETUP.md, step 3.",
        )
        return
    report.add("db_reachable", OK, f"Database is reachable at {target}")
    if facts.current_revision is None:
        report.add(
            "db_migrated",
            FIX,
            "The database is empty (its tables have not been created)",
            "",
            "From packages/orchestrator run: alembic upgrade head   then: askbpl-seed",
        )
        return
    if facts.head_known and facts.current_revision != facts.head_revision:
        report.add(
            "db_migrated",
            FIX,
            "The database is out of date for this version of the code",
            f"The database is at '{facts.current_revision}'; this code expects '{facts.head_revision}'.",
            "From packages/orchestrator run: alembic upgrade head",
        )
        return
    note = "" if facts.head_known else "Could not find the migration folder, so only 'tables exist' was checked."
    report.add("db_migrated", OK, "The database tables are up to date", note)
    if facts.demo_tester:
        report.add("demo_tester", OK, "The shared demo tester account exists")
    else:
        report.add(
            "demo_tester",
            FIX,
            "The shared demo tester account is missing or switched off",
            "The test web page signs everyone in through this one account.",
            "From packages/orchestrator run: askbpl-seed",
        )
    n = len(facts.answerable_titles)
    if n == 0:
        report.add(
            "answerable_docs",
            FIX,
            "No policy documents can be used to answer questions yet",
            f"{facts.docs_total} documents are recorded; none is both indexed and allowed to answer.",
            "Load the test policies (docs/PINECONE_CORPUS_INGEST.md) or check ALLOW_TEST_INDEX.",
        )
    else:
        shown = "; ".join(facts.answerable_titles[:10]) + (" ..." if n > 10 else "")
        report.add(
            "answerable_docs",
            OK,
            f"{n} policy document{'s' if n != 1 else ''} can answer questions (of the 88 BPL policies)",
            f"{shown}. {facts.chunks} text passages are stored. None of these is confirmed current by BPL yet.",
        )
    if facts.approved_glossary_entries is not None:
        if facts.approved_glossary_entries == 0:
            report.add(
                "glossary",
                INFO,
                "The acronym glossary has no BPL-approved terms",
                "Acronyms are not expanded until BPL approves definitions. This is expected.",
            )
        else:
            report.add("glossary", OK, f"The glossary has {facts.approved_glossary_entries} approved terms")


def glossary_count(settings: Settings) -> Optional[int]:
    try:
        from ask_bpl_orchestrator.services.glossary import BUNDLED_PATH, load_glossary

        path = Path(settings.glossary_path) if (settings.glossary_path or "").strip() else BUNDLED_PATH
        return len(load_glossary(path).approved)
    except Exception:  # noqa: BLE001
        return None


# ------------------------------------------------------------------------------------------------ web demo checks
def parse_env_file(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.is_file():
        return out
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        k, v = s.split("=", 1)
        out[k.strip()] = v.strip()
    return out


def check_web_demo(report: Report, settings: Settings, web_dir: Optional[Path], which: Callable[[str], Optional[str]]) -> None:
    if web_dir is None or not web_dir.is_dir():
        report.add(
            "web_dir",
            INFO,
            "The web page folder (packages/web-demo) was not found from here",
            "This is fine if the web page is hosted somewhere else.",
        )
        return
    env_local = web_dir / ".env.local"
    values = parse_env_file(env_local)
    if not env_local.is_file():
        report.add(
            "web_env",
            FIX,
            "The web page has no settings file (.env.local)",
            "Without it the page does not know where the Ask BPL server is.",
            "In packages/web-demo copy '.env.example' to '.env.local' (see docs/TESTER_SETUP.md, step 5).",
        )
    else:
        api = values.get("VITE_API_BASE_URL", "").strip()
        if not api:
            report.add(
                "web_api",
                FIX,
                "The web page settings do not say where the server is (VITE_API_BASE_URL)",
                "",
                "Add the line VITE_API_BASE_URL=http://localhost:8000 to packages/web-demo/.env.local",
            )
        else:
            report.add("web_api", OK, f"The web page will talk to {scrub(api, settings)}")
            origin = _page_origin_ok(settings)
            if not origin:
                report.add(
                    "cors",
                    WARN,
                    "The server may refuse requests from the web page's address",
                    "The usual address of the test page (http://localhost:5173) is not in CORS_ORIGINS.",
                    "Add http://localhost:5173 to CORS_ORIGINS in .env, or ignore this if the page runs on another address you have already listed.",
                )
        if values.get("VITE_MOCK_ASK", "").strip().lower() == "true":
            report.add(
                "web_mock",
                FIX,
                "The web page is in PRETEND mode (VITE_MOCK_ASK=true)",
                "It shows canned answers instead of asking the real system. Testers would be judging fake answers.",
                "Remove the VITE_MOCK_ASK line from packages/web-demo/.env.local, or set it to false, and restart the page.",
            )
        if values.get("VITE_PILOT_DEMO_ACCESS_CODE", "").strip():
            report.add(
                "web_code",
                WARN,
                "An access code is written into the web page settings",
                "Anything in a VITE_ variable is readable by anyone who can open the page.",
                "Do not host a page built with a real access code in it.",
            )
    if (web_dir / "node_modules").is_dir():
        report.add("web_modules", OK, "The web page's add-on packages are installed")
    else:
        report.add(
            "web_modules",
            FIX,
            "The web page's add-on packages are not installed",
            "",
            "In packages/web-demo run: npm install",
        )
    if which("node") is None:
        report.add(
            "node",
            FIX,
            "Node.js is not installed (the web page needs it to start)",
            "",
            "Install the current LTS version of Node.js from nodejs.org, then reopen the terminal.",
        )
    else:
        report.add("node", OK, "Node.js is installed")


def _page_origin_ok(settings: Settings) -> bool:
    origins = {o.rstrip("/") for o in settings.cors_origin_list}
    return "http://localhost:5173" in origins or "*" in origins


# ------------------------------------------------------------------------------------------------ live checks
async def check_running_server(report: Report, base_url: str, fetch: Optional[Callable[[str], Any]] = None) -> None:
    import httpx

    base = base_url.rstrip("/")

    async def _get(path: str) -> int:
        if fetch is not None:
            return await fetch(base + path)
        async with httpx.AsyncClient(timeout=5.0) as client:
            return (await client.get(base + path)).status_code

    try:
        alive = await _get("/healthz")
    except Exception as exc:  # noqa: BLE001
        kind = classify_error(exc)
        report.add(
            "server",
            INFO,
            f"The Ask BPL server is not running at {scrub(base, None)}",
            _ERROR_WORDS.get(kind, "") if kind != "unknown" else "",
            "If you have not started it yet, that is expected. Start it with: uvicorn ask_bpl_orchestrator.main:app --port 8000",
        )
        return
    if alive != 200:
        report.add("server", FIX, f"The server at {base} answered but is not healthy (status {alive})")
        return
    report.add("server", OK, f"The Ask BPL server is running at {base}")
    try:
        ready = await _get("/readyz")
    except Exception:  # noqa: BLE001
        ready = 0
    if ready == 200:
        report.add("server_ready", OK, "The server can reach its database")
    else:
        report.add(
            "server_ready",
            FIX,
            "The server is running but cannot reach its database",
            "",
            "Check DATABASE_URL in .env and restart the server.",
        )


async def check_outside_services(
    report: Report,
    settings: Settings,
    probes: Optional[Mapping[str, Callable[[Settings], Any]]] = None,
    db_chunks: int = 0,
) -> None:
    """Ask the three outside services whether the keys work. Costs a fraction of a cent. Opt-in (--live)."""
    from ask_bpl_orchestrator import health_checks as hc

    use = dict(probes) if probes else {"openai": hc.probe_openai, "anthropic": hc.probe_anthropic, "pinecone": hc.probe_pinecone}
    labels = {"openai": "OpenAI", "anthropic": "Anthropic", "pinecone": "Pinecone"}
    keys = {"openai": "openai_api_key", "anthropic": "anthropic_api_key", "pinecone": "pinecone_api_key"}
    names = list(use)
    has_key = {n: bool(str(getattr(settings, keys[n], "") or "").strip()) for n in names}

    async def _skipped() -> dict[str, Any]:
        return {"status": "skipped"}

    # A service whose key is not set is never called: there is nothing to test and no reason to spend a request.
    results = await asyncio.gather(*(_run_probe(use[n], settings) if has_key[n] else _skipped() for n in names))
    for name, res in zip(names, results):
        label = labels[name]
        if not has_key[name]:
            report.add(f"live:{name}", SKIP, f"{label}: skipped because its key is not set")
            continue
        if res.get("status") == "ok":
            if name == "pinecone":
                vectors = int(res.get("vectors") or 0)
                msg = f"Pinecone answers and holds {vectors} stored passages"
                report.add(f"live:{name}", OK, msg)
                if db_chunks and vectors < db_chunks:
                    report.add(
                        "live:pinecone_gap",
                        WARN,
                        "Pinecone holds fewer passages than the database lists",
                        f"Pinecone has {vectors}; the database lists {db_chunks}. Some documents may need to be loaded again.",
                        "Ask the build team to re-run the ingest step (docs/PINECONE_CORPUS_INGEST.md).",
                    )
            else:
                report.add(f"live:{name}", OK, f"{label} accepted the key")
            continue
        detail = str(res.get("detail", ""))
        if name == "pinecone" and detail == "index_empty":
            report.add(
                "live:pinecone",
                FIX,
                "Pinecone answers but holds no stored passages",
                "Every question would be refused.",
                "Load the test policies (docs/PINECONE_CORPUS_INGEST.md).",
            )
            continue
        kind = res.get("kind") or "unknown"
        report.add(
            f"live:{name}",
            FIX,
            f"{label} did not accept the check",
            _ERROR_WORDS.get(kind, _ERROR_WORDS["unknown"]),
            f"Check {label}'s key in .env, then run this again.",
        )


async def _run_probe(probe: Callable[[Settings], Any], settings: Settings) -> dict[str, Any]:
    """Run one probe and return only its status and a CLASSIFIED reason. The probe's own error text is dropped."""
    try:
        res = await probe(settings)
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "kind": classify_error(exc)}
    if not isinstance(res, dict):
        return {"status": "error", "kind": "unknown"}
    if res.get("status") == "ok":
        return {"status": "ok", "vectors": res.get("vectors")}
    detail = str(res.get("detail", ""))
    if detail == "index_empty":
        return {"status": "error", "detail": "index_empty"}
    return {"status": "error", "kind": _classify_text(detail)}


def _classify_text(text: str) -> str:
    class _E(Exception):
        pass

    return classify_error(_E(text))


# ------------------------------------------------------------------------------------------------ run + render
def run_checks(
    settings: Settings,
    *,
    cwd: Optional[Path] = None,
    web_dir: Optional[Path] = None,
    live: bool = False,
    url: Optional[str] = None,
    db_facts: Optional[DbFacts] = None,
    probes: Optional[Mapping[str, Callable[[Settings], Any]]] = None,
    which: Optional[Callable[[str], Optional[str]]] = None,
    fetch: Optional[Callable[[str], Any]] = None,
) -> Report:
    import shutil

    report = Report()
    check_settings_file(report, cwd or Path.cwd())
    check_secrets(report, settings)
    check_privacy_flags(report, settings)
    facts = db_facts
    if facts is None:
        facts = asyncio.run(gather_database_facts(settings, alembic_head()))
        facts.approved_glossary_entries = glossary_count(settings)
    check_database(report, settings, facts)
    check_web_demo(report, settings, web_dir, which or shutil.which)
    if url:
        asyncio.run(check_running_server(report, url, fetch))
    if live:
        asyncio.run(check_outside_services(report, settings, probes, db_chunks=facts.chunks))
    else:
        report.add(
            "live_skipped",
            INFO,
            "The outside services were not contacted",
            "OpenAI, Anthropic and Pinecone were not asked whether the keys work.",
            "Run: askbpl-doctor --live   (uses a tiny amount of paid usage: one short embedding and one 10-word reply).",
        )
    return report


def render(report: Report, settings: Optional[Settings] = None) -> str:
    lines = ["Ask BPL preflight check", "=" * 23, ""]
    for c in report.checks:
        lines.append(f"{TAGS[c.status]} {c.title}")
        if c.detail:
            lines.append(f"          {c.detail}")
        if c.todo and c.status in (FIX, WARN, INFO):
            lines.append(f"          What to do: {c.todo}")
    lines.append("")
    fixes, warns = report.count(FIX), report.count(WARN)
    if fixes:
        lines.append(f"Result: {fixes} thing{'s' if fixes != 1 else ''} to fix before testing. Start with the first [FIX] above.")
    elif warns:
        lines.append(f"Result: nothing is broken, but {warns} item{'s' if warns != 1 else ''} marked [CHECK] need a look.")
    else:
        lines.append("Result: everything this tool can check is in place.")
    lines.append(
        "Remember: a clean result means the parts are connected. It does not mean the answers are right, "
        "the policies are current, or that BPL has approved sending questions to outside services."
    )
    text = "\n".join(lines)
    return scrub(text, settings)  # last line of defence: nothing secret-shaped leaves this function


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Plain-words, read-only preflight check for the Ask BPL test version.")
    parser.add_argument("--live", action="store_true", help="also ask OpenAI, Anthropic and Pinecone whether the keys work (tiny cost)")
    parser.add_argument("--url", default=None, help="also check a running server, e.g. http://localhost:8000")
    parser.add_argument("--web-dir", type=Path, default=None, help="the packages/web-demo folder (default: found next to this project)")
    args = parser.parse_args(argv)

    from ask_bpl_orchestrator.config import get_settings

    settings = get_settings()
    web_dir = args.web_dir
    if web_dir is None:
        guess = Path(__file__).resolve().parents[2] / "web-demo"
        web_dir = guess if guess.is_dir() else None
    report = run_checks(settings, web_dir=web_dir, live=args.live, url=args.url)
    print(render(report, settings))
    return 1 if report.blockers else 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
