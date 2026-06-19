"""Tests for the Layer-2 claim-verification harness — pure, no engine, no API key.

The deterministic detectors are precision-critical (a false alarm in a CI gate is
worse than a miss), so most tests assert the harness does NOT fire on legitimate prose,
alongside the true-positive cases. The LLM judge's pure helpers (item assembly, response
parsing) are tested; the network call is not.
"""
import factcheck as FC
from factcheck import (
    bind_span_to_ply,
    check_geometry,
    check_material,
    check_piece_square,
    verify_report,
)


def _pkt(**kw):
    base = {"ply": 47, "move_no": 24, "side": "Black", "played": "Kg7", "tier": 2}
    base.update(kw)
    return base


# --- ply binding (the precision gate) ---------------------------------------
def test_bind_single_reference():
    pk = _pkt()
    assert bind_span_to_ply("A fine idea, **24...Kg7**, centralising.", [pk]) is pk


def test_bind_abstains_on_two_references():
    pk1, pk2 = _pkt(move_no=12, side="White", played="Nxd4"), _pkt(move_no=14, side="White", played="e5")
    assert bind_span_to_ply("After **12. Nxd4** and **14. e5** White is better.", [pk1, pk2]) is None


def test_bind_none_when_unresolvable():
    assert bind_span_to_ply("**24...Kg7** is interesting.", [_pkt(played="Rf8")]) is None


# --- geometry ---------------------------------------------------------------
def test_geometry_flags_onto_file_already_there():
    pk = _pkt(played="Kg7")
    pk["from"], pk["to"] = "g8", "g7"
    out = list(check_geometry(pk, "Black slides the king onto the g-file."))
    assert len(out) == 1 and "g-file" in out[0].claim


def test_geometry_no_flag_castling_genuinely_changes_file():
    pk = _pkt(move_no=14, side="White", played="O-O")
    pk["from"], pk["to"] = "e1", "g1"
    assert list(check_geometry(pk, "O-O tucks the king onto the g-file.")) == []


def test_geometry_no_flag_control_verb():
    pk = _pkt(move_no=15, side="White", played="Rg1")
    pk["from"], pk["to"] = "f1", "g1"
    assert list(check_geometry(pk, "The rook seizes the g-file.")) == []


def test_geometry_no_flag_rank_genuinely_changed():
    pk = _pkt(played="Kg7")
    pk["from"], pk["to"] = "g8", "g7"
    assert list(check_geometry(pk, "The king steps onto the 7th rank.")) == []


def test_geometry_no_flag_different_piece_onto_file():
    # Bound to a KING move that stays on the g-file, but the 'onto' clause is about a ROOK.
    pk = _pkt(played="Kg7")
    pk["from"], pk["to"] = "g8", "g7"
    assert list(check_geometry(pk, "The rook now slides onto the g-file to contest it.")) == []


def test_geometry_no_flag_different_piece_onto_rank():
    # Bound to a rook 'on' rank 7, but the 'onto the 7th rank' clause is about the queen.
    pk = _pkt(move_no=20, side="White", played="Rc7")
    pk["from"], pk["to"] = "c7", "c7"
    assert list(check_geometry(pk, "The queen too will come onto the 7th rank.")) == []


# --- piece_square -----------------------------------------------------------
def _pieces_pkt(**kw):
    pk = _pkt(**kw)
    pk["pieces"] = "White K:g1 N:e4 P:d3 | Black K:g8 R:f8"
    pk["to"] = "g7"
    return pk


def test_piece_square_flags_mislocated_piece():
    out = list(check_piece_square(_pieces_pkt(), "The knight on c5 is loose."))
    assert len(out) == 1 and "c5" in out[0].claim


def test_piece_square_no_flag_past_tense():
    assert list(check_piece_square(_pieces_pkt(), "The knight, formerly on c5, now eyes d6.")) == []


def test_piece_square_no_flag_destination_square():
    pk = _pieces_pkt()
    pk["to"] = "e4"
    assert list(check_piece_square(pk, "This plants the knight on e4.")) == []


def test_piece_square_no_flag_captured_type_absent():
    # No bishop anywhere on the board -> a 'bishop on g4' is a legit past/captured ref.
    assert list(check_piece_square(_pieces_pkt(), "His bishop on g4 was the problem.")) == []


