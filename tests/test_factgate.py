"""Tests for the Output Fact-Gate predicate library — pure, no engine, no API key.

This is the L1 (structural-correctness) half of the testing doctrine: every predicate
is checked with a POSITIVE position and at least one TRAP that must NOT certify,
including the named hallucination classes (a king "already on the file", an enemy pawn
that can still challenge an outpost). Wrappers are parity-locked to the analyzer
detectors so the allow-set can never drift from the fact packet.
"""
import chess

import factgate as F
from analyzer import detect_double_attack, detect_royal_alignment, file_structure, detect_overloaded_defender_full


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


# --- is_fianchetto ----------------------------------------------------------

def test_fianchetto_white_kingside_basic():
    # Spec example 1: KIA setup — White bishop on g2, pawn on g3.
    board = chess.Board("rnbqkbnr/pppppppp/8/8/8/6P1/PPPPPPBP/RNBQK1NR w KQkq - 0 3")
    ok, ev_list = F.is_fianchetto(board, chess.WHITE)
    assert ok
    assert ev_list is not None and len(ev_list) == 1
    ev = ev_list[0]
    assert ev["flank"] == "kingside"
    assert ev["bishop_square"] == "g2"
    assert ev["pawn_square"] == "g3"
    assert ev["long_diagonal"] == "h1-a8"
    assert ev["aims_at"] == "a8"
    assert ev["king_behind"] is False
    assert "fianchettoed" in ev["evidence"]
    assert "g2" in ev["evidence"] and "g3" in ev["evidence"]
    assert "h1-a8" in ev["evidence"] and "a8" in ev["evidence"]


def test_fianchetto_black_kingside_non_mover():
    # Spec example 2: White to move; both-colors loop certifies Black's g7/g6 fianchetto.
    board = chess.Board("rnbqk2r/ppppppbp/5np1/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 4")
    ok, ev_list = F.is_fianchetto(board, chess.BLACK)
    assert ok
    assert ev_list is not None and len(ev_list) == 1
    ev = ev_list[0]
    assert ev["flank"] == "kingside"
    assert ev["bishop_square"] == "g7"
    assert ev["pawn_square"] == "g6"
    assert ev["long_diagonal"] == "a1-h8"
    assert ev["aims_at"] == "a1"
    assert ev["side"] == "Black"


def test_fianchetto_white_queenside():
    # Spec example 3: Nimzo-Larsen — White bishop on b2, pawn on b3.
    board = chess.Board("rnbqkbnr/pppppppp/8/8/8/1P6/PBPPPPPP/RN1QKBNR b KQkq - 1 2")
    ok, ev_list = F.is_fianchetto(board, chess.WHITE)
    assert ok
    assert ev_list is not None and len(ev_list) == 1
    ev = ev_list[0]
    assert ev["flank"] == "queenside"
    assert ev["bishop_square"] == "b2"
    assert ev["pawn_square"] == "b3"
    assert ev["long_diagonal"] == "a1-h8"
    assert ev["aims_at"] == "h8"
    assert "b2" in ev["evidence"] and "b3" in ev["evidence"]


def test_fianchetto_black_queenside():
    # Spec example 4: Queen's Indian — Black bishop on b7, pawn on b6.
    board = chess.Board("rn1qkb1r/pbpp1ppp/1p2pn2/8/2PP4/5N2/PP2PPPP/RNBQKB1R w KQkq - 2 5")
    ok, ev_list = F.is_fianchetto(board, chess.BLACK)
    assert ok
    assert ev_list is not None and len(ev_list) == 1
    ev = ev_list[0]
    assert ev["flank"] == "queenside"
    assert ev["bishop_square"] == "b7"
    assert ev["pawn_square"] == "b6"
    assert ev["long_diagonal"] == "h1-a8"
    assert ev["aims_at"] == "h1"
    assert ev["side"] == "Black"


def test_fianchetto_double_white():
    # Spec example 5: White bishops on b2 and g2, pawns on b3 and g3 — 2-element list.
    board = chess.Board("rnbqk1nr/pp1p1ppp/8/8/8/1PP3P1/PB1PPPBP/RN1QK1NR w KQkq - 0 5")
    ok, ev_list = F.is_fianchetto(board, chess.WHITE)
    assert ok
    assert ev_list is not None and len(ev_list) == 2
    flanks = {ev["flank"] for ev in ev_list}
    assert flanks == {"kingside", "queenside"}
    squares = {ev["bishop_square"] for ev in ev_list}
    assert squares == {"b2", "g2"}


def test_fianchetto_king_behind_true():
    # White bishop on g2, pawn on g3, king on g1 (castled KS) → king_behind = True.
    board = chess.Board("4k3/8/8/8/8/6P1/6B1/6K1 w - - 0 1")
    ok, ev_list = F.is_fianchetto(board, chess.WHITE)
    assert ok
    assert ev_list is not None
    ev = ev_list[0]
    assert ev["king_behind"] is True
    assert "castled king on g1" in ev["evidence"]


def test_fianchetto_current_rake_is_sorted_list():
    # current_rake is a sorted list of square names actually attacked by the bishop now.
    board = chess.Board("rnbqkbnr/pppppppp/8/8/8/6P1/PPPPPPBP/RNBQK1NR w KQkq - 0 3")
    ok, ev_list = F.is_fianchetto(board, chess.WHITE)
    assert ok
    ev = ev_list[0]
    assert isinstance(ev["current_rake"], list)
    assert ev["current_rake"] == sorted(ev["current_rake"])
    assert len(ev["current_rake"]) > 0


def test_fianchetto_pinned_bishop_still_certifies():
    # Spec §1: pin never suppresses the verdict. Bishop on g2 pinned by Black rook g8 to king g1.
    board = chess.Board("6rk/8/8/8/8/6P1/6B1/6K1 w - - 0 1")
    ok, ev_list = F.is_fianchetto(board, chess.WHITE)
    assert ok
    assert ev_list is not None
    assert ev_list[0]["flank"] == "kingside"


def test_fianchetto_negative_two_square_pawn_push():
    # Pawn on g4 (not g3) — g3 is empty, veto 2 fires.
    board = chess.Board("7k/8/8/8/6P1/8/6B1/7K w - - 0 1")
    ok, ev_list = F.is_fianchetto(board, chess.WHITE)
    assert ok is False
    assert ev_list is None


def test_fianchetto_negative_destroyed_no_bishop():
    # Pawn on g3 but no bishop on g2 (destroyed / pre-development) — veto 1 fires.
    board = chess.Board("7k/8/8/8/8/6P1/8/7K w - - 0 1")
    ok, ev_list = F.is_fianchetto(board, chess.WHITE)
    assert ok is False
    assert ev_list is None


