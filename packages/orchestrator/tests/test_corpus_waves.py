"""Guards for the staged ingestion of the 21 received-but-unevaluated documents (patch 0029 onward).

What these tests pin (docs/CORPUS_WAVES.md has the reasoning):
  * every wave manifest entry is a real file, byte-identical to the copy BPL supplied, and a row in the inventory
    workbook whose parse check passed and whose lifecycle can still answer;
  * the nine documents the team chose to HOLD back are in no wave manifest and have no file in any wave folder;
  * each manifest `policy` slug exists in routing_seed.yaml with at least one proposed rule that names an existing team
    (no team is invented, RTG-4);
  * the workbook is either before or after a wave's hand edit, never half of it, and the held rows are never marked
    as test-index members.

The tests are written to hold both before and after the curator edits the workbook by hand (the workbook is the
curator's file, so this patch does not ship one). They never touch a database or an outside service.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

import openpyxl
import pytest
import yaml

from ask_bpl_orchestrator.db.models import Eligibility
from ask_bpl_orchestrator.ingest.inventory import load_inventory, normalize_name

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "sample_corpus"
INVENTORY = CORPUS / "AskBPL_Source_Inventory_v0_1.xlsx"
ROUTING = ROOT / "config" / "routing_seed.yaml"

# The eight documents that were in the pilot index before the waves (docs/CORPUS_WAVES.md section 1).
PILOT = {"SRC-03", "SRC-05", "SRC-06", "SRC-10", "SRC-13", "SRC-14", "SRC-16", "SRC-22"}

# Held back on 2026-10-31 (team decision, section 3 of docs/CORPUS_WAVES.md). Putting one in a wave is a decision to
# make deliberately: change this set and the document together.
HELD = {
    "SRC-01": "emergency response, 2002 contact numbers (OD-03)",
    "SRC-07": "emergency closing, 2002 telephone tree (OD-03)",
    "SRC-23": "crisis management, 2008 contacts (OD-03)",
    "SRC-04": "1995 mileage rate",
    "SRC-25": "1974 manual, blank policy number and dates",
    "SRC-20": "design deck, not a policy (ING-10)",
    "SRC-29": "supporting guidance for an unsettled policy (OD-02)",
    "SRC-30": "draft marked 'Issued: June 2026 (TBD)' (OD-02)",
    "SRC-15": "named as superseded by SRC-11, Promotional and Marketing Materials (2020) (ING-12)",
}

# manifest file -> {file name: (source id, sha-256 of the supplied copy)}
WAVES = {
    "corpus_manifest_wave1.yaml": {
        "01 - Policy for Policy Management.pdf": ("SRC-02", "a69148971ae06e82f9f40b2e450d34c5a193b6f11caaa1e0fc184674355f3dad"),
        "02d - Collection Maintenance Procedures (updated 2026).pdf": ("SRC-08", "beca4ab55306ee3f6a140ec9933cc570f8cd633df402c52a2ea15135738a23ad"),
        "03 - Internal Communications Policy and Norms (10.24) (2).pdf": ("SRC-09", "289873203651dc29e5a0bac467f2922b1a0b0e0e366a262bac59c29cd0f4d7f6"),
        "04 - Promotional and Marketing Materials (05.20) (1).pdf": ("SRC-11", "b54fe9af87f5b11777e959d6c9329cb8284f5ec56cb8f53b8d19ddc63a114848"),
        "09 - Dress Code Policy (06.06).pdf": ("SRC-17", "28bd212c4059070ee6951563a34917326202b697dad2c9e5c09b20447c8f4def"),
        "12 - Custodianship of Library Materials (02.08) (1).pdf": ("SRC-21", "931182924461e3f235fa458746d5d237b7b6ba95b9f5ee2705cd92a50a5438fa"),
        "26 - Social Media Policy (03.22) (1).pdf": ("SRC-27", "6b5d499c276e6a51410da49fc8d02f0ea68dba6bde5c3e9e02e5a1930d887a12"),
    },
}


def _manifest(name: str) -> dict:
    return yaml.safe_load((CORPUS / name).read_text())


def _wave_ids(manifest_name: str) -> set[str]:
    return {sid for sid, _ in WAVES[manifest_name].values()}


def _all_wave_ids() -> set[str]:
    return set().union(*(_wave_ids(m) for m in WAVES))


def _by_id() -> dict:
    return {r.source_id: r for r in load_inventory(INVENTORY).values()}


def test_every_wave_manifest_on_disk_is_pinned_in_this_test() -> None:
    """A new manifest_wave file cannot appear without its file names, source ids and hashes being pinned here."""
    on_disk = {p.name for p in CORPUS.glob("corpus_manifest_wave*.yaml")}
    assert on_disk == set(WAVES)


@pytest.mark.parametrize("manifest_name", sorted(WAVES))
def test_manifest_lists_exactly_the_pinned_files(manifest_name: str) -> None:
    m = _manifest(manifest_name)
    listed = [d["path"] for d in m["documents"]]
    assert sorted(listed) == sorted(WAVES[manifest_name])
    assert len(set(listed)) == len(listed)
    for d in m["documents"]:
        assert d.get("title") and d.get("version") and d.get("policy")
        assert not d.get("validated_extraction"), "no wave document is a scan; none needs a validated record"


@pytest.mark.parametrize("manifest_name", sorted(WAVES))
def test_files_exist_and_are_byte_identical_to_the_supplied_copies(manifest_name: str) -> None:
    folder = CORPUS / _manifest(manifest_name)["corpus_root"]
    assert sorted(p.name for p in folder.glob("*")) == sorted(WAVES[manifest_name]), "unlisted or missing file"
    for name, (sid, sha) in WAVES[manifest_name].items():
        assert hashlib.sha256((folder / name).read_bytes()).hexdigest() == sha, f"{sid}: file differs from the supplied copy"


@pytest.mark.parametrize("manifest_name", sorted(WAVES))
def test_each_entry_matches_its_inventory_row_which_can_still_answer(manifest_name: str) -> None:
    inv = load_inventory(INVENTORY)
    for name, (sid, _sha) in WAVES[manifest_name].items():
        row = inv.get(normalize_name(name))
        assert row is not None, f"{name}: no inventory row"
        assert row.source_id == sid
        assert row.eligibility == Eligibility.authority_pending, f"{sid}: must stay Authority pending (nothing is BPL-confirmed)"
        wb = openpyxl.load_workbook(INVENTORY, read_only=True)["Source Inventory"]
        parse = next(r[5] for r in wb.iter_rows(min_row=2, values_only=True) if r[0] == sid)
        assert str(parse).lower().startswith("pass"), f"{sid}: parse check did not pass"


def test_held_documents_are_in_no_manifest_and_have_no_file_in_a_wave_folder() -> None:
    inv = _by_id()
    held_names = {normalize_name(inv[sid].file_name) for sid in HELD}
    assert len(held_names) == len(HELD)
    for manifest_name in WAVES:
        m = _manifest(manifest_name)
        assert not {normalize_name(d["path"]) for d in m["documents"]} & held_names
        folder = CORPUS / m["corpus_root"]
        assert not {normalize_name(p.name) for p in folder.glob("*")} & held_names
    for any_manifest in CORPUS.glob("corpus_manifest*.yaml"):
        listed = {normalize_name(d["path"]) for d in yaml.safe_load(any_manifest.read_text()).get("documents", [])}
        assert not listed & held_names, f"{any_manifest.name} names a held document"


def test_wave_held_and_pilot_sets_are_disjoint_and_cover_the_inventory_exactly() -> None:
    inv = _by_id()
    waves, held = _all_wave_ids(), set(HELD)
    assert not (waves & held) and not (waves & PILOT) and not (held & PILOT)
    excluded = {sid for sid, r in inv.items() if r.eligibility == Eligibility.excluded}
    assert excluded == {"SRC-28"}  # the test script is not a policy
    unplaced = set(inv) - PILOT - waves - held - excluded
    # Documents not yet in a wave (waves not built yet) are the only ones allowed to be unplaced.
    assert unplaced == {"SRC-12", "SRC-18", "SRC-19", "SRC-24", "SRC-26"} - waves


def test_the_workbook_is_never_half_edited_and_held_rows_are_never_members() -> None:
    inv = _by_id()
    members = {sid for sid, r in inv.items() if r.test_index_member}
    assert not members & set(HELD), "a held document is marked as a test-index member in the workbook"
    # SRC-13 is a member only once its scan is activated (DEC-15); that is pinned in test_eligibility.py, not here.
    assert PILOT - {"SRC-13"} <= members
    assert members <= PILOT | _all_wave_ids(), "a document outside the pilot and the waves is marked as a member"
    for manifest_name in WAVES:
        marked = _wave_ids(manifest_name) & members
        assert marked in (set(), _wave_ids(manifest_name)), f"{manifest_name}: only part of the wave is marked in the workbook"


def test_marking_a_wave_in_a_copy_of_the_workbook_makes_exactly_that_wave_answerable(tmp_path: Path) -> None:
    """The hand edit the curator makes (G = Yes on the wave's rows) and nothing else: only those rows join the index."""
    wb = openpyxl.load_workbook(INVENTORY)
    ws = wb["Source Inventory"]
    header = [c.value for c in ws[1]]
    col = header.index("In current pilot index")
    before = {sid: r.test_index_member for sid, r in _by_id().items()}
    for manifest_name in WAVES:
        ids = _wave_ids(manifest_name)
        for row in ws.iter_rows(min_row=2):
            if row[0].value in ids:
                row[col].value = "Yes"
    copy = tmp_path / "inventory_marked.xlsx"
    wb.save(copy)
    after = {r.source_id: r for r in load_inventory(copy).values()}
    for sid, r in after.items():
        if sid in _all_wave_ids():
            assert r.test_index_member and r.eligibility == Eligibility.authority_pending
        else:
            assert r.test_index_member == before[sid], f"{sid} changed although it is not in a wave"


def test_routing_has_a_slug_and_a_proposed_rule_for_every_wave_document() -> None:
    cfg = yaml.safe_load(ROUTING.read_text())
    slugs = [t["slug"] for t in cfg["policy_types"]]
    assert len(slugs) == len(set(slugs)), "duplicate slug"
    teams = {t["key"] for t in cfg["teams"]}
    for manifest_name in WAVES:
        for d in _manifest(manifest_name)["documents"]:
            assert re.fullmatch(r"[a-z][a-z0-9_]*", d["policy"])
            assert d["policy"] in slugs, f"{d['policy']}: missing from routing_seed.yaml"
            rules = [r for r in cfg["routing_rules"] if r["policy_type_slug"] == d["policy"]]
            assert rules, f"{d['policy']}: no routing rule (staff would get no referral)"
            assert all(r["team_key"] in teams for r in rules), f"{d['policy']}: a rule names a team that does not exist"


def test_the_routing_seed_does_not_pre_approve_anything() -> None:
    """Approval is set only by SEED_AUTO_APPROVE_ROUTING or the admin console, never by the file (RTG-3, RTG-5)."""
    cfg = yaml.safe_load(ROUTING.read_text())
    for rule in cfg["routing_rules"]:
        assert not {"selvon_approved", "approved", "approved_at", "approved_by"} & set(rule)
    for team in cfg["teams"]:
        assert not {"selvon_approved", "approved", "approved_at", "approved_by"} & set(team)


def _marked_copy(tmp_path: Path, ids: set[str]) -> Path:
    wb = openpyxl.load_workbook(INVENTORY)
    ws = wb["Source Inventory"]
    col = [c.value for c in ws[1]].index("In current pilot index")
    for row in ws.iter_rows(min_row=2):
        if row[0].value in ids:
            row[col].value = "Yes"
    out = tmp_path / "inventory_marked.xlsx"
    wb.save(out)
    return out


@pytest.mark.parametrize("manifest_name", sorted(WAVES))
async def test_batch_ingest_accepts_every_wave_entry_with_its_row_once_the_workbook_is_marked(manifest_name: str, tmp_path: Path) -> None:
    """The real batch loader, with the outside calls replaced: nothing is refused or failed, and each file is passed
    with the inventory row that carries its own source id and marks it a test-index member."""
    from unittest.mock import patch

    from ask_bpl_orchestrator.ingest import batch

    calls: list = []

    async def fake_ingest(**kw):
        calls.append(kw)

    inventory = _marked_copy(tmp_path, _wave_ids(manifest_name))
    with patch.object(batch, "ingest_file", side_effect=fake_ingest):
        lines = await batch.ingest_manifest(CORPUS / manifest_name, inventory)

    assert [l for l in lines if l.startswith(("refused:", "failed:"))] == []
    assert len(calls) == len(WAVES[manifest_name])
    got = {Path(str(c["absolute_path"])).name: c["inventory_row"].source_id for c in calls}
    assert got == {name: sid for name, (sid, _) in WAVES[manifest_name].items()}
    assert all(c["inventory_row"].test_index_member for c in calls)
    assert all(c["validated_extraction"] is None for c in calls)
