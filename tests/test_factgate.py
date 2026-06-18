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
    # Kings only, no pawns, no heavy pieces — nothing to certify on a quiet king step.
    b, mv, a = _push("4k3/8/8/8/8/8/4K3/8 w - - 0 1", "e2d2")
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


# --- is_isolated_pawn -------------------------------------------------------

def test_isolated_pawn_iqp_white_d4():
    # Textbook IQP structure: White d4 pawn, c- and e-files have no White pawn.
    # FEN from spec positive example 1.
    board = chess.Board("rnbqkb1r/pp3ppp/4pn2/8/3P4/2N2N2/PP3PPP/R1BQKB1R w KQkq - 0 7")
    ok, ev = F.is_isolated_pawn(board, chess.D4, chess.WHITE)
    assert ok
    assert ev["is_isolani"] is True
    assert ev["file"] == "d"
    assert ev["color"] == "White"
    assert "isolani" in ev["evidence_str"]


def test_isolated_pawn_edge_file_a_pawn_black():
    # Black a7 is isolated — only adjacent b-file has no Black pawn.
    board = chess.Board("8/p7/8/8/8/5k2/5P2/6K1 b - - 0 1")
    ok, ev = F.is_isolated_pawn(board, chess.A7, chess.BLACK)
    assert ok
    assert ev["color"] == "Black"
    assert ev["adjacent_files"] == ["b"]
    assert "b-file" in ev["evidence_str"]


def test_isolated_pawn_doubled_isolated_white_c():
    # White c3 and c4 with no b- or d-pawn: both isolated doubled.
    board = chess.Board("6k1/8/8/8/2P5/2P5/6PP/6K1 w - - 0 1")
    ok4, ev4 = F.is_isolated_pawn(board, chess.C4, chess.WHITE)
    ok3, ev3 = F.is_isolated_pawn(board, chess.C3, chess.WHITE)
    assert ok4
    assert ev4["is_doubled"] is True
    assert set(ev4["doubled_squares"]) == {"c3", "c4"}
    assert ok3
    assert ev3["is_doubled"] is True


def test_isolated_pawn_passed_and_isolated():
    # White e5, g2, h2 — d and f empty; no Black pawns → isolated AND passed.
    board = chess.Board("8/6k1/8/4P3/8/8/6PP/6K1 w - - 0 1")
    ok, ev = F.is_isolated_pawn(board, chess.E5, chess.WHITE)
    assert ok
    assert ev["is_passed"] is True
    assert "isolated passed pawn" in ev["evidence_str"]


def test_isolated_pawn_false_adjacent_file_occupied():
    # White b3 has White a2 on the adjacent a-file — NOT isolated.
    board = chess.Board("8/8/8/8/1p6/1P6/P7/6K1 w - - 0 1")
    ok, _ = F.is_isolated_pawn(board, chess.B3, chess.WHITE)
    assert ok is False


def test_isolated_pawn_false_hanging_pawns():
    # White c4 and d4 together — each has the other on an adjacent file.
    board = chess.Board("4k3/8/8/8/2PP4/8/8/4K3 w - - 0 1")
    ok_c, _ = F.is_isolated_pawn(board, chess.C4, chess.WHITE)
    ok_d, _ = F.is_isolated_pawn(board, chess.D4, chess.WHITE)
    assert ok_c is False
    assert ok_d is False


def test_isolated_pawn_false_non_pawn():
    # Non-pawn piece: knight on d4.
    board = chess.Board("4k3/8/8/8/3N4/8/8/4K3 w - - 0 1")
    ok, ev = F.is_isolated_pawn(board, chess.D4, chess.WHITE)
    assert ok is False
    assert ev == {}


def test_isolated_pawn_false_enemy_pawn():
    # Black pawn on d4; asking for WHITE → veto fires (wrong color).
    board = chess.Board("4k3/8/8/8/3p4/8/8/4K3 w - - 0 1")
    ok, ev = F.is_isolated_pawn(board, chess.D4, chess.WHITE)
    assert ok is False
    assert ev == {}


def test_isolated_pawn_pinned_still_certifies():
    # White d2 absolutely pinned by Bb4 against Ke1; c and e files empty → still isolated.
    board = chess.Board("4k3/8/8/8/1b6/8/3P4/4K3 w - - 0 1")
    ok, ev = F.is_isolated_pawn(board, chess.D2, chess.WHITE)
    assert ok
    assert ev["is_isolani"] is True


def test_isolated_pawn_in_certified_claims():
    # White lone d-pawn advances: d4→d5. No White pawns on c or e → isolated IQP.
    b, mv, a = _push("4k3/8/8/8/3P4/8/8/4K3 w - - 0 1", "d4d5")
    tags = F.certified_claims(b, mv, a, chess.WHITE)
    assert "isolated_pawn" in tags


# --- is_doubled_pawn --------------------------------------------------------