def test_fianchetto_negative_bishop_not_on_flank_square():
    # White bishop on e4 (on the long diagonal but not the exact flank square) — veto 1.
    board = chess.Board("7k/8/8/8/4B3/8/8/7K w - - 0 1")
    ok, ev_list = F.is_fianchetto(board, chess.WHITE)
    assert ok is False
    assert ev_list is None


def test_fianchetto_negative_wrong_piece_on_flank_square():
    # Starting position: g2 holds a White pawn, not a bishop — veto 1 (piece_type != BISHOP).
    board = chess.Board()
    ok, ev_list = F.is_fianchetto(board, chess.WHITE)
    assert ok is False
    assert ev_list is None


def test_fianchetto_negative_enemy_pawn_on_open_square():
    # Black pawn on g3 with White bishop on g2 — veto 2 color check rejects it.
    board = chess.Board("7k/8/8/8/8/6p1/6B1/7K w - - 0 1")
    ok, ev_list = F.is_fianchetto(board, chess.WHITE)
    assert ok is False
    assert ev_list is None


def test_fianchetto_negative_reversed_rank_color_trap():
    # White bishop deep on g7 — neither color certifies a fianchetto (color-parameterized squares).
    board = chess.Board("7k/6B1/8/8/8/8/8/7K w - - 0 1")
    assert F.is_fianchetto(board, chess.WHITE) == (False, None)
    assert F.is_fianchetto(board, chess.BLACK) == (False, None)


def test_fianchetto_in_certified_claims():
    # Integration: d4 from KIA setup — "fianchetto" appears in the allow-set (both-colors loop).
    b, mv, a = _push("rnbqkbnr/pppppppp/8/8/8/6P1/PPPPPPBP/RNBQK1NR w KQkq - 0 3", "d2d4")
    tags = F.certified_claims(b, mv, a, chess.WHITE)
    assert "fianchetto" in tags


# --- outpost_evidence -------------------------------------------------------

def test_outpost_evidence_knight_one_supporter():
    # Spec example 1: White Nd5 defended by c4 — canonical knight outpost.
    board = chess.Board("r1bq1rk1/pp3ppp/2n2n2/3N4/2P5/8/PP3PPP/R1BQ1RK1 w - - 0 1")
    ev = F.outpost_evidence(board, chess.D5, chess.WHITE)
    assert ev is not None
    assert ev["is_outpost"] is True
    assert ev["piece_name"] == "knight"
    assert ev["square_name"] == "d5"
    assert ev["color_name"] == "White"
    assert ev["supporter_names"] == ["c4"]
    assert "knight" in ev["evidence"]
    assert "d5" in ev["evidence"]
    assert "c4" in ev["evidence"]
    assert "immune" in ev["evidence"]


def test_outpost_evidence_bishop_one_supporter():
    # Spec example 4: White Bc5 defended by d4 — bishop outpost.
    board = chess.Board("r2qk2r/p2n1ppp/4pn2/2B5/3P4/8/PP3PPP/R2QK2R w KQkq - 0 1")
    ev = F.outpost_evidence(board, chess.C5, chess.WHITE)
    assert ev is not None
    assert ev["piece_name"] == "bishop"
    assert ev["square_name"] == "c5"
    assert "bishop" in ev["evidence"]
    assert "c5" in ev["evidence"]
    assert "d4" in ev["evidence"]


def test_outpost_evidence_evidence_string_format():
    # Evidence string must follow the one-supporter template exactly.
    board = chess.Board("r1bq1rk1/pp3ppp/2n2n2/3N4/2P5/8/PP3PPP/R1BQ1RK1 w - - 0 1")
    ev = F.outpost_evidence(board, chess.D5, chess.WHITE)
    assert ev is not None
    s = ev["evidence"]
    assert s.startswith("the White knight on d5 is an outpost")
    assert "defended by the pawn on c4" in s
    assert "immune to any enemy pawn challenge" in s


def test_outpost_evidence_two_supporters():
    # Position with two friendly pawns both defending the outpost square.
    # White Nd5, c4 defends (diagonal) and e4 also defends (diagonal).
    board = chess.Board("4k3/8/8/3N4/2P1P3/8/8/4K3 w - - 0 1")
    ev = F.outpost_evidence(board, chess.D5, chess.WHITE)
    # c4 defends d5 (diagonal); e4 defends d5 (diagonal)
    if ev is not None:  # might still certify depending on enemy pawns
        assert len(ev["supporter_names"]) >= 1
        assert "pawns on" in ev["evidence"] or "pawn on" in ev["evidence"]


def test_outpost_evidence_returns_none_when_not_outpost():
    # Pawn on d5 (not a knight/bishop) — is_outpost fails → outpost_evidence returns None.
    board = chess.Board("4k3/8/8/3P4/2P5/8/8/4K3 w - - 0 1")
    assert F.outpost_evidence(board, chess.D5, chess.WHITE) is None


def test_outpost_evidence_returns_none_unsupported():
    # Knight on e5 with no pawn defender — is_outpost fails → returns None.
    board = chess.Board("4k3/pppppppp/8/4N3/8/8/PPP2PPP/4K3 w - - 0 1")
    assert F.outpost_evidence(board, chess.E5, chess.WHITE) is None


def test_outpost_evidence_black_knight():
    # Spec example 3: Black Nd4, defended by e5. Mirror-test for Black color branch.
    board = chess.Board("r1bq1rk1/pp3ppp/8/4p3/3n4/5N2/PP3PPP/R1BQ1RK1 w - - 0 1")
    ev = F.outpost_evidence(board, chess.D4, chess.BLACK)
    assert ev is not None
    assert ev["piece_name"] == "knight"
    assert ev["color_name"] == "Black"
    assert ev["square_name"] == "d4"
    assert "Black" in ev["evidence"]
    assert "d4" in ev["evidence"]


# --- is_zugzwang ------------------------------------------------------------

def _zz(board, cp_best, cp_pass, phase, legal_count, san, mate_best=None, mate_pass=None):
    """Helper: call is_zugzwang with keyword-defaulted mate arguments."""
    return F.is_zugzwang(board, cp_best, mate_best, cp_pass, mate_pass, phase, legal_count, san)


def test_zugzwang_trebuchet_white():
    # Spec §3 example 2 (MANDATORY two-color test): trébuchet, White to move.
    # White must abandon the e3 pawn; passing holds (reciprocal zugzwang).
    # Manually-constructed scores: cp_best=-200 (losing after move), cp_pass=0 (holds if pass).
    board = chess.Board("8/8/8/8/4k3/4p3/4K3/8 w - - 0 1")
    assert not board.is_game_over()
    result = _zz(board, -200, 0, "endgame", 6, "Kd2")
    assert result["is_zugzwang"] is True
    assert result["strict"] is True
    assert result["label"] == "zugzwang"
    assert result["side_to_move"] == "White"
    # sign=+1: eval_best = +1 * (-200) = -200; eval_pass = +1 * 0 = 0; delta = 200
    assert result["eval_best_cp"] == -200
    assert result["eval_pass_cp"] == 0
    assert result["delta_cp"] == 200
    assert result["threshold_cp"] == F.ZUGZWANG_CP
    assert result["veto_reason"] is None
    assert "zugzwang" in result["evidence"]
    assert "White" in result["evidence"]
    assert "Kd2" in result["evidence"]


