"""Replace people's names in a staff question before it is stored or sent to an outside service (patch 0064).

Team decision 2026-11-02 (options 1, 2 and 3): staff are asked not to type names; names that are typed anyway are found
here, on our own server, and replaced before the question is embedded (OpenAI), answered (Anthropic) or stored. Policy
answers almost never depend on who was named, so the question still gets its answer; the staff member is told a name was
removed. Nothing about the name is logged: counts only.

How a name is found (offline, from `config/person_names.txt`, see `config/person_names_SOURCE.md`):

1. a title then a capitalised word: "Ms. Rodriguez", "Dr. Patel";
2. a role word then a name: "my coworker Tasha", "my manager jennifer" (after "my"/"our" any capitalised word or listed
   name; after "a"/"the" only a capitalised listed name, so "the Volunteer Manual" is not a person);
3. a capitalised listed first name, with a following capitalised word taken as the surname. Everyday-word names
   (AMBIGUOUS: Will, May, Grace...) count only when a surname follows ("Grace Kim", never "grace period" or "May").

ALL-CAPS words (headings, acronyms) are never names. Known limits: rare names not in the list ("Selvon"), public figures
are replaced too ("Toni Morrison"), and a name written in lower case without a role word is missed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional, Tuple

NAMES_FILE = Path(__file__).resolve().parents[2] / "config" / "person_names.txt"
REPLACEMENT = "a colleague"

# Names that are also everyday words: names only beside a surname, a title or a role word.
AMBIGUOUS = frozenset(
    """may will mark frank grace rose ruby amber angel crystal robin dale dawn june holly chase pearl bill daisy
    destiny faith autumn joy grant gene glen jade brandy lance iris penny hope genesis summer guy trinity drew luna ivy
    misty sandy wade august april opal olive pat willow river earnest nova chance lane nick jack ray dean jay sue melody
    harmony hazel violet gage noel rex bob rich art sky star brook storm reed price sage case justice royal king major""".split()
)
# Capitalised words that follow a name but are not surnames ("Grace Policy" is not a person).
NOT_SURNAMES = frozenset(
    """policy policies library branch office manual handbook program programme form guide agreement contract services
    act plan department center centre committee hall""".split()
)
_TITLES = r"(?:Mr|Mrs|Ms|Miss|Mx|Dr|Prof)\.?"
_ROLE = (
    r"(?:co-?worker|colleague|manager|supervisor|boss|director|assistant|librarian|cousin|sister|brother|friend"
    r"|neighbou?r|partner|husband|wife|son|daughter|employee|volunteer|patron)"
)
_TOKEN = re.compile(r"[A-Za-z][A-Za-z'’\-]+")


@lru_cache(maxsize=1)
def _names() -> frozenset:
    return frozenset(line.strip() for line in NAMES_FILE.read_text(encoding="utf-8").splitlines() if line.strip())


def _base(word: str) -> str:
    return re.sub(r"['’]s$", "", word)


def find_names(text: str) -> List[Tuple[int, int, str]]:
    """(start, end, kind) for each name found, merged; kind is "title", "role" or "first"."""
    names = _names()
    spans: List[Tuple[int, int, str]] = []
    for m in re.finditer(rf"\b{_TITLES}\s+([A-Z][a-zA-Z'’\-]+)", text):
        spans.append((m.start(), m.end(), "title"))
    for m in re.finditer(rf"\b(my|our|the|a)\s+{_ROLE}\s+([A-Za-z][a-zA-Z'’\-]+)", text, re.I):
        det, word = m.group(1).lower(), m.group(2)
        low = _base(word.lower())
        if low in NOT_SURNAMES:
            continue
        ok = (word[0].isupper() or low in names) if det in ("my", "our") else (word[0].isupper() and low in names)
        if ok:
            spans.append((m.start(2), m.end(2), "role"))
    for m in _TOKEN.finditer(text):
        base = _base(m.group(0))
        if len(base) > 1 and base.isupper():
            continue  # ALL CAPS: a heading or an acronym
        if not base[0].isupper() or base.lower() not in names:
            continue
        end = m.end()
        nxt = re.match(r"\s+([A-Z][a-z][a-zA-Z'’\-]*)", text[end:])
        has_surname = bool(nxt) and nxt.group(1).lower() not in NOT_SURNAMES
        if base.lower() in AMBIGUOUS and not has_surname:
            continue
        if has_surname:
            end += nxt.end()
        spans.append((m.start(), end, "first"))
    extended = []
    for s, e, kind in spans:
        suffix = re.match(r",?\s+(?:Jr|Sr)\.?|\s+(?:II|III|IV)\b", text[e:])
        extended.append((s, e + (suffix.end() if suffix else 0), kind))
    extended.sort()
    merged: List[Tuple[int, int, str]] = []
    for s, e, kind in extended:
        if merged and (s <= merged[-1][1] or text[merged[-1][1]:s].strip() == ""):
            ps, pe, pk = merged[-1]
            merged[-1] = (ps, max(pe, e), "role" if "role" in (pk, kind) else pk)
        else:
            merged.append((s, e, kind))
    return merged


@dataclass(frozen=True)
class Redaction:
    text: str
    removed: int


def redact(text: str) -> Redaction:
    """Replace each name: removed after a role word ("my supervisor Denise said" -> "my supervisor said"), otherwise
    "a colleague" ("Can Maria approve" -> "Can a colleague approve"; "Sarah's daughter" -> "a colleague's daughter")."""
    if not text:
        return Redaction(text, 0)
    spans = find_names(text)
    out = text
    for s, e, kind in reversed(spans):
        possessive = out[s:e].endswith(("'s", "’s"))
        if kind == "role":
            out = out[:s].rstrip() + ("'s" if possessive else "") + out[e:]
        else:
            before = out[:s].rstrip()
            word = ("A colleague" if before == "" or before.endswith((".", "?", "!")) else REPLACEMENT) + ("'s" if possessive else "")
            out = out[:s] + word + out[e:]
    return Redaction(re.sub(r"[ \t]{2,}", " ", out).strip() if spans else text, len(spans))


def redact_context(turns: Optional[List[Dict[str, str]]]) -> Tuple[Optional[List[Dict[str, str]]], int]:
    """The earlier conversation turns sent with a follow-up question, each with names replaced."""
    if not turns:
        return turns, 0
    out, total = [], 0
    for turn in turns:
        r = redact(str(turn.get("content", "")))
        total += r.removed
        out.append({**turn, "content": r.text})
    return out, total