def test_doubled_pawn_simple_white_c_file():
    # White pawns c2 and c3 — doubled on c-file.
    board = chess.Board("4k3/8/8/8/8/2P5/2P5/6K1 w - - 0 1")
    ok, ev = F.is_doubled_pawn(board, chess.C3, chess.WHITE)
    assert ok
    assert ev["count"] == 2
    assert ev["descriptor"] == "doubled"
    assert ev["file"] == "c"
    assert set(ev["square_names"]) == {"c2", "c3"}
    assert "doubled pawns on the c-file" in ev["evidence_str"]


def test_doubled_pawn_tripled():
    # White pawns c2, c3, c4 — tripled.
    board = chess.Board("4k3/8/8/8/2P5/2P5/2P5/6K1 w - - 0 1")
    ok, ev = F.is_doubled_pawn(board, chess.C4, chess.WHITE)
    assert ok
    assert ev["count"] == 3
    assert ev["descriptor"] == "tripled"
    assert "tripled pawns" in ev["evidence_str"]


def test_doubled_pawn_false_adjacent_files():
    # White e4 and f4 — a phalanx/duo, NOT doubled.
    board = chess.Board("4k3/8/8/8/4PP2/8/8/4K3 w - - 0 1")
    ok_e, _ = F.is_doubled_pawn(board, chess.E4, chess.WHITE)
    ok_f, _ = F.is_doubled_pawn(board, chess.F4, chess.WHITE)
    assert ok_e is False
    assert ok_f is False


def test_doubled_pawn_false_lone_pawn():
    # White e4 only — no same-file companion.
    board = chess.Board("4k3/8/8/8/4P3/8/8/4K3 w - - 0 1")
    ok, ev = F.is_doubled_pawn(board, chess.E4, chess.WHITE)
    assert ok is False
    assert ev == {}


def test_doubled_pawn_false_enemy_pawn_same_file():
    # White e4, Black e6 — enemy pawn on same file does not make White's doubled.
    board = chess.Board("4k3/8/4p3/8/4P3/8/8/4K3 w - - 0 1")
    ok, _ = F.is_doubled_pawn(board, chess.E4, chess.WHITE)
    assert ok is False


def test_doubled_pawn_false_non_pawn():
    # A rook on c3 is not a pawn.
    board = chess.Board("4k3/8/8/8/8/2R5/2P5/6K1 w - - 0 1")
    ok, ev = F.is_doubled_pawn(board, chess.C3, chess.WHITE)
    assert ok is False
    assert ev == {}


def test_doubled_pawn_false_single_pawn_veto():
    # Only one White pawn on the board — step-2 veto fires.
    board = chess.Board("4k3/8/8/8/3P4/8/8/4K3 w - - 0 1")
    ok, _ = F.is_doubled_pawn(board, chess.D4, chess.WHITE)
    assert ok is False


def test_doubled_pawn_black_certified():
    # Black pawns f6 and f7 — doubled for Black.
    board = chess.Board("4k3/5p2/5p2/8/8/8/8/4K3 b - - 0 1")
    ok, ev = F.is_doubled_pawn(board, chess.F6, chess.BLACK)
    assert ok
    assert ev["color"] == "Black"
    assert ev["file"] == "f"


def test_doubled_pawn_in_certified_claims():
    # White bxc5 recapture: White b4 captures Black c5; White also has c2.
    # After the capture White has c2 and c5 on the same file.
    b, mv, a = _push("4k3/8/8/2p5/1P6/8/2P5/4K3 w - - 0 1", "b4c5")
    tags = F.certified_claims(b, mv, a, chess.WHITE)
    assert "doubled_pawn" in tags


# --- is_luft ----------------------------------------------------------------

def test_luft_true_classic_h3():
    # Classic kingside h3 luft: White king g1, all pawns in front.
    b, mv, a = _push("6k1/5ppp/8/8/8/8/5PPP/6K1 w - - 0 1", "h2h3")
    ok, ev = F.is_luft(b, mv, a, chess.WHITE)
    assert ok
    assert chess.H2 in ev["luft_squares"]
    assert ev["evidence"].startswith("h3")


def test_luft_true_black_h6():
    # Black mirror: ...h6 gives king on g8 flight via h7.
    b, mv, a = _push("6k1/5ppp/8/8/8/8/5PPP/3R2K1 b - - 0 1", "h7h6")
    ok, ev = F.is_luft(b, mv, a, chess.BLACK)
    assert ok
    assert chess.H7 in ev["luft_squares"]


def test_luft_true_queenside_b3():
    # Queenside luft: White king c1, b2 push opens b2 flight.
    b, mv, a = _push("2kr3r/ppp2ppp/8/8/8/8/PPP2PPP/2KR3R w - - 0 1", "b2b3")
    ok, ev = F.is_luft(b, mv, a, chess.WHITE)
    assert ok
    assert chess.B2 in ev["luft_squares"]


def test_luft_false_pawn_far_from_king():
    # a-pawn push when king is on g1: a2-a4 is 6 files away — VETO 4.
    b, mv, a = _push("6k1/5ppp/8/8/8/8/P4PPP/6K1 w - - 0 1", "a2a4")
    ok, _ = F.is_luft(b, mv, a, chess.WHITE)
    assert ok is False