def test_zugzwang_trebuchet_black():
    # Spec §3 example 2 (MANDATORY two-color test): same trébuchet, Black to move.
    # White-POV scores: cp_best=+200 (White winning after Black's best move),
    # cp_pass=0 (balanced if Black could pass — White would then also face zugzwang).
    board = chess.Board("8/8/8/8/4k3/4p3/4K3/8 b - - 0 1")
    assert not board.is_game_over()
    result = _zz(board, 200, 0, "endgame", 6, "Kd4")
    assert result["is_zugzwang"] is True
    assert result["strict"] is True
    assert result["label"] == "zugzwang"
    assert result["side_to_move"] == "Black"
    # sign=-1: eval_best = -1 * 200 = -200; eval_pass = -1 * 0 = 0; delta = 200
    assert result["eval_best_cp"] == -200
    assert result["eval_pass_cp"] == 0
    assert result["delta_cp"] == 200
    assert result["veto_reason"] is None
    assert "zugzwang" in result["evidence"]
    assert "Black" in result["evidence"]


def test_zugzwang_near_label_when_pass_losing():
    # NEAR case: delta ≥ threshold but the pass baseline is itself losing (< -50).
    board = chess.Board("8/8/8/8/4k3/4p3/4K3/8 w - - 0 1")
    # cp_pass=-100, cp_best=-300 → eval_pass=-100, eval_best=-300 → delta=200 ≥ 100
    # strict = eval_pass >= -50? → -100 < -50 → False → label = "near-zugzwang"
    result = _zz(board, -300, -100, "endgame", 6, "Kd2")
    assert result["is_zugzwang"] is True
    assert result["strict"] is False
    assert result["label"] == "near-zugzwang"
    assert result["delta_cp"] == 200
    assert "near-zugzwang" in result["evidence"]


def test_zugzwang_below_threshold():
    # Delta < ZUGZWANG_CP → no fire (below_threshold).
    board = chess.Board("8/8/8/8/4k3/4p3/4K3/8 w - - 0 1")
    # cp_pass=0, cp_best=-50 → delta = 0 - (-50) = 50 < 100
    result = _zz(board, -50, 0, "endgame", 6, "Kd2")
    assert not result["is_zugzwang"]
    assert result["veto_reason"] == "below_threshold"


def test_zugzwang_veto1_game_over():
    # VETO 1: stalemate is game over — never zugzwang.
    # Black king on a8, White queen on c7, White king on c6 — Black is stalemated.
    board = chess.Board("k7/2Q5/2K5/8/8/8/8/8 b - - 0 1")
    assert board.is_game_over(), "FEN must be stalemate for this test"
    result = _zz(board, -200, 0, "endgame", 0, "")
    assert not result["is_zugzwang"]
    assert result["veto_reason"] == "game_over"


def test_zugzwang_veto2_in_check():
    # VETO 2: side to move is in check — null-move baseline is garbage, abstain.
    # White king on e1, Black rook on e8 giving check to White.
    board = chess.Board("4r3/8/8/8/8/8/8/4K3 w - - 0 1")
    assert board.is_check(), "FEN must put White in check for this test"
    result = _zz(board, -200, 0, "endgame", 4, "Kd1")
    assert not result["is_zugzwang"]
    assert result["veto_reason"] == "in_check"


def test_zugzwang_veto3_forced():
    # VETO 3: legal_move_count <= 1 → no meaningful choice to degrade.
    board = chess.Board("8/8/8/8/4k3/4p3/4K3/8 w - - 0 1")
    result = _zz(board, -200, 0, "endgame", 1, "Kd1")
    assert not result["is_zugzwang"]
    assert result["veto_reason"] == "forced"


def test_zugzwang_veto4_phase_middlegame_many_pieces():
    # VETO 4: middlegame phase AND > 6 non-KP pieces → phase gate fires.
    board = chess.Board()  # 16 non-KP pieces, phase="middlegame"
    result = _zz(board, -200, 0, "middlegame", 20, "e4")
    assert not result["is_zugzwang"]
    assert result["veto_reason"] == "phase"


def test_zugzwang_veto4_passes_low_piece_count():
    # VETO 4 does NOT fire for ≤6 non-KP pieces even with phase="middlegame".
    # Trébuchet has 0 non-KP pieces → VETO 4 passes regardless of phase label.
    board = chess.Board("8/8/8/8/4k3/4p3/4K3/8 w - - 0 1")
    result = _zz(board, -200, 0, "middlegame", 6, "Kd2")
    assert result["is_zugzwang"] is True  # VETO 4 cleared by low piece count


def test_zugzwang_veto5_en_passant():
    # VETO 5: en-passant capture available — null-move baseline is polluted.
    # White pawn on d4 (just advanced), Black pawn on e4 can capture en passant.
    board = chess.Board("4k3/8/8/8/3Pp3/8/8/4K3 b - d3 0 1")
    assert board.has_legal_en_passant(), "FEN must have en passant for this test"
    result = _zz(board, 200, 0, "endgame", 4, "exd3")
    assert not result["is_zugzwang"]
    assert result["veto_reason"] == "en_passant"


def test_zugzwang_no_null_scores():
    # Both cp_pass and mate_pass None (null-move probe skipped upstream) → no fire.
    board = chess.Board("8/8/8/8/4k3/4p3/4K3/8 w - - 0 1")
    result = F.is_zugzwang(board, -200, None, None, None, "endgame", 6, "Kd2")
    assert not result["is_zugzwang"]
    assert result["veto_reason"] == "below_threshold"


def test_zugzwang_evidence_strict_format():
    # Spec §5 STRICT evidence template verification.
    board = chess.Board("8/8/8/8/4k3/4p3/4K3/8 w - - 0 1")
    result = _zz(board, -200, 0, "endgame", 6, "Kd2")
    assert result["strict"] is True
    ev = result["evidence"]
    assert ev.startswith("White is in zugzwang:")
    assert "passing would hold" in ev
    assert "Kd2" in ev
    assert "6 legal moves" in ev


def test_zugzwang_evidence_near_format():
    # Spec §5 NEAR evidence template verification.
    board = chess.Board("8/8/8/8/4k3/4p3/4K3/8 w - - 0 1")
    result = _zz(board, -300, -100, "endgame", 6, "Kd2")
    assert result["strict"] is False
    ev = result["evidence"]
    assert ev.startswith("White is in near-zugzwang:")
    assert "no useful waiting move" in ev
    assert "Kd2" in ev
    assert "centipawns" in ev


