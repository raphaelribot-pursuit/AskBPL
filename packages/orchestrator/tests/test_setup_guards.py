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


@pytest.mark.skipif(shutil.which("git") is None or not (REPO / ".git").exists(), reason="needs git and a git checkout")
def test_the_baseline_record_points_at_a_real_commit_and_a_comparison_script() -> None:
    record = (DOCS / "BASELINE_2026-10-31.md").read_text(encoding="utf-8")
    commit = re.search(r"Evaluated commit \| `([0-9a-f]{7,40})`", record).group(1)
    subprocess.run(["git", "cat-file", "-e", f"{commit}^{{commit}}"], cwd=REPO, check=True)
    assert (REPO / "scripts" / "compare_runs.py").exists()
    for f in re.findall(r"eval_\d{8}T\d{6}Z_[0-9a-f]+_live_default-staff\.json", record):
        assert commit in f, f"{f} was not recorded on the evaluated commit"


@pytest.mark.skipif(shutil.which("git") is None or not (REPO / ".git").exists(), reason="needs git and a git checkout")
def test_every_commit_in_the_change_log_exists_and_the_rows_run_oldest_first() -> None:
    log = (DOCS / "CHANGE_LOG.md").read_text(encoding="utf-8")
    hashes = set(re.findall(r"`([0-9a-f]{7})`", log))
    assert len(hashes) > 40
    for h in sorted(hashes):
        subprocess.run(["git", "cat-file", "-e", f"{h}^{{commit}}"], cwd=REPO, check=True)
    dates = re.findall(r"^\| (2026-\d\d-\d\d) \|", log, flags=re.M)
    # One known out-of-order pair: 0028 was committed 2026-10-29 but merged before the 2026-10-28 lock-file commit.
    out_of_order = [(a, b) for a, b in zip(dates, dates[1:]) if b < a]
    assert out_of_order == [("2026-10-29", "2026-10-28")], out_of_order


def test_the_handover_guide_names_only_real_commands_documents_tests_and_settings() -> None:
    """docs/HANDOVER.md is BPL's entry point (NFR-6, patch 0042); everything it names must exist."""
    import tomllib

    guide = (DOCS / "HANDOVER.md").read_text(encoding="utf-8")
    scripts = set(tomllib.loads((ORCH / "pyproject.toml").read_text())["project"]["scripts"])
    named_commands = set(re.findall(r"\b(askbpl-[a-z-]+)\b", guide))
    assert named_commands and named_commands <= scripts, named_commands - scripts
    for doc in set(re.findall(r"`(docs/[A-Za-z0-9_./-]+\.md)`", guide)):
        assert (REPO / doc).exists(), doc
    for test in set(re.findall(r"`?(test_[a-z0-9_]+\.py)`?", guide)) | set(re.findall(r"`tests/(test_[a-z0-9_]+\.py)`", guide)):
        assert (ORCH / "tests" / test).exists(), test
    for web_test in set(re.findall(r"`([A-Za-z]+\.test\.tsx)`", guide)):
        assert list((REPO / "packages" / "web-demo" / "src").rglob(web_test)), web_test
    settings = set(re.findall(r"^([A-Z_]+)=", (REPO / ".env.example").read_text(), flags=re.M))
    from ask_bpl_orchestrator.config import Settings
    settings |= {name.upper() for name in Settings.model_fields}
    for name in set(re.findall(r"`([A-Z][A-Z_]{3,})`", guide)) - {"P0"}:
        assert name in settings or name.startswith("VITE_"), name
    assert not re.search(r"sk-[A-Za-z0-9]{8,}|pcsk_[A-Za-z0-9]{8,}", guide)  # no key ever pasted into the guide
