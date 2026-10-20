"""Approved BPL glossary: query-side term expansion and unlisted-acronym detection (patch 0016; PRD GLO-1 to GLO-6).

What this does, and the limits that matter:

* Only entries with ``status: approved`` are ever used. ``draft`` and ``conflict`` entries are kept in the file for
  review and never match (GLO-1, GLO-5). An approved entry must carry an expansion, a source, an approver and a date,
  or the file is rejected.
* An approved term that appears in the question adds its expansion to the **retrieval query only**. The expansion is
  never given to the model, never shown to staff and never cited (GLO-6): the model still receives the staff
  member's own words, and an answer still needs real policy chunks above the grounding gate.
* The glossary never defines a term for staff. It only helps the search find text that spells a term out.
* Unlisted acronyms are **detected and counted for the log only** in this patch (GLO-2 behaviour is a team decision).
  The count is logged without the text: question text must not reach logs (SAF-5, NFR-4, AC-15).
* An empty or missing set of approved entries changes nothing: the retrieval query stays byte-identical.
"""

from __future__ import annotations

import datetime as dt
import logging
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable, Optional

import yaml

log = logging.getLogger(__name__)

BUNDLED_PATH = Path(__file__).resolve().parents[2] / "config" / "glossary.yaml"
STATUSES = ("approved", "draft", "conflict")
_ENTRY_KEYS = {
    "term",
    "expansion",
    "aliases",
    "context",
    "source",
    "status",
    "owner",
    "approved_by",
    "approved_on",
}
_TOP_KEYS = {"entries", "common_words_allowlist"}

# Capitalised tokens that are not BPL institutional acronyms. Extended by `common_words_allowlist` in the file.
BUILTIN_ALLOWLIST = frozenset(
    {
        "US",
        "USA",
        "NY",
        "NYC",
        "OK",
        "AM",
        "PM",
        "ID",
        "PDF",
        "FAQ",
        "ASAP",
        "FYI",
        "TV",
        "DVD",
        "CD",
        "URL",
    }
    | {"I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII"}
)
_ACRONYM_TOKEN = re.compile(r"(?<!\w)[A-Z]{2,6}(?!\w)")


class GlossaryError(ValueError):
    """The glossary file is unreadable or breaks a rule. The message says which entry and why."""


@dataclass(frozen=True)
class GlossaryEntry:
    term: str
    expansion: str = ""
    aliases: tuple[str, ...] = ()
    context: str = ""
    source: str = ""
    status: str = "draft"
    owner: str = ""
    approved_by: str = ""
    approved_on: Optional[dt.date] = None

    @property
    def forms(self) -> tuple[str, ...]:
        return (self.term, *self.aliases)


@dataclass(frozen=True)
class Match:
    entry: GlossaryEntry
    form: str  # the term or alias as written in the glossary


@dataclass(frozen=True)
class ExpandedQuery:
    text: str
    matches: tuple[Match, ...] = ()


def _is_acronym(form: str) -> bool:
    """Short all-capitals forms ("CBH", "MAC") match case-sensitively, so "Mac" or "mac" never fires them."""
    return (
        " " not in form
        and form == form.upper()
        and any(ch.isalpha() for ch in form)
        and len(form) <= 6
    )


def form_pattern(form: str) -> re.Pattern[str]:
    flags = 0 if _is_acronym(form) else re.IGNORECASE
    return re.compile(r"(?<!\w)" + re.escape(form) + r"(?!\w)", flags)


@dataclass(frozen=True)
class Glossary:
    entries: tuple[GlossaryEntry, ...] = ()
    allowlist: frozenset[str] = field(default_factory=frozenset)
    _patterns: tuple[tuple[GlossaryEntry, str, re.Pattern[str]], ...] = field(
        default=(), repr=False, compare=False
    )

    def __post_init__(self) -> None:
        patterns = tuple(
            (e, f, form_pattern(f)) for e in self.entries if e.status == "approved" for f in e.forms
        )
        object.__setattr__(self, "_patterns", patterns)

    @property
    def approved(self) -> tuple[GlossaryEntry, ...]:
        return tuple(e for e in self.entries if e.status == "approved")

    def find(self, text: str) -> tuple[Match, ...]:
        """Approved terms present in ``text``, one match per entry, in order of first appearance."""
        found: dict[str, tuple[int, Match]] = {}
        for entry, form, pattern in self._patterns:
            m = pattern.search(text)
            if m and (entry.term not in found or m.start() < found[entry.term][0]):
                found[entry.term] = (m.start(), Match(entry, form))
        return tuple(match for _, match in sorted(found.values(), key=lambda item: item[0]))

    def expand_query(self, text: str) -> ExpandedQuery:
        """Add approved expansions to a retrieval query. Nothing approved and present means the text is unchanged."""
        matches = self.find(text)
        lowered = text.casefold()
        added = [m for m in matches if m.entry.expansion.casefold() not in lowered]
        if not added:
            return ExpandedQuery(text, matches)
        suffix = "; ".join(f"{m.form} = {m.entry.expansion}" for m in added)
        return ExpandedQuery(f"{text} ({suffix})", matches)

    def unlisted_acronyms(self, text: str) -> list[str]:
        """All-capital tokens of 2 to 6 letters that are not an approved term, alias or allowlisted word.

        A question typed entirely in capitals is skipped: every word would look like an acronym.
        """
        if not any(ch.islower() for ch in text):
            return []
        known = {f for e in self.approved for f in e.forms} | BUILTIN_ALLOWLIST | self.allowlist
        seen: list[str] = []
        for token in _ACRONYM_TOKEN.findall(text):
            if token not in known and token not in seen:
                seen.append(token)
        return seen