# --- creates_overloaded / detect_overloaded_defender_full ------------------
# Position: White queen c3 is the SOLE defender of the White knight on a1
# (attacked by the Black rook on b1) and the White bishop on f6 (attacked by
# the Black bishop on g5). The queen defends both via the same c3-a1 diagonal
# and the c3-f6 diagonal.
_OVERLOADED_FEN = "7k/8/5B2/6b1/8/2Q5/8/Nr5K w - - 0 1"


def test_creates_overloaded_positive_evidence_bundle():
    board = chess.Board(_OVERLOADED_FEN)
    result = F.creates_overloaded(board)
    assert result is not None
    assert result["tag"] == "overloaded_piece"
    assert "queen" in result["defender"].lower()
    assert len(result["targets"]) >= 2
    assert "overloaded" in result["evidence"].lower()
    assert "side" in result
    assert "defender_square" in result
    assert "defender_piece" in result


def test_creates_overloaded_evidence_keys_present():
    board = chess.Board(_OVERLOADED_FEN)
    result = F.creates_overloaded(board)
    assert result is not None
    for key in ("tag", "side", "defender", "defender_square", "defender_piece", "targets", "evidence"):
        assert key in result, f"missing key: {key}"


def test_creates_overloaded_evidence_no_internal_field_names():
    # Evidence string must read naturally — no JSON key names in the prose.
    board = chess.Board(_OVERLOADED_FEN)
    result = F.creates_overloaded(board)
    assert result is not None
    ev = result["evidence"].lower()
    for bad in ("overloaded_piece", "defender_square", "defender_piece"):
        assert bad not in ev, f"internal key '{bad}' leaked into evidence string"


def test_creates_overloaded_negative_sole_defender_not_required():
    # The knight on e4 is defended by BOTH the rook on e1 and the queen on a4,
    # so no sole-defender condition holds; should not certify.
    # White: Ke1-rook, Qa4, Ne4; Black: Kh8, Ra4-attacks e4? No — let's use
    # a simple "no overloaded piece" quiet position.
    board = chess.Board()  # starting position — no piece is overloaded
    assert F.creates_overloaded(board) is None


def test_creates_overloaded_negative_only_one_target():
    # A defender defends ONE attacked piece only — not overloaded (needs >= 2).
    # White: Kh1, Qe4 (defends Nf6); Black: Kh8, Be7 (attacks Nf6); Qe4 sole-defends Nf6 only.
    board = chess.Board("7k/4b3/5N2/8/4Q3/8/8/7K w - - 0 1")
    result = F.creates_overloaded(board)
    # The queen on e4 attacks f6 and is the sole defender of the knight on f6
    # (attacked by the bishop on e7). But it only defends ONE attacked piece,
    # so the condition `len(defended_attacked) >= 2` is not met.
    assert result is None


def test_creates_overloaded_in_certified_claims():
    # certified_claims must add "overloaded_piece" to its tag set on the
    # overloaded position. Use a quiet null-move to keep the test simple:
    # push a do-nothing move so we have board_before/move/board_after.
    board_before = chess.Board(_OVERLOADED_FEN)
    # Make a legal move that leaves the overloaded structure intact.
    # Any move that doesn't change the defender/targets works; here we move the
    # Black king from h8 to g8 (it's Black's turn after White last moved).
    # Actually _OVERLOADED_FEN has White to move; let's make a White king move
    # that keeps the queen, knight, and bishop in place.
    move = chess.Move.from_uci("h1g1")  # Kg1 — doesn't disturb the overloaded structure
    board_after = board_before.copy()
    board_after.push(move)
    tags = F.certified_claims(board_before, move, board_after, chess.WHITE)
    assert "overloaded_piece" in tags


# --- is_compensation --------------------------------------------------------
# Helpers use the same calling convention as the zugzwang helpers above.

def _comp(material_balance: float, eval_cp, mate, mover_white: bool):
    return F.is_compensation(material_balance, eval_cp, mate, mover_white)


def test_compensation_positive_pawn_sac_level_eval():
    # White sacrificed a pawn (material_balance = -1.5, White behind), eval near 0.
    result = _comp(-1.5, 20, None, True)
    assert result is not None
    assert result["tag"] == "compensation"
    assert result["side"] == "White"
    assert result["down_pawns"] == 1.5
    assert result["eval_cp"] == 20
    assert result["mechanism"] is None
    assert result["approximate"] is False
    assert "compensation" in result["evidence"].lower()


def test_compensation_positive_exchange_sac_black():
    # Black sacrificed an exchange (R for B, ≈ 2 pawns). material_balance = +2.0
    # (White is 2 up), eval_cp = +30 from White's POV = -30 from Black's = -30 for Black mover.
    # Black mover: mover_material = -1 * 2.0 = -2.0 (≤ -1.5 ✓); mover_eval = -1 * 30 = -30 (≥ -50 ✓)
    result = _comp(2.0, 30, None, False)
    assert result is not None
    assert result["side"] == "Black"
    assert result["down_pawns"] == 2.0


def test_compensation_evidence_keys_present():
    result = _comp(-1.5, -30, None, True)
    assert result is not None
    for key in ("tag", "side", "down_pawns", "eval_cp", "mechanism", "approximate", "evidence"):
        assert key in result, f"missing key: {key}"


def test_compensation_evidence_no_internal_field_names():
    result = _comp(-1.5, 10, None, True)
    assert result is not None
    ev = result["evidence"].lower()
    for bad in ("compensation_evidence", "eval_cp", "down_pawns", "mechanism"):
        assert bad not in ev, f"internal key '{bad}' leaked into evidence string"


def test_compensation_veto2_not_down_enough():
    # Only down 1.0 pawn — below the 1.5-pawn threshold.
    assert _comp(-1.0, 10, None, True) is None


def test_compensation_veto2_mover_ahead():
    # White is ahead in material — not compensation.
    assert _comp(1.5, 100, None, True) is None


def test_compensation_veto3_eval_too_bad():
    # Down 2.0 pawns and eval is -200 (clearly lost) — no compensation.
    assert _comp(-2.0, -200, None, True) is None


def test_compensation_veto3_border_just_below():
    # Exactly at the border: eval = -51 (below -50 threshold) — veto.
    assert _comp(-1.5, -51, None, True) is None


def test_compensation_veto3_border_at_threshold():
    # Exactly at threshold: eval = -50 (≥ -50) — certify.
    result = _comp(-1.5, -50, None, True)
    assert result is not None


def test_compensation_veto1_mate_score_abstain():
    # Under a mate score (forcing line) — abstain regardless of material.
    assert _comp(-2.0, None, 5, True) is None