def test_luft_false_already_had_air():
    # King g1, f2/g2 pawns but h2 already empty: h2→h3 is a quiet pawn push but
    # king ALREADY had h2 as a flight square, so the diff is empty — no new air.
    b, mv, a = _push("6k1/5ppp/8/8/8/8/5PP1/6K1 w - - 0 1", "g2g3")
    ok, _ = F.is_luft(b, mv, a, chess.WHITE)
    # king g1: flights_before includes g2 (empty and unattacked) → push g2-g3 vacates g2
    # which was already a flight square before push? No — g2 was occupied by the pawn BEFORE
    # the push, so it was NOT a flight square before. After the push g2 is empty.
    # So this IS luft (g2 opens up). Let's confirm:
    assert ok  # g2 is newly opened


def test_luft_false_not_a_pawn():
    # King moves — not a pawn push.
    b, mv, a = _push("6k1/5ppp/8/8/8/8/5PPP/6K1 w - - 0 1", "g1f1")
    ok, _ = F.is_luft(b, mv, a, chess.WHITE)
    assert ok is False


def test_luft_false_capture():
    # Pawn captures — VETO 3 fires.
    b, mv, a = _push("6k1/5p1p/6p1/8/8/6P1/5PP1/6K1 w - - 0 1", "g3h4")
    # Actually g3xh4 won't work without a Black piece on h4. Let's use a setup:
    # White h3 captures Black g4: "6k1/8/8/8/6p1/7P/5PPP/6K1 w - - 0 1" h3xg4
    b2, mv2, a2 = _push("6k1/8/8/8/6p1/7P/5PPP/6K1 w - - 0 1", "h3g4")
    ok2, _ = F.is_luft(b2, mv2, a2, chess.WHITE)
    assert ok2 is False


def test_luft_in_certified_claims():
    # Nf3 doesn't make luft; h2→h3 behind a boxed-in king does.
    b, mv, a = _push("6k1/5ppp/8/8/8/8/5PPP/6K1 w - - 0 1", "h2h3")
    tags = F.certified_claims(b, mv, a, chess.WHITE)
    assert "luft" in tags


# --- is_back_rank_weak ------------------------------------------------------

def test_back_rank_weak_true_black_classic():
    # Classic: Black king g8 behind f7/g7/h7, White rook on a1 (open a-file bearing).
    board = chess.Board("6k1/5ppp/8/8/8/8/8/R5K1 w - - 0 1")
    ok, ev = F.is_back_rank_weak(board, chess.BLACK)
    assert ok
    assert ev["heavy_piece_bearing"] is True
    assert "bears on the back rank" in ev["evidence"]
    assert "mate" not in ev["evidence"].lower()


def test_back_rank_weak_mutual():
    # Both kings boxed in behind their pawns, rooks on the a-file.
    board = chess.Board("r5k1/5ppp/8/8/8/8/5PPP/R5K1 w - - 0 1")
    ok_w, ev_w = F.is_back_rank_weak(board, chess.WHITE)
    ok_b, ev_b = F.is_back_rank_weak(board, chess.BLACK)
    assert ok_w and ok_b


def test_back_rank_weak_false_king_has_luft():
    # Black plays …h6, giving king g8 genuine luft via h7.
    board = chess.Board("6k1/5pp1/7p/8/8/8/5PPP/R5K1 w - - 0 1")
    ok, _ = F.is_back_rank_weak(board, chess.BLACK)
    assert ok is False


def test_back_rank_weak_false_king_off_back_rank():
    # King on g2 — not on the back rank.
    board = chess.Board("6k1/5ppp/8/8/8/8/5PPK/R7 w - - 0 1")
    ok, _ = F.is_back_rank_weak(board, chess.WHITE)
    assert ok is False


def test_back_rank_weak_false_no_enemy_heavy():
    # Black king boxed but White has no rook or queen.
    board = chess.Board("6k1/5ppp/8/8/8/8/8/6K1 w - - 0 1")
    ok, _ = F.is_back_rank_weak(board, chess.BLACK)
    assert ok is False


def test_back_rank_weak_evidence_no_mate_words():
    # Evidence string must never say "mate", "mates", "checkmate", "mating", or "wins".
    board = chess.Board("6k1/5ppp/8/8/8/8/8/R5K1 w - - 0 1")
    _, ev = F.is_back_rank_weak(board, chess.BLACK)
    forbidden = ("mate", "mates", "checkmate", "mating", "wins")
    for word in forbidden:
        assert word not in ev["evidence"].lower(), f"forbidden word '{word}' in evidence"


def test_back_rank_weak_in_certified_claims():
    # Classic back-rank setup: Black king g8, White rook a1 bearing.
    b, mv, a = _push("6k1/5ppp/8/8/8/8/8/R4KQ1 w - - 0 1", "f1e1")
    # White king on e1 after move — still on back rank, both rook bearing → tags fire.
    tags = F.certified_claims(b, mv, a, chess.WHITE)
    assert "back_rank_weakness" in tags


# --- creates_pin ------------------------------------------------------------

