"""Role lenses: who is asking changes the framing of an answer, never the evidence or the decision (patch 0024).

PRD ROLE-1 to ROLE-11. What this does, and the limits that matter:

* A role is **self-selected and is not a security boundary** (ROLE-4). It must never gate access to a document.
* ``resolve`` accepts anything. A missing, blank, wrongly typed or unrecognised value becomes the default role
  instead of an error (ROLE-11). It never raises. The default is set in the file (Staff since patch 0028, a team working
  choice, not a BPL decision), so a request that sends no role gets the default role's lens.
* The role reaches **generation only**. Retrieval, the safety gates, the grounding threshold and the answer-or-refuse
  decision never read it (ROLE-2). ``ask_service`` passes it to ``generate_answer`` and to the question log, nowhere else.
* Exactly one role is the *plain* role: no lens text and no addendum (General). Its prompt is byte-identical to the
  pre-0024 prompt, so it is the baseline the evals compare against. The default role may be any role.
* A lens may only ask the model to frame what the excerpts say. It must not invite invented duties (ROLE-3).
* The supervisor addendum stays off until the file records who approved it and when (ROLE-7).
* The role words live in ``config/roles.yaml`` so BPL can review them without code changes (ROLE-6).
"""

from __future__ import annotations

import datetime as dt
import logging
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

import yaml

log = logging.getLogger(__name__)

BUNDLED_PATH = Path(__file__).resolve().parents[2] / "config" / "roles.yaml"
_TOP_KEYS = {"default_role", "roles"}
_ROLE_KEYS = {"key", "label", "lens", "supervisor_addendum"}
_ADDENDUM_KEYS = {"approved", "max_sentences", "approved_by", "approved_on"}
MAX_ROLE_KEY_CHARS = 40
MAX_LENS_CHARS = 1200


class RolesError(ValueError):
    """The roles file is unreadable or breaks a rule. The message says which role and why."""


@dataclass(frozen=True)
class SupervisorAddendum:
    approved: bool = False
    max_sentences: int = 2
    approved_by: str = ""
    approved_on: Optional[dt.date] = None

    @property
    def active(self) -> bool:
        return self.approved and self.max_sentences > 0


@dataclass(frozen=True)
class Role:
    key: str
    label: str
    lens: str = ""
    addendum: SupervisorAddendum = SupervisorAddendum()


@dataclass(frozen=True)
class RoleSet:
    roles: tuple[Role, ...]
    default_key: str

    @property
    def default(self) -> Role:
        return self.by_key[self.default_key]

    @property
    def plain(self) -> Role:
        """The one role with no lens: the pre-role prompt, and the baseline for evals."""
        return next(r for r in self.roles if not r.lens and not r.addendum.active)

    @property
    def by_key(self) -> dict[str, Role]:
        return {r.key: r for r in self.roles}

    def resolve(self, value: Any) -> Role:
        """The role for a request value; anything not on the list is the default (ROLE-11)."""
        if isinstance(value, str):
            key = value.strip().casefold()
            if len(key) <= MAX_ROLE_KEY_CHARS and key in self.by_key:
                return self.by_key[key]
        return self.default


# The built-in set is used only if the file cannot be read: General, with no lens (the pre-role behaviour).
FALLBACK = RoleSet(roles=(Role(key="general", label="General"),), default_key="general")


# ------------------------------------------------------------------------------------------------ prompt text
def render_role_block(role: Role) -> str:
    """Text added to the system prompt for a role. The plain role (General) adds nothing (empty string)."""
    if not role.lens.strip():
        return ""
    lens = " ".join(role.lens.split())
    lines = [
        "ROLE LENS (framing only)",
        "------------------------",
        f"The staff member asking identified their role as: {role.label}. {lens}",
        "",
        "Rules for this lens:",
        "  · The role changes how you phrase the answer. It never changes which excerpts you use, and it never makes you",
        "    answer or refuse differently. If the excerpts would not support an answer for a General reader, refuse.",
        "  · State a duty, permission or step for this role ONLY if the RETRIEVAL_BLOCK says so. If the excerpts do not",
        "    distinguish by role, say in one sentence that the excerpts do not describe a different rule for this role,",
        "    then answer normally. Do not say or imply that the policy applies to everyone unless the excerpts say that.",
        "  · Report what the excerpts say, not what you think follows from them. Do not write \"you would\", \"you'll want to\"",
        "    or \"make sure\" about a step the excerpts do not state for this role, even if it seems a sensible consequence.",
        "  · If a rule applies to a defined group (for example \"Covered Persons\"), name the group and keep the rule attached",
        "    to it. Do not say \"you must\" or \"you need to\" unless the excerpts say the person asking belongs to that group.",
        "  · Point the person to an office or contact only if the excerpts name that office or contact for that purpose.",
        "  · The sentence limit stated earlier still applies in full. The role lens adds no sentences.",
    ]
    addendum = role.addendum
    if addendum.active:
        lines += [
            f"  · After the main answer you may add up to {addendum.max_sentences} sentences starting \"As a supervisor,\"",
            "    but only if the excerpts state something specific to supervisors. Otherwise add nothing.",
        ]
    return "\n".join(lines)