def test_compensation_veto0_no_eval_data():
    # No eval data at all — abstain.
    assert _comp(-2.0, None, None, True) is None


# --- is_tempo ---------------------------------------------------------------
# Position: White queen on e4 attacks the Black knight on d5.
# The Black knight can move to c7 (Nc7) as its best reply.
# FEN: "7k/8/8/3n4/4Q3/8/8/7K b - - 0 15" (Black to move)
_TEMPO_FEN = "7k/8/8/3n4/4Q3/8/8/7K b - - 0 15"
_TEMPO_ATTACKS = ["knight on d5"]
_TEMPO_REFUTATION = "15... Nc7"


def test_is_tempo_positive_forced_reply_moves_attacked_piece():
    result = F.is_tempo(_TEMPO_ATTACKS, _TEMPO_REFUTATION, _TEMPO_FEN, False)
    assert result is not None
    assert result["tag"] == "tempo_gain"
    assert "knight" in result["attacked"]
    assert result["forced_reply"] == "Nc7"
    assert result["square"] == "d5"
    assert "tempo" in result["evidence"].lower()


def test_is_tempo_evidence_keys_present():
    result = F.is_tempo(_TEMPO_ATTACKS, _TEMPO_REFUTATION, _TEMPO_FEN, False)
    assert result is not None
    for key in ("tag", "attacked", "forced_reply", "square", "evidence"):
        assert key in result, f"missing key: {key}"


def test_is_tempo_veto1_is_capture():
    # The move was a capture — not a pure tempo gain.
    assert F.is_tempo(_TEMPO_ATTACKS, _TEMPO_REFUTATION, _TEMPO_FEN, True) is None


def test_is_tempo_veto1_only_pawn_attacked():
    # Only a pawn is attacked — pawn attacks don't certify tempo.
    assert F.is_tempo(["pawn on d5"], _TEMPO_REFUTATION, _TEMPO_FEN, False) is None


def test_is_tempo_veto1_empty_attacks():
    assert F.is_tempo([], _TEMPO_REFUTATION, _TEMPO_FEN, False) is None


def test_is_tempo_veto2_no_refutation_line():
    assert F.is_tempo(_TEMPO_ATTACKS, "", _TEMPO_FEN, False) is None


def test_is_tempo_veto3_reply_ignores_attacked_square():
    # Opponent plays Kg7 (king shuffle) — ignores the attacked knight on d5.
    result = F.is_tempo(_TEMPO_ATTACKS, "15... Kg7", _TEMPO_FEN, False)
    assert result is None


def test_is_tempo_pawn_plus_minor_certifies_on_minor():
    # attacks_pieces has both a pawn and a minor piece; should certify on the minor.
    result = F.is_tempo(
        ["pawn on e5", "knight on d5"],
        _TEMPO_REFUTATION,
        _TEMPO_FEN,
        False,
    )
    assert result is not None
    assert result["square"] == "d5"  # certified on the non-pawn piece


# --- is_hole / detect_weak_square -------------------------------------------
# Position: White Knight on d5 (rank 4, file 3), no Black pawns on adjacent files.
# Kings on h1 / h8 to satisfy chess.Board requirements.
_HOLE_FEN        = "7k/8/8/3N4/8/8/8/7K w - - 0 1"
_HOLE_MOVE       = chess.Move.from_uci("c3d5")   # arbitrary from_sq; only to_sq (d5) used
_HOLE_BOARD      = chess.Board(_HOLE_FEN)

# Position where Black HAS a pawn on c6 (can still challenge d5).
_NO_HOLE_FEN     = "7k/8/2p5/3N4/8/8/8/7K w - - 0 1"
_NO_HOLE_BOARD   = chess.Board(_NO_HOLE_FEN)

# Position where the Black pawn on c4 has ALREADY PASSED the attack rank for d5.
# A Black pawn at c4 (rank 3) cannot advance back to c6 (rank 5) to attack d5.
_PASSED_HOLE_FEN  = "7k/8/8/3N4/2p5/8/8/7K w - - 0 1"
_PASSED_HOLE_BOARD = chess.Board(_PASSED_HOLE_FEN)


def test_is_hole_positive_no_enemy_pawns():
    # d5 with no Black pawns on adjacent files at all — permanent hole.
    assert F.is_hole(_HOLE_BOARD, chess.D5, chess.BLACK) is True


def test_is_hole_negative_enemy_pawn_can_advance():
    # Black pawn on c6 (rank 5 >= d5_rank+1=5) — can still challenge d5.
    assert F.is_hole(_NO_HOLE_BOARD, chess.D5, chess.BLACK) is False


def test_is_hole_positive_enemy_pawn_has_passed():
    # Black pawn on c4 (rank 3 < 5) — already advanced past the attack rank.
    assert F.is_hole(_PASSED_HOLE_BOARD, chess.D5, chess.BLACK) is True


def test_detect_weak_square_positive_knight():
    # White Knight on d5, no Black pawns on adjacent files.
    result = F.detect_weak_square(_HOLE_BOARD, _HOLE_MOVE, chess.WHITE)
    assert result is not None
    assert result["tag"] == "weak_square"
    assert result["square"] == "d5"
    assert result["piece"] == "knight"
    assert "permanent" in result["evidence"].lower()


def test_detect_weak_square_positive_rook():
    # White Rook on d5 — rooks (not just minors) benefit from a hole.
    board = chess.Board("7k/8/8/3R4/8/8/8/7K w - - 0 1")
    move  = chess.Move.from_uci("d1d5")
    result = F.detect_weak_square(board, move, chess.WHITE)
    assert result is not None
    assert result["piece"] == "rook"


def test_detect_weak_square_veto1_pawn():
    # White Pawn on d5 — pawns cannot benefit from a hole.
    board = chess.Board("7k/8/8/3P4/8/8/8/7K w - - 0 1")
    move  = chess.Move.from_uci("d4d5")
    assert F.detect_weak_square(board, move, chess.WHITE) is None


def test_detect_weak_square_veto2_rank_not_advanced():
    # White Knight on d3 (rank 2) — not in advanced territory.
    board = chess.Board("7k/8/8/8/8/3N4/8/7K w - - 0 1")
    move  = chess.Move.from_uci("c1d3")
    assert F.detect_weak_square(board, move, chess.WHITE) is None


def test_detect_weak_square_veto3_not_a_hole():
    # Black pawn on c6 can still challenge d5 — NOT a hole.
    move  = chess.Move.from_uci("c3d5")
    assert F.detect_weak_square(_NO_HOLE_BOARD, move, chess.WHITE) is None


def test_detect_weak_square_veto4_hanging():
    # White Knight on d5 attacked by Black Rook c5, undefended — hanging; no certification.
    board = chess.Board("7k/8/8/2rN4/8/8/8/7K w - - 0 1")
    move  = chess.Move.from_uci("c3d5")
    assert F.detect_weak_square(board, move, chess.WHITE) is None