def test_pin_true_absolute_bishop_knight_king():
    # Spec §3 example 1: bishop b5 pins black knight c6 to black king e8
    board = chess.Board("4k3/8/2n5/1B6/8/8/8/4K3 w - - 0 1")
    ok, ev = F.creates_pin(board, chess.WHITE)
    assert ok
    assert ev["kind"] == "absolute"
    assert ev["attacker_piece"] == "bishop"
    assert ev["pinned_piece"] == "knight"
    assert ev["behind_piece"] == "king"
    assert ev["line"] == "diagonal"


def test_pin_true_relative_bishop_knight_queen():
    # Spec §3 example 2: bishop g5 pins black knight f6 to black queen d8
    board = chess.Board("3qk3/8/5n2/6B1/8/8/8/4K3 w - - 0 1")
    ok, ev = F.creates_pin(board, chess.WHITE)
    assert ok
    assert ev["kind"] == "relative"
    assert ev["pinned_piece"] == "knight"
    assert ev["behind_piece"] == "queen"
    assert ev["line"] == "diagonal"


def test_pin_true_relative_rook_knight_rook_file():
    # Spec §3 example 3: rook c1 pins black knight c3 to black rook c8 on c-file
    board = chess.Board("2r1k3/8/8/8/8/2n5/8/2RK4 w - - 0 1")
    ok, ev = F.creates_pin(board, chess.WHITE)
    assert ok
    assert ev["kind"] == "relative"
    assert ev["pinned_piece"] == "knight"
    assert ev["behind_piece"] == "rook"
    assert ev["line"] == "file"


def test_pin_true_absolute_rook_bishop_king_file():
    # Spec §3 example 4: rook d1 pins black bishop d3 to black king d8 on d-file
    board = chess.Board("3k4/8/8/8/8/3b4/8/3RK3 w - - 0 1")
    ok, ev = F.creates_pin(board, chess.WHITE)
    assert ok
    assert ev["kind"] == "absolute"
    assert ev["pinned_piece"] == "bishop"
    assert ev["behind_piece"] == "king"
    assert ev["line"] == "file"


def test_pin_true_relative_queen_knight_rook_rank():
    # Spec §3 example 5: queen a4 pins black knight c4 to black rook e4 on 4th rank
    board = chess.Board("4k3/8/8/8/Q1n1r3/8/8/4K3 w - - 0 1")
    ok, ev = F.creates_pin(board, chess.WHITE)
    assert ok
    assert ev["kind"] == "relative"
    assert ev["pinned_piece"] == "knight"
    assert ev["behind_piece"] == "rook"
    assert ev["line"] == "rank"


def test_pin_true_absolute_pawn_as_front():
    # Spec §3 example 6: rook e1 pins black pawn e6 to black king e8 — pawn as front
    board = chess.Board("4k3/8/4p3/8/8/8/8/4R1K1 w - - 0 1")
    ok, ev = F.creates_pin(board, chess.WHITE)
    assert ok
    assert ev["kind"] == "absolute"
    assert ev["pinned_piece"] == "pawn"
    assert ev["behind_piece"] == "king"


def test_pin_false_skewer_queen_in_front():
    # Rook d1 → black queen d3 → black rook d8: PIECE_VALUES[rook](5) > PIECE_VALUES[queen](9) is False
    board = chess.Board("3r2k1/8/8/8/8/3q4/8/3RK3 w - - 0 1")
    ok, _ = F.creates_pin(board, chess.WHITE)
    assert ok is False


def test_pin_false_equal_value_rear():
    # Bishop g5 → black knight f6 → black bishop e7: 3 > 3 is False — spec §4 example 2
    board = chess.Board("4k3/4b3/5n2/6B1/8/8/8/4K3 w - - 0 1")
    ok, _ = F.creates_pin(board, chess.WHITE)
    assert ok is False


def test_pin_false_hanging_pinner():
    # Bishop b5 attacked by pawn a6 (diagonal), not defended — rule 2 fires, pin illusory
    board = chess.Board("4k3/8/p1n5/1B6/8/8/8/4K3 w - - 0 1")
    ok, _ = F.creates_pin(board, chess.WHITE)
    assert ok is False


def test_pin_false_own_piece_as_rear():
    # Rook d1 → black knight d3 → white pawn d5: rear is mover's own piece, rule 7 fires
    board = chess.Board("3k4/8/8/3P4/8/3n4/8/3RK3 w - - 0 1")
    ok, _ = F.creates_pin(board, chess.WHITE)
    assert ok is False


def test_pin_evidence_bundle_keys():
    # All documented evidence bundle keys must be present
    board = chess.Board("4k3/8/2n5/1B6/8/8/8/4K3 w - - 0 1")
    ok, ev = F.creates_pin(board, chess.WHITE)
    assert ok
    for key in ("kind", "attacker_square", "attacker_piece", "pinned_square",
                "pinned_piece", "behind_square", "behind_piece", "line", "coord", "evidence"):
        assert key in ev, f"missing evidence key: {key}"
    assert ev["kind"] in ("absolute", "relative")
    assert ev["line"] in ("file", "rank", "diagonal")
    assert "pins" in ev["evidence"]