# ------------------------------------------------------------------------------------------------ loading
def _text(raw: dict[str, Any], key: str, where: str) -> str:
    value = raw.get(key, "")
    if value is None:
        return ""
    if not isinstance(value, (str, int, float)) or isinstance(value, bool):
        raise RolesError(f"{where}: {key} must be text")
    return str(value).strip()


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
        raise RolesError(f"{where}: approved_on must be a date like 2026-10-27, got {value!r}") from exc


def _int(value: Any, where: str, name: str, low: int, high: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        raise RolesError(f"{where}: {name} must be a whole number from {low} to {high}")
    return value


def _parse_addendum(raw: Any, where: str) -> SupervisorAddendum:
    if raw is None:
        return SupervisorAddendum()
    if not isinstance(raw, dict):
        raise RolesError(f"{where}: supervisor_addendum must be a mapping")
    unknown = set(raw) - _ADDENDUM_KEYS
    if unknown:
        raise RolesError(f"{where}: unknown supervisor_addendum field(s) {sorted(unknown)}")
    approved = raw.get("approved", False)
    if not isinstance(approved, bool):
        raise RolesError(f"{where}: supervisor_addendum.approved must be true or false")
    sentences = _int(raw.get("max_sentences", 2), where, "supervisor_addendum.max_sentences", 0, 4)
    approved_by = _text(raw, "approved_by", where)
    approved_on = _as_date(raw.get("approved_on"), where)
    if approved and not (approved_by and approved_on):
        raise RolesError(
            f"{where}: an approved supervisor addendum needs approved_by and approved_on (ROLE-7: BPL approves it)"
        )
    return SupervisorAddendum(approved, sentences, approved_by, approved_on)


def parse_roles(data: Any) -> RoleSet:
    if not isinstance(data, dict):
        raise RolesError("the roles file must be a mapping with a 'roles' list")
    unknown = set(data) - _TOP_KEYS
    if unknown:
        raise RolesError(f"unknown top-level key(s) {sorted(unknown)}; allowed: {sorted(_TOP_KEYS)}")
    raw_roles = data.get("roles")
    if not isinstance(raw_roles, list) or not raw_roles:
        raise RolesError("'roles' must be a non-empty list")
    roles: list[Role] = []
    seen: set[str] = set()
    for i, raw in enumerate(raw_roles, start=1):
        if not isinstance(raw, dict):
            raise RolesError(f"role {i}: each role must be a mapping of fields")
        key = _text(raw, "key", f"role {i}").casefold()
        where = f"role {i} ({key or 'no key'})"
        extra = set(raw) - _ROLE_KEYS
        if extra:
            raise RolesError(f"{where}: unknown field(s) {sorted(extra)}; allowed: {sorted(_ROLE_KEYS)}")
        if not key or len(key) > MAX_ROLE_KEY_CHARS or not key.replace("_", "").isalnum():
            raise RolesError(f"{where}: key must be 1 to {MAX_ROLE_KEY_CHARS} letters, digits or underscores")
        if key in seen:
            raise RolesError(f"{where}: duplicate key")
        seen.add(key)
        label = _text(raw, "label", where)
        if not label:
            raise RolesError(f"{where}: label is required")
        lens = _text(raw, "lens", where)
        if len(lens) > MAX_LENS_CHARS:
            raise RolesError(f"{where}: lens is longer than {MAX_LENS_CHARS} characters")
        roles.append(Role(key=key, label=label, lens=lens, addendum=_parse_addendum(raw.get("supervisor_addendum"), where)))
    default_key = _text(data, "default_role", "file").casefold()
    if default_key not in seen:
        raise RolesError(f"default_role {default_key!r} is not one of the roles {sorted(seen)}")
    plain = [r.key for r in roles if not r.lens]
    if len(plain) != 1:
        raise RolesError(
            f"exactly one role must have no lens (the plain role whose answers match the pre-role behaviour); "
            f"found {len(plain)}: {plain}"
        )
    for r in roles:
        if not r.lens and r.addendum.active:
            raise RolesError(f"role {r.key}: the plain role (no lens) cannot have a supervisor addendum")
    return RoleSet(roles=tuple(roles), default_key=default_key)


def load_roles(path: Path) -> RoleSet:
    try:
        data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError, UnicodeDecodeError) as exc:
        raise RolesError(f"cannot read {path}: {exc}") from exc
    return parse_roles(data)


@lru_cache
def get_roles() -> RoleSet:
    """The role set the app uses. A broken file is logged as an error and leaves only General, so questions are
    still answered exactly as before. Run ``python -c "from ask_bpl_orchestrator.services.roles import *"`` or the
    tests to see what is wrong."""
    from ask_bpl_orchestrator.config import get_settings

    configured = (get_settings().roles_path or "").strip()
    path = Path(configured) if configured else BUNDLED_PATH
    try:
        return load_roles(path)
    except RolesError:
        log.error("roles file could not be loaded; only the General role is available: %s", path, exc_info=True)
        return FALLBACK