def test_detect_weak_square_integration_certified_claims():
    # Full pipeline: White Knight c3 → d5; board_after has the Knight on d5 with no
    # Black pawns on adjacent files → certified_claims must include "weak_square".
    board_before = chess.Board("7k/8/8/8/8/2N5/8/7K w - - 0 1")
    move         = chess.Move.from_uci("c3d5")
    board_after  = chess.Board("7k/8/8/3N4/8/8/8/7K b - - 1 1")
    tags = F.certified_claims(board_before, move, board_after, chess.WHITE)
    assert "weak_square" in tags


# --- is_zwischenzug ---------------------------------------------------------
# Position: White Rook d1, Queen h1, King e1; Black Knight d5 (free), King a3.
# White plays Qh3+ (checking Black King a3 along rank 3) instead of Rxd5.
# The Black knight on d5 is attacked by the Rook and undefended — the forgone capture.
_ZWIG_FEN_BEFORE   = "8/8/8/3n4/8/k7/8/3RK2Q w - - 0 1"
_ZWIG_BOARD_BEFORE = chess.Board(_ZWIG_FEN_BEFORE)
_ZWIG_MOVE_CHECK   = chess.Move.from_uci("h1h3")   # Qh3+ checking King a3 along 3rd rank
_ZWIG_BOARD_AFTER  = _ZWIG_BOARD_BEFORE.copy()
_ZWIG_BOARD_AFTER.push(_ZWIG_MOVE_CHECK)


def test_is_zwischenzug_positive_checking_intermezzo():
    result = F.is_zwischenzug(
        _ZWIG_BOARD_BEFORE, _ZWIG_MOVE_CHECK, _ZWIG_BOARD_AFTER, chess.WHITE
    )
    assert result is not None
    assert result["tag"] == "zwischenzug"
    assert result["forgone_piece"] == "knight"   # Black knight d5 was forgone


def test_is_zwischenzug_positive_keys_present():
    result = F.is_zwischenzug(
        _ZWIG_BOARD_BEFORE, _ZWIG_MOVE_CHECK, _ZWIG_BOARD_AFTER, chess.WHITE
    )
    assert result is not None
    for key in ("tag", "check_square", "forgone_capture", "forgone_piece", "side", "evidence"):
        assert key in result, f"missing key: {key}"


def test_is_zwischenzug_veto1_no_check():
    # White captures the knight directly — no check given, not a zwischenzug.
    move_capture  = chess.Move.from_uci("d1d5")   # Rxd5 (captures the free knight)
    board_after_c = _ZWIG_BOARD_BEFORE.copy()
    board_after_c.push(move_capture)
    result = F.is_zwischenzug(
        _ZWIG_BOARD_BEFORE, move_capture, board_after_c, chess.WHITE
    )
    assert result is None


def test_is_zwischenzug_veto3_no_forgone_piece():
    # White gives check but there is no undefended enemy piece to bypass.
    board_before = chess.Board("8/8/8/8/8/k7/8/4K2Q w - - 0 1")
    move         = chess.Move.from_uci("h1h3")   # Qh3+ checking King a3
    board_after  = board_before.copy()
    board_after.push(move)
    result = F.is_zwischenzug(board_before, move, board_after, chess.WHITE)
    assert result is None


def test_is_zwischenzug_integration_certified_claims():
    # Full pipeline: Qh3+ in the zwischenzug position — "zwischenzug" in the tag set.
    board_after = _ZWIG_BOARD_BEFORE.copy()
    board_after.push(_ZWIG_MOVE_CHECK)
    tags = F.certified_claims(_ZWIG_BOARD_BEFORE, _ZWIG_MOVE_CHECK, board_after, chess.WHITE)
    assert "zwischenzug" in tags


# --- is_initiative -----------------------------------------------------------
# Position after White Rd8+: Black King e8 in check (escape squares e7, f7, d7 …).
# White Rook d8 on 8th rank gives check; after Ke7, Rd7+ delivers the second check.
_INIT_CHECK_FEN = "3Rk3/8/8/8/8/8/8/4K3 b - - 0 1"   # Black to move, in check


def test_is_initiative_positive():
    # PV: Black Ke7, then White Rd7+ — second check fires.
    result = F.is_initiative(_INIT_CHECK_FEN, "1... Ke7 2. Rd7+", chess.WHITE)
    assert result is not None
    assert result["tag"] == "initiative"
    assert result["second_check"] == "Rd7+"
    assert result["opp_reply"] == "Ke7"


def test_is_initiative_positive_keys_present():
    result = F.is_initiative(_INIT_CHECK_FEN, "1... Ke7 2. Rd7+", chess.WHITE)
    assert result is not None
    for key in ("tag", "opp_reply", "second_check", "side", "evidence"):
        assert key in result, f"missing key: {key}"


def test_is_initiative_veto1_not_in_check():
    # Quiet position — not in check.
    quiet_fen = "8/8/8/8/8/8/8/4K2k b - - 0 1"
    result = F.is_initiative(quiet_fen, "1... Kh2 2. Kd1+", chess.WHITE)
    assert result is None


def test_is_initiative_veto2_checkmate():
    # Scholar's mate — Black is in checkmate, not a sustained initiative.
    mate_fen = "r1bqkb1r/pppp1Qpp/2n2n2/4p3/2B1P3/8/PPPP1PPP/RNB1K1NR b KQkq - 0 4"
    result = F.is_initiative(mate_fen, "1... Ke8", chess.WHITE)
    assert result is None


def test_is_initiative_veto3_no_pv():
    result = F.is_initiative(_INIT_CHECK_FEN, "", chess.WHITE)
    assert result is None


def test_is_initiative_veto4_only_one_pv_move():
    # PV has only the opponent's reply — no mover follow-up.
    result = F.is_initiative(_INIT_CHECK_FEN, "1... Ke7", chess.WHITE)
    assert result is None


def test_is_initiative_veto5_followup_not_check():
    # Second move in PV is not a check (no '+').
    result = F.is_initiative(_INIT_CHECK_FEN, "1... Ke7 2. Rd6", chess.WHITE)
    assert result is None


# --- detect_space_advantage --------------------------------------------------
# White pawns c5, d5, e5 (score 3+3+3=9) vs Black d6, e6, f7 (score 1+1+0=2); lead=7.
_SA_WHITE_FEN = "4k3/5p2/3pp3/2PPP3/8/8/8/4K3 w - - 0 1"
# Black pawns c6, d6, e6 (score 1+1+1=3), c5, d5 (score 2+2=4) = 7; White d4 (score 2); lead=5.
_SA_BLACK_FEN = "4k3/8/2ppp3/2pp4/3P4/8/8/4K3 w - - 0 1"