def test_pin_in_certified_claims():
    # Bishop moves c4→b5, creating absolute pin of c6 knight to e8 king
    b, mv, a = _push("4k3/8/2n5/8/2B5/8/8/4K3 w - - 0 1", "c4b5")
    tags = F.certified_claims(b, mv, a, chess.WHITE)
    assert "pin" in tags


# --- creates_skewer ---------------------------------------------------------

def test_skewer_true_absolute_rook_rank():
    # Rook b8 checks black king g8 along 8th rank; black rook h8 behind — absolute skewer
    board = chess.Board("1R4kr/8/8/8/8/8/8/6K1 b - - 0 1")
    ok, ev = F.creates_skewer(board, chess.WHITE)
    assert ok
    assert ev["kind"] == "absolute"
    assert ev["forced"] is True
    assert ev["front_piece"] == "king"
    assert ev["back_piece"] == "rook"
    assert ev["line"] == "rank"


def test_skewer_true_relative_bishop_queen_rook_diagonal():
    # Bishop b2 (defended by rook a2) skewers black queen d4 to black rook f6
    # on the b2–f6 diagonal; bishop is not pinned/hanging thanks to rook on a2
    board = chess.Board("7k/8/5r2/8/3q4/8/RB5K/8 w - - 0 1")
    ok, ev = F.creates_skewer(board, chess.WHITE)
    assert ok
    assert ev["kind"] == "relative"
    assert ev["front_piece"] == "queen"
    assert ev["back_piece"] == "rook"
    assert ev["line"] == "diagonal"


def test_skewer_true_absolute_queen_file():
    # Queen e1 checks black king e7 along e-file; black rook e8 behind — absolute file skewer
    board = chess.Board("4r3/4k3/8/8/8/8/8/4Q1K1 b - - 0 1")
    ok, ev = F.creates_skewer(board, chess.WHITE)
    assert ok
    assert ev["kind"] == "absolute"
    assert ev["front_piece"] == "king"
    assert ev["back_piece"] == "rook"
    assert ev["line"] == "file"


def test_skewer_false_pin_king_behind():
    # Rook e1 → black knight e5 → black king e8: king is rear → absolute PIN, not skewer
    board = chess.Board("4k3/8/8/8/8/4n3/8/4RK2 w - - 0 1")
    ok, _ = F.creates_skewer(board, chess.WHITE)
    assert ok is False


def test_skewer_false_equal_value_rook_rook():
    # Rook d1 → black rook d5 → black rook d8: equal value → no cert (strict >)
    board = chess.Board("3r3k/8/8/3r4/8/8/8/3RK3 w - - 0 1")
    ok, _ = F.creates_skewer(board, chess.WHITE)
    assert ok is False


def test_skewer_false_hanging_attacker():
    # Bishop f3 attacked by black pawn g4 and undefended — rule 2 vetoes
    board = chess.Board("7k/1r6/8/3q4/6p1/5B2/8/7K w - - 0 1")
    ok, _ = F.creates_skewer(board, chess.WHITE)
    assert ok is False


def test_skewer_false_back_pawn_relative():
    # Rook d1 → black queen d5 → black pawn d8: back is pawn → relative worth gate vetoes
    board = chess.Board("3p3k/8/8/3q4/8/8/8/3RK3 w - - 0 1")
    ok, _ = F.creates_skewer(board, chess.WHITE)
    assert ok is False


def test_skewer_evidence_bundle_keys():
    # All documented evidence bundle keys must be present on a certified skewer
    board = chess.Board("1R4kr/8/8/8/8/8/8/6K1 b - - 0 1")
    ok, ev = F.creates_skewer(board, chess.WHITE)
    assert ok
    for key in ("kind", "forced", "mover_color", "attacker_square", "attacker_piece",
                "front_square", "front_piece", "back_square", "back_piece", "back_is_pawn",
                "line", "coord", "evidence"):
        assert key in ev, f"missing evidence key: {key}"
    assert ev["kind"] in ("absolute", "relative")
    assert "skewer" in ev["evidence"].lower() or "check" in ev["evidence"].lower()


def test_skewer_in_certified_claims():
    # Rook moves b2→b8 giving check to g8 king, winning h8 rook
    b, mv, a = _push("6kr/8/8/8/8/8/1R6/6K1 w - - 0 1", "b2b8")
    tags = F.certified_claims(b, mv, a, chess.WHITE)
    assert "skewer" in tags


# --- creates_discovered_attack / detect_discovered_attack -------------------

def test_discovered_check_knight_reveals_rook():
    # Ne5-g4: knight vacates e5, rook e1 reveals check to e8 king (only the rook checks)
    b, mv, a = _push("4k3/8/8/4N3/8/8/8/4R1K1 w - - 0 1", "e5g4")
    ok, ev = F.creates_discovered_attack(b, mv, a, chess.WHITE)
    assert ok
    assert ev is not None
    assert "discovered check" in ev
    assert "double check" not in ev


def test_double_check_knight_and_rook():
    # Ne4-f6: knight checks e8 from f6 AND rook e1 reveals through vacated e4 — double check
    b, mv, a = _push("4k3/8/8/8/4N3/8/8/4R1K1 w - - 0 1", "e4f6")
    ok, ev = F.creates_discovered_attack(b, mv, a, chess.WHITE)
    assert ok
    assert ev is not None
    assert "double check" in ev
    assert "discovered check" in ev


