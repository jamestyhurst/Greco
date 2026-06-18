"""Commentary-refs health checks — the testing protocol for commentary additions.

Parallel to test_knowledge_corpus_health.py for the knowledge corpus:
these tests run automatically in the pytest suite and act as a gate against
broken or incomplete commentary reference folders.

Checks:
  1. The house style guide (GRECO_STYLE.md) is loadable and non-empty.
  2. Every non-example, non-placeholder commentary folder has a real transcript
     (not a stub) and a meta.json with the required fields.
  3. load_commentary_references() returns content when refs are present.
  4. The loaded content carries the ABSOLUTE RULE guard (no chess facts from refs).

Run manually after adding a new folder:
  pytest tests/test_commentary.py -v
Or use the verification script:
  python tools/verify_commentary_addition.py <folder-slug>
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import commentary
from commentary import REFS_DIR, load_style_guide, load_commentary_references


# ── 1. Style guide ────────────────────────────────────────────────────────────

def test_style_guide_is_loadable():
    """GRECO_STYLE.md must exist and load without error."""
    text = load_style_guide()
    assert text, (
        "load_style_guide() returned empty. "
        "Ensure commentary_refs/GRECO_STYLE.md exists and is non-empty."
    )


def test_style_guide_contains_required_sections():
    """The style guide must describe both source voices."""
    text = load_style_guide()
    assert "Agadmator" in text, "Style guide missing Agadmator voice description"
    assert "SammyChess" in text, "Style guide missing SammyChess voice description"


# ── 2. Per-folder health ──────────────────────────────────────────────────────

def _commentary_folders() -> list[Path]:
    """Return all active (non-_-prefixed, non-.-prefixed) commentary folders."""
    if not REFS_DIR.is_dir():
        return []
    return [
        sub for sub in sorted(REFS_DIR.iterdir())
        if sub.is_dir() and not sub.name.startswith(("_", "."))
    ]

COMMENTARY_FOLDERS = _commentary_folders()
FOLDER_NAMES = [f.name for f in COMMENTARY_FOLDERS]


@pytest.mark.parametrize("folder_name", FOLDER_NAMES)
def test_transcript_exists(folder_name):
    folder = REFS_DIR / folder_name
    assert (folder / "transcript.txt").exists(), (
        f"{folder_name}: missing transcript.txt. "
        "Either fetch the transcript or prefix the folder with '_' to mark it as inactive."
    )


@pytest.mark.parametrize("folder_name", FOLDER_NAMES)
def test_transcript_is_not_a_placeholder(folder_name):
    path = REFS_DIR / folder_name / "transcript.txt"
    if not path.exists():
        pytest.skip("no transcript.txt (caught by test_transcript_exists)")
    text = path.read_text(encoding="utf-8").strip()
    assert not text.upper().startswith("PLACEHOLDER"), (
        f"{folder_name}: transcript.txt is a placeholder stub — fetch the real transcript "
        "or prefix the folder with '_' to exclude it from the active pool."
    )
    assert len(text) >= 200, (
        f"{folder_name}: transcript.txt has only {len(text)} chars — "
        "this looks like a stub; a real transcript should be substantially longer."
    )


@pytest.mark.parametrize("folder_name", FOLDER_NAMES)
def test_meta_json_exists_and_is_valid(folder_name):
    path = REFS_DIR / folder_name / "meta.json"
    assert path.exists(), (
        f"{folder_name}: missing meta.json. "
        "Create it with at minimum: title, commentator, video_id, channel_verified."
    )
    try:
        meta = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        pytest.fail(f"{folder_name}: meta.json parse error: {exc}")
    required = {"title", "commentator", "video_id", "channel_verified"}
    missing = required - meta.keys()
    assert not missing, (
        f"{folder_name}: meta.json missing required fields: {missing}"
    )


@pytest.mark.parametrize("folder_name", FOLDER_NAMES)
def test_channel_is_sammy_or_agadmator(folder_name):
    """Only SammyChess and Agadmator are in the approved style pool."""
    path = REFS_DIR / folder_name / "meta.json"
    if not path.exists():
        pytest.skip("no meta.json")
    meta = json.loads(path.read_text(encoding="utf-8"))
    commentator = meta.get("commentator", "").lower()
    approved = {"sammychess", "agadmator"}
    assert any(a in commentator for a in approved), (
        f"{folder_name}: commentator '{meta.get('commentator')}' is not in the approved "
        "pool (SammyChess or Agadmator). Per WORKFLOW.md rule 2: Greco's voice draws "
        "only from these two styles. Prefix the folder with '_' if you are experimenting."
    )


# ── 3. Loader output ──────────────────────────────────────────────────────────

def test_load_commentary_references_returns_content_when_refs_present():
    """If valid refs exist, the loader must return a non-empty block."""
    # Only meaningful when there is at least one valid ref.
    has_valid = any(
        (REFS_DIR / name / "transcript.txt").exists() and
        len((REFS_DIR / name / "transcript.txt").read_text(encoding="utf-8").strip()) >= 200
        for name in FOLDER_NAMES
    )
    if not has_valid:
        pytest.skip("no valid commentary refs present")
    block = load_commentary_references()
    assert block, "load_commentary_references() returned empty despite valid refs being present"


def test_loaded_block_contains_absolute_rule_guard():
    """The loaded block must carry the ABSOLUTE RULE against importing chess facts."""
    block = load_commentary_references()
    if not block:
        pytest.skip("no commentary refs loaded")
    assert "ABSOLUTE RULE" in block, (
        "The loaded commentary block is missing the ABSOLUTE RULE safety guard. "
        "This guard prevents the narrator from importing chess facts from style refs."
    )
