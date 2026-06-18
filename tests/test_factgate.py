"""Tests for the Output Fact-Gate predicate library — pure, no engine, no API key.

This is the L1 (structural-correctness) half of the testing doctrine: every predicate
is checked with a POSITIVE position and at least one TRAP that must NOT certify,
including the named hallucination classes (a king "already on the file", an enemy pawn
that can still challenge an outpost). Wrappers are parity-locked to the analyzer
detectors so the allow-set can never drift from the fact packet.
"""
import chess

import factgate as F
from analyzer import detect_double_attack, detect_royal_alignment, file_structure


# --- threatens_mate_in_one --------------------------------------------------
def test_mate_in_one_true_on_back_rank():
    assert F.threatens_mate_in_one(chess.Board("6k1/5ppp/8/8/8/8/8/3R2K1 w - - 0 1")) is True


def test_mate_in_one_false_quiet():
    assert F.threatens_mate_in_one(chess.Board()) is False


def test_mate_in_one_false_check_that_is_not_mate():
    # White Qd1-d8+ is check but the king escapes; not mate.
    assert F.threatens_mate_in_one(chess.Board("4k3/8/8/8/8/8/8/3QK3 w - - 0 1")) is False


# --- is_rook_lift -----------------------------------------------------------
def _push(fen, uci):
    b = chess.Board(fen)
    mv = chess.Move.from_uci(uci)
    after = b.copy()
    after.push(mv)
    return b, mv, after


def test_rook_lift_true_open_file():
    b, mv, a = _push("4k3/8/8/8/8/8/8/3RK3 w - - 0 1", "d1d3")
    ok, ev = F.is_rook_lift(b, mv, a)
    assert ok and "d-file" in ev


def test_rook_lift_false_king_already_on_file():
    # The canonical bug: a king playing Kg7 from g8 is NOT a lift (and isn't a rook).
    b, mv, a = _push("6k1/8/8/8/8/8/8/4K3 b - - 0 1", "g8g7")
    assert F.is_rook_lift(b, mv, a) == (False, None)


def test_rook_lift_false_sideways_no_forward_change():
    b, mv, a = _push("4k3/8/8/8/8/8/8/R3K3 w - - 0 1", "a1c1")
    assert F.is_rook_lift(b, mv, a)[0] is False


def test_rook_lift_false_capture():
    b, mv, a = _push("4k3/8/8/8/8/8/3r4/3RK3 w - - 0 1", "d1d2")
    assert F.is_rook_lift(b, mv, a)[0] is False


# --- is_outpost -------------------------------------------------------------
def test_outpost_true_supported_unchallengeable():
    ok, sup = F.is_outpost(chess.Board("4k3/8/8/4N3/3P4/8/8/4K3 w - - 0 1"), chess.E5, chess.WHITE)
    assert ok and chess.D4 in sup


def test_outpost_false_challengeable():
    # A black d-pawn on d7 can play ...d6 to attack e5 -> not a true outpost.
    assert F.is_outpost(chess.Board("3pk3/8/8/4N3/3P4/8/8/4K3 w - - 0 1"), chess.E5, chess.WHITE)[0] is False


def test_outpost_false_not_a_minor():
    assert F.is_outpost(chess.Board("4k3/8/8/4R3/3P4/8/8/4K3 w - - 0 1"), chess.E5, chess.WHITE)[0] is False


# --- is_passed_pawn ---------------------------------------------------------
def test_passed_pawn_true():
    assert F.is_passed_pawn(chess.Board("4k3/8/4P3/8/8/8/8/4K3 w - - 0 1"), chess.E6, chess.WHITE) is True


def test_passed_pawn_false_adjacent_enemy_ahead():
    assert F.is_passed_pawn(chess.Board("4k3/5p2/4P3/8/8/8/8/4K3 w - - 0 1"), chess.E6, chess.WHITE) is False


def test_passed_pawn_false_same_file_blocker():
    assert F.is_passed_pawn(chess.Board("4k3/4p3/4P3/8/8/8/8/4K3 w - - 0 1"), chess.E6, chess.WHITE) is False