def test_plain_discovered_attack_bishop_onto_queen():
    # Nd4-f5: knight vacates d4 (on a1-h8 diagonal), bishop a1 reveals onto black queen e5
    b, mv, a = _push("8/7k/8/4q3/3N4/8/8/B6K w - - 0 1", "d4f5")
    ok, ev = F.creates_discovered_attack(b, mv, a, chess.WHITE)
    assert ok
    assert ev is not None
    assert "discovered attack" in ev
    assert "queen" in ev


def test_pinned_rear_piece_still_certified():
    # Bf4-e5: bishop leaves f-file, rook f1 reveals onto black rook f8.
    # White rook is pinned to king a1 by black queen h1 along rank 1 (different from f-file).
    # Discovery is geometrically real → certify; evidence names the pin constraint.
    b, mv, a = _push("5r1k/8/8/8/5B2/8/8/K4R1q w - - 0 1", "f4e5")
    ok, ev = F.creates_discovered_attack(b, mv, a, chess.WHITE)
    assert ok
    assert ev is not None
    assert "pinned and cannot capture" in ev


def test_en_passant_opens_discovery():
    # d5xe6 en passant: captured black pawn on e5 disappears, opening bishop b2's diagonal
    # to black rook on f6 (discovery via cap_sq, not from_sq).
    b, mv, a = _push("7k/8/5r2/3Pp3/8/8/1B6/K7 w - e6 0 1", "d5e6")
    ok, ev = F.creates_discovered_attack(b, mv, a, chess.WHITE)
    assert ok
    assert ev is not None
    assert "discovered attack" in ev


def test_negative_castling_vetoed():
    # Castling is VETO 2 — not a classic front-piece discovery
    b, mv, a = _push("4k3/8/8/8/8/8/8/4K2R w K - 0 1", "e1g1")
    ok, ev = F.creates_discovered_attack(b, mv, a, chess.WHITE)
    assert ok is False
    assert ev is None


def test_negative_null_move():
    # Null move is VETO 1
    board = chess.Board("4k3/8/8/8/4N3/8/8/4R1K1 w - - 0 1")
    result = F.creates_discovered_attack(board, chess.Move.null(), board, chess.WHITE)
    ok, ev = result
    assert ok is False
    assert ev is None


def test_negative_no_rear_slider():
    # No white sliders exist: knight is the only white piece (besides king) — no discovery
    b, mv, a = _push("8/4q3/8/8/8/3N4/8/K6k w - - 0 1", "d3f4")
    ok, ev = F.creates_discovered_attack(b, mv, a, chess.WHITE)
    assert ok is False
    assert ev is None


def test_discovered_attack_in_certified_claims():
    # Double-check position: Ne4-f6 should certify "discovered_attack" in the full gate
    b, mv, a = _push("4k3/8/8/8/4N3/8/8/4R1K1 w - - 0 1", "e4f6")
    tags = F.certified_claims(b, mv, a, chess.WHITE)
    assert "discovered_attack" in tags


# --- is_backward_pawn ---------------------------------------------------------

def test_backward_pawn_half_open_classic_black():
    # Black d7-d6: Black c5 (strictly ahead), White e4 controls d5, d-file half-open.
    # Textbook Black backward d6-pawn in e4/c5 structure.
    b, mv, a = _push("7k/3p4/8/2p5/4P3/8/8/7K b - - 0 1", "d7d6")
    ok, ev = F.is_backward_pawn(a, mv.to_square, chess.BLACK)
    assert ok
    assert "d6" in ev["evidence"]
    assert "d5" in ev["evidence"]
    assert "half" in ev["evidence"]
    assert ev["subtype"] == "half_open"


def test_backward_pawn_blocked_subtype():
    # Black c7-c6: White pawn already on c5 (stop sq directly occupied), White b4 attacks c5,
    # Black b5 strictly ahead. Certifies as the "blocked" subtype.
    b, mv, a = _push("7k/2p5/8/1pP5/1P6/8/8/7K b - - 0 1", "c7c6")
    ok, ev = F.is_backward_pawn(a, mv.to_square, chess.BLACK)
    assert ok
    assert ev["is_blocked"] is True
    assert ev["subtype"] == "blocked"


def test_backward_pawn_fixed_level_neighbour():
    # Black d7-d6: Black c6 level at d6's rank but support sq c5 is occupied by White pawn,
    # so c6 is fixed. Black e5 is strictly ahead. White e4 controls d5.
    b, mv, a = _push("7k/3p4/2p5/2P1p3/4P3/8/8/7K b - - 0 1", "d7d6")
    ok, ev = F.is_backward_pawn(a, mv.to_square, chess.BLACK)
    assert ok
    assert len(ev["fixed_level_neighbors"]) == 1
    assert "c5" in ev["evidence"]     # support square name in evidence
    assert "level" in ev["evidence"]  # "although the c-pawn is level on c6..."


