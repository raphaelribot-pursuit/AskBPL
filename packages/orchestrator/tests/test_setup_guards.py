"""Setup guards for two failures a Windows tester hit on 2026-10-31.

1. Git for Windows converts LF to CRLF on checkout (core.autocrlf=true). Files whose exact bytes are checked by SHA-256
   (the validated text of a scanned policy; files covered by an Eligible approval) then fail their check. The repository's
   .gitattributes marks those folders -text so Git never converts them.
2. A Pinecone index created with a document schema rejects the vector writes ingest makes. The setup docs must say to
   create a plain dense index and name the error.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

ORCH = Path(__file__).resolve().parents[1]
REPO = ORCH.parents[1]
DOCS = REPO / "docs"

CHECKED_FILES = [
    "packages/orchestrator/extraction_reviews/SRC-13/validated_text.md",
    "packages/orchestrator/extraction_reviews/SRC-13/validation_record.json",
    "packages/orchestrator/sample_corpus/corpus_manifest_pilot.yaml",
    "packages/orchestrator/sample_corpus/pilot/04 - Annual Leave Policy (01.06) (1).pdf",
]


def _attr(path: str, name: str) -> str:
    out = subprocess.run(["git", "check-attr", name, "--", path], cwd=REPO, capture_output=True, text=True, check=True)
    return out.stdout.strip().rsplit(": ", 1)[-1]


@pytest.mark.skipif(shutil.which("git") is None or not (REPO / ".git").exists(), reason="needs git and a git checkout")
@pytest.mark.parametrize("path", CHECKED_FILES)
def test_files_with_checked_bytes_are_never_line_ending_converted(path: str) -> None:
    assert (REPO / path).exists(), path
    assert _attr(path, "text") == "unset", f"{path}: Git may convert its line endings on Windows"


def test_the_validated_text_in_the_repository_has_unix_line_endings() -> None:
    # The validation record's hash was taken over LF bytes; a CRLF copy committed by mistake would fail on every machine.
    assert b"\r" not in (ORCH / "extraction_reviews" / "SRC-13" / "validated_text.md").read_bytes()


@pytest.mark.parametrize("doc", ["TESTER_SETUP.md", "PINECONE_CORPUS_INGEST.md"])
def test_setup_docs_require_a_plain_dense_index_and_name_the_document_schema_error(doc: str) -> None:
    text = (DOCS / doc).read_text(encoding="utf-8")
    assert "document schema" in text and "1536" in text and "cosine" in text
    assert "This index has a document schema" in text


def test_tester_setup_explains_both_errors_and_the_safe_refresh() -> None:
    text = (DOCS / "TESTER_SETUP.md").read_text(encoding="utf-8")
    assert "validated text was changed after the review was finalized" in text
    assert "git checkout -- packages/orchestrator/extraction_reviews" in text
    assert "git config core.autocrlf false" not in text  # changing the setting floods git status on an existing checkout


@pytest.mark.parametrize("doc", ["README.md", "docs/TESTER_SETUP.md", "docs/demo_acceptance.md"])
def test_web_setup_installs_the_locked_versions(doc: str) -> None:
    # `npm install` (or `npm audit fix --force`) can rewrite package.json and the lock file; `npm ci` cannot.
    text = (REPO / doc).read_text(encoding="utf-8")
    assert "npm ci" in text
    assert not re.search(r"npm install(?! *-)", text.replace("not `npm install`", "")), f"{doc} still says npm install"