def test_piece_square_no_flag_displacement_prose():
    # Naming a piece's PRE-move square while describing the move that evicted it.
    assert list(check_piece_square(_pieces_pkt(), "The knight on c5 was undermined and forced to a6.")) == []


# --- material ---------------------------------------------------------------
def test_material_flags_ahead_when_behind():
    pk = _pkt(side="Black", material=3.0)  # White +3 -> Black is down 3
    out = list(check_material(pk, "You are up a clean pawn here."))
    assert len(out) == 1


def test_material_no_flag_sound_sac_framing():
    pk = _pkt(side="Black", material=3.0)
    assert list(check_material(pk, "Black is down a piece but winning.")) == []


def test_material_no_flag_exchange():
    pk = _pkt(side="Black", material=3.0)
    assert list(check_material(pk, "Black is up the exchange.")) == []


def test_material_no_flag_future_tactic():
    pk = _pkt(side="Black", material=3.0)  # down now, but the win is next move
    assert list(check_material(pk, "Black wins a piece next move with Nxe4.")) == []


def test_material_no_flag_wins_back_to_equality():
    pk = _pkt(side="Black", material=3.0)
    assert list(check_material(pk, "Black wins a pawn back to reach equality.")) == []


# --- verify_report integration (binding + abstain) --------------------------
def test_verify_report_clean_is_empty():
    pk = _pkt(played="Kg7")
    pk["from"], pk["to"] = "g8", "g7"
    body = "## Walkthrough\n\nThe king heads for safety with **24...Kg7**, eyeing the centre.\n"
    report = "# Title\n\n---\n\n" + body
    assert verify_report(report, [pk]) == []


def test_verify_report_flags_geometry_bug():
    pk = _pkt(played="Kg7")
    pk["from"], pk["to"] = "g8", "g7"
    report = "# Title\n\n---\n\nA slip: **24...Kg7** moves the king onto the g-file for no reason.\n"
    found = verify_report(report, [pk])
    assert any(f.check == "geometry" for f in found)


def test_verify_report_skips_hypothetical_sentence():
    pk = _pkt(played="Kg7")
    pk["from"], pk["to"] = "g8", "g7"
    # 'if' marks a hypothetical -> the geometry claim is about a line, not the board.
    report = "# T\n\n---\n\nIf **24...Kg7** moves onto the g-file, problems follow.\n"
    assert verify_report(report, [pk]) == []


# --- variation check (delegates to the legal-from-branch validator) ---------
# Real FENs: the validator replays moves on actual boards (Qh8 is illegal here — no
# queen exists), so it FLAGs the line. See docs/specs/VARIATION_VALIDATOR.md.
def test_check_variations_flags_illegal_move(make_move, make_game):
    m = make_move(side="Black", move_number=24, san="Kg7", uci="g8g7",
                  fen_before="6k1/5p1p/8/8/8/8/5PPP/6K1 b - - 0 24",
                  fen_after="8/5pkp/8/8/8/8/5PPP/6K1 w - - 1 25")
    game = make_game([m])
    report = "This runs into *(25. Qh8 winning)*."
    found = FC.check_variations(report, game)
    assert any(f.check == "variation" and f.confidence == "high" for f in found)
    assert any("Qh8" in f.claim for f in found)


# --- LLM-judge pure helpers (no network) ------------------------------------
def test_build_judge_items_maps_and_skips_tier0(make_move, make_game):
    m1 = make_move(ply=1, move_number=1, side="White", san="e4")
    m2 = make_move(ply=2, move_number=1, side="Black", san="e5")
    game = make_game([m1, m2])
    report = "# T\n\n---\n\nThe game opens with **1. e4**, the classical choice.\n"
    items = FC.build_judge_items(game, [2, 0], report)  # m2 is tier 0 -> skipped
    assert len(items) == 1 and items[0]["played"] == "e4"


def test_parse_judge_response():
    canned = ('Here you go: {"contradictions":[{"move_no":24,"side":"Black",'
              '"claim_text":"king onto g-file","contradicted_fact":"already on g","confidence":0.9}]}')
    out = FC._parse_judge_response(canned)
    assert len(out) == 1 and out[0].check == "llm-judge" and "g-file" in out[0].claim


def test_parse_judge_response_empty_on_garbage():
    assert FC._parse_judge_response("no json here") == []