# --- wrappers parity (anti-drift lock) --------------------------------------
def test_creates_fork_parity_with_analyzer():
    b = chess.Board(None)
    b.set_piece_at(chess.E6, chess.Piece(chess.KNIGHT, chess.WHITE))
    b.set_piece_at(chess.G7, chess.Piece(chess.KING, chess.BLACK))
    b.set_piece_at(chess.C7, chess.Piece(chess.QUEEN, chess.BLACK))
    b.set_piece_at(chess.A1, chess.Piece(chess.KING, chess.WHITE))
    ok, ev = F.creates_fork(b, chess.E6, chess.WHITE)
    assert ok is (detect_double_attack(b, chess.E6, chess.WHITE) is not None)
    assert ev == detect_double_attack(b, chess.E6, chess.WHITE)


def test_sets_up_royal_pin_parity_with_analyzer():
    b = chess.Board(None)
    b.set_piece_at(chess.G1, chess.Piece(chess.ROOK, chess.WHITE))
    b.set_piece_at(chess.G4, chess.Piece(chess.QUEEN, chess.BLACK))
    b.set_piece_at(chess.G8, chess.Piece(chess.KING, chess.BLACK))
    b.set_piece_at(chess.H1, chess.Piece(chess.KING, chess.WHITE))
    ok, ev = F.sets_up_royal_pin(b, chess.WHITE)
    assert ok is (detect_royal_alignment(b, chess.WHITE) is not None)
    assert ev == detect_royal_alignment(b, chess.WHITE)  # evidence-locked, not just boolean


def test_file_state_parity():
    b = chess.Board("4k3/8/8/8/8/8/8/3RK3 w - - 0 1")  # no pawns -> all files open
    files = file_structure(b)
    assert F.file_state(b, chess.FILE_NAMES.index("d"), chess.WHITE) == "open_file"
    assert "d" in files["open"]


# --- certified_claims (the allow-set) ---------------------------------------
def test_certified_claims_collects_tags():
    b, mv, a = _push("4k3/8/8/8/8/8/8/3RK3 w - - 0 1", "d1d3")
    tags = F.certified_claims(b, mv, a, chess.WHITE)
    assert "rook_lift" in tags
    assert "open_file" not in tags  # files are governed by their own packet field, not the gate


def test_certified_claims_no_false_mate_threat_when_move_gives_check():
    # Qd6+ gives check; Black's ONLY reply is Kxd6 capturing the queen -> no mate exists.
    b, mv, a = _push("2K5/8/8/3Qk3/5R2/8/p7/8 w - - 0 1", "d5d6")
    assert "mate_in_one_threat" not in F.certified_claims(b, mv, a, chess.WHITE)


def test_certified_claims_empty_on_quiet_move():
    b, mv, a = _push(chess.STARTING_FEN, "g1f3")
    assert F.certified_claims(b, mv, a, chess.WHITE) == set()


def test_certified_claims_serialises_ascii():
    import json
    b, mv, a = _push("4k3/8/8/8/8/8/8/3RK3 w - - 0 1", "d1d3")
    payload = json.dumps(sorted(F.certified_claims(b, mv, a, chess.WHITE)))
    assert payload == payload.encode("ascii").decode("ascii")


def test_certified_claims_never_raises_on_legal_positions():
    # Fail-safe posture: walk a real game and certify every ply without exceptions.
    board = chess.Board()
    for uci in ("e2e4", "e7e5", "g1f3", "b8c6", "f1b5", "a7a6", "b5a4", "g8f6", "e1g1"):
        mv = chess.Move.from_uci(uci)
        before = board.copy()
        board.push(mv)
        F.certified_claims(before, mv, board, before.turn == chess.WHITE)


# --- creates_battery --------------------------------------------------------
def test_battery_true_two_rooks_same_file():
    # White rook moves from d1 to d2, joining the other white rook already on d3.
    # Board: white rooks on d1 and d3, no pawns between them.
    b, mv, a = _push("4k3/8/8/8/8/3R4/8/3RK3 w - - 0 1", "d1d2")
    ok, ev = F.creates_battery(a, mv, chess.WHITE)
    assert ok
    assert "d-file" in ev