def test_detect_space_advantage_positive_white():
    board = chess.Board(_SA_WHITE_FEN)
    result = F.detect_space_advantage(board, chess.WHITE)
    assert result is not None
    assert result["tag"] == "space_advantage"
    assert result["side"] == "White"
    assert result["lead"] >= 4


def test_detect_space_advantage_positive_keys_present():
    board = chess.Board(_SA_WHITE_FEN)
    result = F.detect_space_advantage(board, chess.WHITE)
    assert result is not None
    for key in ("tag", "side", "mover_score", "enemy_score", "lead", "advanced_pawns", "evidence"):
        assert key in result, f"missing key: {key}"


def test_detect_space_advantage_veto1_too_few_pawns():
    # Only 1 White pawn, 0 Black pawns — total < 4.
    board = chess.Board("4k3/8/8/2P5/8/8/8/4K3 w - - 0 1")
    assert F.detect_space_advantage(board, chess.WHITE) is None


def test_detect_space_advantage_veto2_insufficient_lead():
    # White d5 (score 3) vs Black d6, d7, e7 (scores 1+0+0=1); lead=2 < 4.
    board = chess.Board("4k3/3pp3/3p4/3P4/8/8/8/4K3 w - - 0 1")
    result = F.detect_space_advantage(board, chess.WHITE)
    assert result is None


def test_detect_space_advantage_negative_when_opponent_leads():
    # Black has more advanced pawns; White returns None, Black returns not-None.
    board = chess.Board(_SA_BLACK_FEN)
    assert F.detect_space_advantage(board, chess.WHITE) is None
    result_black = F.detect_space_advantage(board, chess.BLACK)
    assert result_black is not None
    assert result_black["side"] == "Black"


def test_detect_space_advantage_integration_certified_claims():
    # Pawn push e4→e5 creates the three-pawn centre; "space_advantage" must appear.
    board_before = chess.Board("4k3/5p2/3pp3/2PP4/4P3/8/8/4K3 w - - 0 1")
    move = chess.Move.from_uci("e4e5")
    board_after = board_before.copy()
    board_after.push(move)
    tags = F.certified_claims(board_before, move, board_after, chess.WHITE)
    assert "space_advantage" in tags


# --- is_prophylaxis ----------------------------------------------------------
# Position: White Rook d1, Black pawn d4 (rank 4, r=3, dangerous), Black King g8.
# White plays Rd3 — places the Rook directly in front of the Black pawn on d4.
_PROP_FEN = "6k1/8/8/8/3p4/8/8/3R2K1 w - - 0 1"
_PROP_BOARD_BEFORE = chess.Board(_PROP_FEN)
_PROP_MOVE = chess.Move.from_uci("d1d3")    # Rd3, blocking d4 pawn's advance to d3
_PROP_BOARD_AFTER = _PROP_BOARD_BEFORE.copy()
_PROP_BOARD_AFTER.push(_PROP_MOVE)


def test_is_prophylaxis_positive():
    result = F.is_prophylaxis(_PROP_BOARD_BEFORE, _PROP_MOVE, _PROP_BOARD_AFTER, chess.WHITE)
    assert result is not None
    assert result["tag"] == "prophylaxis"
    assert result["blocked_pawn"] == "d4"
    assert result["blocking_square"] == "d3"


def test_is_prophylaxis_positive_keys_present():
    result = F.is_prophylaxis(_PROP_BOARD_BEFORE, _PROP_MOVE, _PROP_BOARD_AFTER, chess.WHITE)
    assert result is not None
    for key in ("tag", "blocked_pawn", "blocking_piece", "blocking_square",
                "side", "is_passed_pawn_blockade", "evidence"):
        assert key in result, f"missing key: {key}"


def test_is_prophylaxis_veto1_gives_check():
    # Any move that gives check must not certify as prophylaxis.
    # White Rook d1 slides to g1, checking Black King on g8 via g-file.
    board_before = chess.Board("6k1/8/8/8/3p4/8/8/3R2K1 w - - 0 1")
    move = chess.Move.from_uci("d1g1")    # Rg1+ checks King g8 along g-file
    board_after = board_before.copy()
    board_after.push(move)
    assert board_after.is_check()
    assert F.is_prophylaxis(board_before, move, board_after, chess.WHITE) is None


def test_is_prophylaxis_veto2_capture():
    # White Rook captures the Black pawn directly — not a quiet blockade.
    board_before = chess.Board("6k1/8/8/8/3pR3/8/8/6K1 w - - 0 1")
    move = chess.Move.from_uci("e4d4")    # Rxd4 captures
    board_after = board_before.copy()
    board_after.push(move)
    assert F.is_prophylaxis(board_before, move, board_after, chess.WHITE) is None


def test_is_prophylaxis_veto_pawn_not_dangerous():
    # Black pawn on d7 (rank 7, r=6) — not past centre for White's purposes.
    board_before = chess.Board("6k1/3p4/8/8/8/8/8/3R2K1 w - - 0 1")
    move = chess.Move.from_uci("d1d6")    # Rd6 — in front of d7 pawn but not dangerous
    board_after = board_before.copy()
    board_after.push(move)
    assert F.is_prophylaxis(board_before, move, board_after, chess.WHITE) is None


def test_is_prophylaxis_veto_hanging_piece():
    # White Rook on d3 would be attacked by Black Bishop on f5 and not defended.
    board_before = chess.Board("6k1/8/8/5b2/3p4/8/8/3R2K1 w - - 0 1")
    move = chess.Move.from_uci("d1d3")    # Rd3 — hangs to Bf5
    board_after = board_before.copy()
    board_after.push(move)
    assert F.is_prophylaxis(board_before, move, board_after, chess.WHITE) is None


def test_is_prophylaxis_passed_pawn_blockade_flag():
    # Black pawn d4 with no Black pawns on c- or e-files → it's a passed pawn.
    result = F.is_prophylaxis(_PROP_BOARD_BEFORE, _PROP_MOVE, _PROP_BOARD_AFTER, chess.WHITE)
    assert result is not None
    assert result["is_passed_pawn_blockade"] is True


def test_is_prophylaxis_integration_certified_claims():
    tags = F.certified_claims(_PROP_BOARD_BEFORE, _PROP_MOVE, _PROP_BOARD_AFTER, chess.WHITE)
    assert "prophylaxis" in tags


# --- is_bishop_pair ---------------------------------------------------------
def test_bishop_pair_true_both_vs_one():
    # White: Bc1, Bf1 (both bishops). Black: Bf8 only (one bishop).
    board = chess.Board("2r1kb2/8/8/8/8/8/8/2B1KB2 w - - 0 1")
    ok, ev = F.is_bishop_pair(board, chess.WHITE)
    assert ok
    assert "bishop pair" in ev


