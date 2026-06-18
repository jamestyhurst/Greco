"""Integration test: narrator._move_to_dict → factcheck.verify_report pipeline.

Exercises the full claim-verification path that ship.py / CI guards, using
synthetic (Stockfish-free, key-free) data. Proves that the fact packets
narrator produces and the contradiction detector factcheck expects are
compatible — a regression in either breaks these tests.
"""
from factcheck import verify_report
from narrator import _move_to_dict


def _packet(make_move, **overrides):
    """Build a fact packet via the real narrator serialiser."""
    m = make_move(**overrides)
    return _move_to_dict(m, tier=2)


# --- clean report: no contradictions ----------------------------------------

def test_verify_clean_prose_returns_no_findings(make_move):
    """A sentence with accurate geometry produces zero findings."""
    # Move: e2→e4 (White, move 1)
    pkt = _packet(make_move, ply=1, move_number=1, side="White", san="e4", uci="e2e4")
    report = "---\n\n**1. e4** advances the pawn to the e4-square."
    findings = verify_report(report, [pkt])
    assert findings == []


def test_verify_correctly_stated_file_change_no_finding(make_move):
    """Moving from d1 to g4 does change the g-file — not flagged."""
    pkt = _packet(make_move, ply=3, move_number=2, side="White", san="Qg4", uci="d1g4")
    report = "---\n\n**2. Qg4** puts the queen on the g-file."
    findings = verify_report(report, [pkt])
    assert findings == []


# --- confabulated geometry: same file/rank, flagged -------------------------

def test_verify_flags_false_file_claim(make_move):
    """Claiming a move CHANGED the g-file when both squares are already on it."""
    pkt = _packet(make_move, ply=47, move_number=24, side="Black", san="Kg7", uci="g8g7")
    report = "---\n\n**24...Kg7** slides the king onto the g-file."
    findings = verify_report(report, [pkt])
    # The g8→g7 move does NOT change the file (already on g) — should be flagged
    assert len(findings) >= 1
    assert any("g-file" in f.claim for f in findings)


def test_verify_flags_false_rank_claim(make_move):
    """Claiming a move changed the 4th rank when both squares are on it."""
    pkt = _packet(make_move, ply=7, move_number=4, side="White", san="Re4", uci="a4e4")
    report = "---\n\n**4. Re4** brings the rook onto the 4th rank."
    # a4→e4: both are on rank 4 — should be flagged
    findings = verify_report(report, [pkt])
    assert any("4th rank" in f.claim or "rank" in f.claim.lower() for f in findings)


# --- no cross-contamination between plies -----------------------------------

def test_verify_does_not_apply_one_ply_claims_to_another(make_move):
    """A confabulated claim about move 24 is not incorrectly attributed to move 12."""
    pkt12 = _packet(make_move, ply=23, move_number=12, side="White", san="Nf3", uci="g1f3")
    pkt24 = _packet(make_move, ply=47, move_number=24, side="Black", san="Kg7", uci="g8g7")
    # The false-file claim is about move 24, not move 12
    report = "---\n\n**12. Nf3** deploys the knight.\n\n**24...Kg7** slides the king onto the g-file."
    findings = verify_report(report, [pkt12, pkt24])
    # Only the move-24 claim should be flagged, not move-12
    assert all(f.move_ref and "24" in f.move_ref for f in findings)