def test_battery_true_rook_queen_same_rank():
    # White rook on e2 moves to e1, joining queen on a1 on the same rank with nothing between.
    b, mv, a = _push("4k3/8/8/8/8/8/4R3/Q4K2 w - - 0 1", "e2e1")
    ok, ev = F.creates_battery(a, mv, chess.WHITE)
    assert ok
    assert "rank 1" in ev


def test_battery_false_blocked():
    # White rooks on d1 and d3 but a pawn on d2 blocks them; moving the d1 rook to d2
    # displaces the pawn... but let's test a case where the blocker stays:
    # White rook moves to d4, other white rook on d1, pawn on d2 blocks.
    b, mv, a = _push("4k3/8/8/3R4/8/8/3P4/3RK3 w - - 0 1", "d1d3")
    # After d1-d3: rooks on d3 and d4 with nothing between them — actually this IS a battery.
    # Let's use a position where they are blocked.
    b2, mv2, a2 = _push("4k3/8/8/8/3R4/3P4/8/3RK3 w - - 0 1", "d1d2")
    # d1-d2, rooks on d2 and d4 with pawn on d3 blocking.
    ok2, _ = F.creates_battery(a2, mv2, chess.WHITE)
    assert ok2 is False


def test_battery_false_not_a_major_piece():
    # Knight move cannot form a battery (batteries are rooks/queens only).
    b, mv, a = _push("4k3/8/8/8/8/8/8/4KN1R w - - 0 1", "f1e3")
    ok, _ = F.creates_battery(a, mv, chess.WHITE)
    assert ok is False


# --- threatens_promotion ---------------------------------------------------
def test_promotion_threat_true_advance():
    # White pawn on e7, e8 empty — can advance to promote.
    b, mv, a = _push("4k3/8/8/8/8/8/4P3/4K3 w - - 0 1", "e2e4")
    # Set up a cleaner board: pawn on d7, empty d8.
    b2 = chess.Board("4k3/3P4/8/8/8/8/8/4K3 b - - 0 1")  # it's black's turn but pawn is white
    ok, ev = F.threatens_promotion(b2, chess.WHITE)
    assert ok
    assert "d-file" in ev


def test_promotion_threat_true_capture():
    # White pawn on d7, enemy rook on e8 can be captured diagonally to promote; king safe on h8.
    b = chess.Board("3rr2k/3P4/8/8/8/8/8/4K3 b - - 0 1")
    ok, ev = F.threatens_promotion(b, chess.WHITE)
    assert ok


def test_promotion_threat_false_blocked():
    # White pawn on d7, enemy piece on d8 blocks straight advance, no diagonal capture.
    b = chess.Board("3qk3/3P4/8/8/8/8/8/4K3 b - - 0 1")
    ok, _ = F.threatens_promotion(b, chess.WHITE)
    assert ok is False


def test_promotion_threat_false_no_seventh_rank_pawn():
    b = chess.Board("4k3/8/3P4/8/8/8/8/4K3 b - - 0 1")  # pawn on d6, not d7
    ok, _ = F.threatens_promotion(b, chess.WHITE)
    assert ok is False


def test_battery_in_certified_claims():
    # Rook doubles on the d-file: moving d1 rook to d2 forms a battery with d3 rook.
    b, mv, a = _push("4k3/8/8/8/8/3R4/8/3RK3 w - - 0 1", "d1d2")
    tags = F.certified_claims(b, mv, a, chess.WHITE)
    assert "battery" in tags


def test_promotion_threat_in_certified_claims():
    # White plays e6-e7 (creating the threat); black king is on h8 so e8 is empty ahead of the pawn.
    b, mv, a = _push("7k/8/4P3/8/8/8/8/4K3 w - - 0 1", "e6e7")
    tags = F.certified_claims(b, mv, a, chess.WHITE)
    assert "promotion_threat" in tags