def acronyms_missing_from(acronyms: Iterable[str], texts: Iterable[str]) -> list[str]:
    """Acronyms that appear in none of the given texts (for example, the retrieved policy chunks)."""
    blob = "\n".join(texts)
    return [a for a in acronyms if not re.search(r"(?<!\w)" + re.escape(a) + r"(?!\w)", blob)]


# ---------------------------------------------------------------------------------------------- loading
def _as_date(value: Any, where: str) -> Optional[dt.date]:
    if value in (None, ""):
        return None
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    try:
        return dt.date.fromisoformat(str(value))
    except ValueError as exc:
        raise GlossaryError(
            f"{where}: approved_on must be a date like 2026-10-18, got {value!r}"
        ) from exc


def _text(raw: dict[str, Any], key: str, where: str) -> str:
    value = raw.get(key, "")
    if value is None:
        return ""
    if not isinstance(value, (str, int, float)):
        raise GlossaryError(f"{where}: {key} must be text")
    return str(value).strip()


def _parse_entry(raw: Any, index: int) -> GlossaryEntry:
    if not isinstance(raw, dict):
        raise GlossaryError(f"entry {index}: each entry must be a mapping of fields")
    term = _text(raw, "term", f"entry {index}")
    where = f"entry {index} ({term or 'no term'})"
    unknown = set(raw) - _ENTRY_KEYS
    if unknown:
        raise GlossaryError(
            f"{where}: unknown field(s) {sorted(unknown)}; allowed: {sorted(_ENTRY_KEYS)}"
        )
    if not term:
        raise GlossaryError(f"{where}: term is required")
    status = _text(raw, "status", where) or "draft"
    if status not in STATUSES:
        raise GlossaryError(f"{where}: status must be one of {list(STATUSES)}, got {status!r}")
    aliases_raw = raw.get("aliases") or []
    if not isinstance(aliases_raw, list) or not all(
        isinstance(a, str) and a.strip() for a in aliases_raw
    ):
        raise GlossaryError(f"{where}: aliases must be a list of non-empty text")
    entry = GlossaryEntry(
        term=term,
        expansion=_text(raw, "expansion", where),
        aliases=tuple(a.strip() for a in aliases_raw),
        context=_text(raw, "context", where),
        source=_text(raw, "source", where),
        status=status,
        owner=_text(raw, "owner", where),
        approved_by=_text(raw, "approved_by", where),
        approved_on=_as_date(raw.get("approved_on"), where),
    )
    if status == "approved":
        missing = [
            name
            for name, value in (
                ("expansion", entry.expansion),
                ("source", entry.source),
                ("approved_by", entry.approved_by),
                ("approved_on", entry.approved_on),
            )
            if not value
        ]
        if missing:
            raise GlossaryError(f"{where}: an approved entry needs {', '.join(missing)}")
    return entry


def parse_glossary(data: Any) -> Glossary:
    if data is None:
        return Glossary()
    if not isinstance(data, dict):
        raise GlossaryError("the glossary file must be a mapping with an 'entries' list")
    unknown = set(data) - _TOP_KEYS
    if unknown:
        raise GlossaryError(
            f"unknown top-level key(s) {sorted(unknown)}; allowed: {sorted(_TOP_KEYS)}"
        )
    raw_entries = data.get("entries") or []
    if not isinstance(raw_entries, list):
        raise GlossaryError("'entries' must be a list")
    entries = tuple(_parse_entry(raw, i) for i, raw in enumerate(raw_entries, start=1))
    allow_raw = data.get("common_words_allowlist") or []
    if not isinstance(allow_raw, list) or not all(isinstance(a, str) for a in allow_raw):
        raise GlossaryError("'common_words_allowlist' must be a list of text")

    owners: dict[str, str] = {}
    for entry in entries:
        if entry.status != "approved":
            continue
        for form in entry.forms:
            key = form.casefold()
            if key in owners and owners[key] != entry.term:
                raise GlossaryError(
                    f"{form!r} is claimed by two approved entries ({owners[key]!r} and {entry.term!r})"
                )
            owners[key] = entry.term
    return Glossary(entries=entries, allowlist=frozenset(a.strip() for a in allow_raw if a.strip()))


def load_glossary(path: Path) -> Glossary:
    path = Path(path)
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise GlossaryError(f"cannot read the glossary file {path}: {exc.strerror or exc}") from exc
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise GlossaryError(f"{path.name} is not valid YAML: {exc}") from exc
    return parse_glossary(data)


@lru_cache
def get_glossary() -> Glossary:
    """The glossary the app uses. A broken file is logged as an error and treated as empty, so questions are still
    answered without expansion. Run ``askbpl-glossary-check`` to see exactly what is wrong."""
    from ask_bpl_orchestrator.config import get_settings

    configured = (get_settings().glossary_path or "").strip()
    path = Path(configured) if configured else BUNDLED_PATH
    try:
        return load_glossary(path)
    except GlossaryError:
        log.error(
            "glossary file could not be loaded; no terms will be expanded: %s", path, exc_info=True
        )
        return Glossary()