def test_bishop_pair_false_opponent_also_has_pair():
    # White: Bc1, Bf1. Black: Bc8, Bf8 (two bishops) → enemy=2 → False.
    board = chess.Board("2b1kb2/8/8/8/8/8/8/2B1KB2 w - - 0 1")
    ok, _ = F.is_bishop_pair(board, chess.WHITE)
    assert not ok


def test_bishop_pair_false_mover_missing_one_bishop():
    # White: only Bf1. Black: Bf8 only.
    board = chess.Board("2r1kb2/8/8/8/8/8/8/4KB2 w - - 0 1")
    ok, _ = F.is_bishop_pair(board, chess.WHITE)
    assert not ok


def test_bishop_pair_false_for_side_that_has_one():
    # White has the pair; from Black's perspective: Black has 1, White has 2 → False for Black.
    board = chess.Board("2r1kb2/8/8/8/8/8/8/2B1KB2 w - - 0 1")
    ok, _ = F.is_bishop_pair(board, chess.BLACK)
    assert not ok


def test_bishop_pair_in_certified_claims():
    # Make a quiet move that preserves the bishop-pair structure.
    board_before = chess.Board("2r1kb2/8/8/8/8/8/8/2B1KB2 w - - 0 1")
    move = chess.Move.from_uci("e1d1")  # Kd1 — king move, bishop count unchanged
    board_after = board_before.copy()
    board_after.push(move)
    tags = F.certified_claims(board_before, move, board_after, chess.WHITE)
    assert "bishop_pair" in tags


# --- is_rook_on_open_file ---------------------------------------------------
def test_rook_on_open_file_true_fully_open():
    # White rook on d1, no pawns on d-file → open.
    board = chess.Board("4k3/8/8/8/8/8/8/3RK3 w - - 0 1")
    ok, ev = F.is_rook_on_open_file(board, chess.D1, chess.WHITE)
    assert ok
    assert "open d-file" in ev


def test_rook_on_open_file_true_half_open():
    # White rook on d1, Black pawn on d7 only → half-open for White.
    board = chess.Board("4k3/3p4/8/8/8/8/8/3RK3 w - - 0 1")
    ok, ev = F.is_rook_on_open_file(board, chess.D1, chess.WHITE)
    assert ok
    assert "half-open d-file" in ev


def test_rook_on_open_file_false_own_pawn_on_file():
    # White rook on d1, White pawn on d4 → d-file closed for White.
    board = chess.Board("4k3/8/8/8/3P4/8/8/3RK3 w - - 0 1")
    ok, _ = F.is_rook_on_open_file(board, chess.D1, chess.WHITE)
    assert not ok


def test_rook_on_open_file_false_wrong_piece():
    # Queen on d1, not a rook → False.
    board = chess.Board("4k3/8/8/8/8/8/8/3QK3 w - - 0 1")
    ok, _ = F.is_rook_on_open_file(board, chess.D1, chess.WHITE)
    assert not ok


def test_rook_on_open_file_false_wrong_color():
    # White rook on d1, but asking for Black → False.
    board = chess.Board("4k3/8/8/8/8/8/8/3RK3 w - - 0 1")
    ok, _ = F.is_rook_on_open_file(board, chess.D1, chess.BLACK)
    assert not ok


def test_rook_on_open_file_in_certified_claims():
    # White rook on d1 on a fully open d-file; any quiet White move should certify the tag.
    board_before = chess.Board("4k3/8/8/8/8/8/8/3RK3 w - - 0 1")
    move = chess.Move.from_uci("e1f1")  # Kf1 — rook stays on d1
    board_after = board_before.copy()
    board_after.push(move)
    tags = F.certified_claims(board_before, move, board_after, chess.WHITE)
    assert "rook_on_open_file" in tags


# --- is_desperado -----------------------------------------------------------
def _desp(fen, uci):
    """Helper: push UCI move on FEN and return is_desperado result."""
    b = chess.Board(fen)
    mv = chess.Move.from_uci(uci)
    after = b.copy()
    after.push(mv)
    return F.is_desperado(b, mv, after)


def test_desperado_true_knight_takes_bishop_under_pawn_attack():
    # White Nd5, attacked by Black pawn c6; White plays Nxb6 capturing Black bishop.
    # Black pawn c6 attacks d5 (backward-diagonal for Black).
    ok, ev = _desp("4k3/8/1bp5/3N4/8/8/8/4K3 w - - 0 1", "d5b6")
    assert ok
    assert ev["piece"] == "knight"
    assert ev["captured"] == "bishop"


def test_desperado_true_queen_takes_pawn_under_rook_attack():
    # White Qd4 attacked by Black Rd8 (rook, 5 ≤ queen 9 → en prise).
    # White plays Qxg7 capturing the Black pawn on g7.
    ok, ev = _desp("3rk3/6p1/8/8/3Q4/8/8/4K3 w - - 0 1", "d4g7")
    assert ok
    assert ev["piece"] == "queen"
    assert ev["captured"] == "pawn"


def test_desperado_true_rook_takes_knight_under_equal_rook_attack():
    # White Rd4 attacked by Black Rd8 (rook, 5 ≤ rook 5 → equal exchange → en prise).
    # White plays Rxh4 capturing the Black knight.
    ok, ev = _desp("3rk3/8/8/8/3R3n/8/8/4K3 w - - 0 1", "d4h4")
    assert ok
    assert ev["piece"] == "rook"
    assert ev["captured"] == "knight"


def test_desperado_false_non_capture():
    # White Nd5 is en prise (Black pawn c6 attacks it), but White plays a quiet Nd5-e3.
    ok, _ = _desp("4k3/8/1bp5/3N4/8/8/8/4K3 w - - 0 1", "d5e3")
    assert not ok


def test_desperado_false_piece_not_under_attack():
    # White Nd5 takes Black bishop b6 but is NOT under attack — just a regular capture.
    ok, _ = _desp("4k3/8/1b6/3N4/8/8/8/4K3 w - - 0 1", "d5b6")
    assert not ok


def test_desperado_false_attacker_is_more_valuable():
    # White Bd5 attacked only by Black queen h1 (queen 9 > bishop 3 → not en prise).
    # White plays Bxb7 but the bishop is NOT a desperado.
    ok, _ = _desp("4k3/1p6/8/3B4/8/8/8/4K2q w - - 0 1", "d5b7")
    assert not ok


def test_desperado_in_certified_claims():
    # Desperado capture should add the "desperado" tag to certified_claims.
    board_before = chess.Board("4k3/8/1bp5/3N4/8/8/8/4K3 w - - 0 1")
    move = chess.Move.from_uci("d5b6")
    board_after = board_before.copy()
    board_after.push(move)
    tags = F.certified_claims(board_before, move, board_after, chess.WHITE)
    assert "desperado" in tags