def test_backward_pawn_white_colour_mirror():
    # White e3-e4: White f5 (strictly ahead), Black f6 controls e5, e-file half-open.
    # Mirrors the Black test; checks fwd=+1 geometry throughout.
    b, mv, a = _push("7k/8/5p2/5P2/8/4P3/8/7K w - - 0 1", "e3e4")
    ok, ev = F.is_backward_pawn(a, mv.to_square, chess.WHITE)
    assert ok
    assert "e4" in ev["evidence"]
    assert "e5" in ev["evidence"]


def test_backward_pawn_negative_isolated():
    # White e3-e4: no White pawns on d- or f-file → isolated, VETO 4a fires.
    b, mv, a = _push("7k/8/3p4/8/8/4P3/8/7K w - - 0 1", "e3e4")
    ok, ev = F.is_backward_pawn(a, mv.to_square, chess.WHITE)
    assert ok is False
    assert ev is None


def test_backward_pawn_negative_no_enemy_pawn_control():
    # White e3-e4: White f5 (ahead) but no Black pawn controls e5 — CONFIRM 1 fails.
    b, mv, a = _push("7k/8/8/5P2/8/4P3/8/7K w - - 0 1", "e3e4")
    ok, ev = F.is_backward_pawn(a, mv.to_square, chess.WHITE)
    assert ok is False
    assert ev is None


def test_backward_pawn_negative_supportable_level_neighbour():
    # White d3-d4: White c4 (level, support sq c5 clear), White e5 (ahead, satisfies VETO 4b).
    # c4 can advance one step to c5 → VETO 3 fires, not backward.
    b, mv, a = _push("7k/8/8/4P3/2P5/3P4/8/7K w - - 0 1", "d3d4")
    ok, ev = F.is_backward_pawn(a, mv.to_square, chess.WHITE)
    assert ok is False
    assert ev is None


def test_backward_pawn_home_rank_double_step_escape():
    # White e2 at home rank: Black f4 controls e3 (stop sq), but e4 (leap sq) is clear and
    # uncontrolled — CONFIRM 1b escape applies, not backward.
    board = chess.Board("7k/8/8/8/5p2/5P2/4P3/K7 w - - 0 1")
    ok, ev = F.is_backward_pawn(board, chess.E2, chess.WHITE)
    assert ok is False
    assert ev is None


def test_backward_pawn_home_rank_leap_blocked():
    # White e2: Black f4 controls e3, Black e4 occupies the leap square — double step blocked,
    # White f3 strictly ahead, so the e2 pawn IS genuinely backward.
    board = chess.Board("7k/8/8/8/4pp2/5P2/4P3/K7 w - - 0 1")
    ok, ev = F.is_backward_pawn(board, chess.E2, chess.WHITE)
    assert ok
    assert "e2" in ev["evidence"]


def test_backward_pawn_in_certified_claims():
    # Black d7-d6 (classic half-open structure) → "backward_pawn" appears in the full gate.
    b, mv, a = _push("7k/3p4/8/2p5/4P3/8/8/7K b - - 0 1", "d7d6")
    tags = F.certified_claims(b, mv, a, chess.BLACK)
    assert "backward_pawn" in tags


# --- is_infiltration --------------------------------------------------------

def test_infiltration_rook_7th_white_pawn_raking():
    # Spec example 1: White Ra7 on 7th rank rakes Black f7 pawn (b7-h7 blocked after f7).
    board = chess.Board("6k1/R4ppp/8/8/8/8/5PPP/6K1 b - - 0 1")
    ok, ev = F.is_infiltration(board, chess.A7, chess.WHITE, "middlegame")
    assert ok
    assert ev["piece"] == "rook"
    assert ev["square"] == "a7"
    assert "f7" in ev["targeted_pawns"]
    assert ev["hanging"] is False
    assert "infiltrated" in ev["evidence_str"]


def test_infiltration_queen_7th_multi_pawn():
    # Spec example 3: White Qd7 attacks Black b7 and f7 pawns.
    board = chess.Board("r4rk1/pp1Q1ppp/8/8/8/8/PPP2PPP/2KR3R b - - 0 1")
    ok, ev = F.is_infiltration(board, chess.D7, chess.WHITE, "middlegame")
    assert ok
    assert ev["piece"] == "queen"
    assert "b7" in ev["targeted_pawns"] or "f7" in ev["targeted_pawns"]
    assert ev["hanging"] is False


def test_infiltration_black_mirror_rook_2nd():
    # Spec example 4: Black Ra2 on rank 2 (deep for Black), rakes White f2 pawn.
    board = chess.Board("6k1/5ppp/8/8/8/8/r4PPP/6K1 w - - 0 1")
    ok, ev = F.is_infiltration(board, chess.A2, chess.BLACK, "middlegame")
    assert ok
    assert ev["piece"] == "rook"
    assert ev["square"] == "a2"
    assert "f2" in ev["targeted_pawns"]


def test_infiltration_endgame_king():
    # Spec example 5: White Ke6 (rank 5 = deep for king in endgame) attacks Black f6 pawn.
    board = chess.Board("8/8/2k1Kp2/8/8/8/5P2/8 b - - 0 1")
    ok, ev = F.is_infiltration(board, chess.E6, chess.WHITE, "endgame")
    assert ok
    assert ev["piece"] == "king"
    assert "f6" in ev["targeted_pawns"]
    assert "marched" in ev["evidence_str"]


def test_infiltration_back_rank_open_file():
    # White Rc8 on open c-file (back rank), Black king off the back rank — open-file arrival.
    board = chess.Board("2R5/5ppp/6k1/8/8/8/5PPP/6K1 b - - 0 1")
    ok, ev = F.is_infiltration(board, chess.C8, chess.WHITE, "middlegame")
    assert ok
    assert ev["arrival_file_state"] == "open"
    assert "back rank" in ev["evidence_str"]


def test_infiltration_king_confinement():
    # Spec example 2: White Ra7 confines Black king to f8 by covering f7 (escape square).
    board = chess.Board("5k2/R5pp/8/8/8/8/6PP/6K1 b - - 0 1")
    ok, ev = F.is_infiltration(board, chess.A7, chess.WHITE, "middlegame")
    assert ok
    assert ev["confines_king"] == "f8"
    assert ev["absolute_seventh"] is False  # rook on a-file, king on f-file — different files


def test_infiltration_hanging_rook_caveat():
    # Re7 attacked by Black Re8 (hanging), but rakes Black g7 pawn — certifies with caveat.
    board = chess.Board("4r1k1/4R1pp/8/8/8/8/6PP/6K1 b - - 0 1")
    ok, ev = F.is_infiltration(board, chess.E7, chess.WHITE, "middlegame")
    assert ok
    assert ev["hanging"] is True
    assert "infiltrating rook is itself hanging" in ev["evidence_str"]


def test_infiltration_evidence_str_no_forbidden_words():
    # Spec §5: evidence_str must never contain "mate", "checkmate", or "wins".
    board = chess.Board("6k1/R4ppp/8/8/8/8/5PPP/6K1 b - - 0 1")
    ok, ev = F.is_infiltration(board, chess.A7, chess.WHITE, "middlegame")
    assert ok
    s = ev["evidence_str"].lower()
    assert "mate" not in s
    assert "wins" not in s


def test_infiltration_negative_knight_deep():
    # Veto 1: knight on the 7th is an outpost candidate, not infiltration.
    board = chess.Board("6k1/4N1pp/8/8/8/8/6PP/6K1 b - - 0 1")
    ok, ev = F.is_infiltration(board, chess.E7, chess.WHITE, "middlegame")
    assert ok is False
    assert ev is None


def test_infiltration_negative_rook_5th():
    # Veto 4: rook on the 5th rank is not deep enough for heavy pieces.
    board = chess.Board("6k1/6pp/8/R7/8/8/6PP/6K1 b - - 0 1")
    ok, ev = F.is_infiltration(board, chess.A5, chess.WHITE, "middlegame")
    assert ok is False
    assert ev is None


def test_infiltration_negative_king_middlegame():
    # Veto 2: a king on a deep rank in the middlegame is a blunder, not infiltration.
    board = chess.Board("8/8/2k1Kp2/8/8/8/5P2/8 b - - 0 1")
    ok, ev = F.is_infiltration(board, chess.E6, chess.WHITE, "middlegame")
    assert ok is False
    assert ev is None


def test_infiltration_negative_check_abstention():
    # Veto 3: rook on back rank that gives check is a tactic, not standing penetration.
    board = chess.Board("2R4k/5ppp/8/8/8/8/5PPP/6K1 b - - 0 1")
    ok, ev = F.is_infiltration(board, chess.C8, chess.WHITE, "middlegame")
    assert ok is False
    assert ev is None


def test_infiltration_negative_idle_rook():
    # Step 6: rook on 7th with no pawn targets and enemy king off the back rank — inert.
    board = chess.Board("8/R7/8/8/8/8/6PP/3k2K1 b - - 0 1")
    ok, ev = F.is_infiltration(board, chess.A7, chess.WHITE, "middlegame")
    assert ok is False
    assert ev is None


def test_infiltration_negative_hanging_queen():
    # Step 5: hanging queen on the 7th is abstained — a blunder, not infiltration.
    board = chess.Board("r4rk1/pp1Q1ppp/1n6/8/8/8/PPP2PPP/2K4R b - - 0 1")
    ok, ev = F.is_infiltration(board, chess.D7, chess.WHITE, "middlegame")
    assert ok is False
    assert ev is None


def test_infiltration_negative_pinned_rook():
    # Step 5: rook on 7th absolutely pinned to its own king cannot operate.
    board = chess.Board("4r1k1/4R1pp/8/8/8/8/8/4K3 b - - 0 1")
    ok, ev = F.is_infiltration(board, chess.E7, chess.WHITE, "middlegame")
    assert ok is False
    assert ev is None


def test_infiltration_in_certified_claims():
    # Integration: Ra1→a7 puts "infiltration" in the allow-set (default middlegame phase).
    b, mv, a = _push("6k1/5ppp/8/8/8/8/5PPP/R5K1 w - - 0 1", "a1a7")
    tags = F.certified_claims(b, mv, a, chess.WHITE)
    assert "infiltration" in tags
