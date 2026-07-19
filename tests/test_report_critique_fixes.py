"""Regression tests for the 2026-07-18 report-critique fixes.

Source of truth: James's verbatim notes in
`Developer Notes (Greco)\\Report Critique Notes (7-18-2026)\\Developer Critique (mpena06).md`.
Each section below locks in one fix so a future refactor can't quietly undo it:

  * item 9  — detect_sacrifice settles the exchange (an offered trade like
              9. a3 inviting ...Bxc3+ bxc3 is NOT a "sound sacrifice")
  * item 11 — best_move_attacks ground truth for the ENGINE'S move (so
              "...f6 strikes at your centre" can't be invented)
  * item 6  — the featured-quote garble/relevance guard (the corrupted 1883
              tournament-table fragment must never be quotable)
  * item 3  — non-checkmate endings marked in the move list and PGN viewer
  * item 2  — move sounds present in the viewer
  * item 4  — steppable, parenthetical engine lines in the viewer
  * items 5/7/8/10/12-16/18/19 — prompt-content assertions for the new
              narrator rules (tagged PENDING_APPROVAL in narrator.py)
"""
import chess

from analyzer import GameAnalysis, MoveAnalysis, detect_sacrifice, material_balance
from knowledge import _best_quotable_sentence
from narrator import SYSTEM_PROMPT_BASE, _move_to_dict
from outputs import (
    _pv_to_fen_plies,
    build_pgn_viewer,
    format_move_list,
    termination_reason,
)

START_FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
AFTER_E4 = "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3 0 1"


# --------------------------------------------------------------------------
# Item 9 — an offered trade is not a sacrifice (detect_sacrifice settles the
# exchange with the mover's recapture before measuring investment).
# --------------------------------------------------------------------------

def test_offered_trade_is_not_a_sound_sacrifice():
    # 1. Nf3 d5 2. c4 e6 3. Nc3 Bb4 4. a3 — the mpena06 shape. The engine's
    # reply ...Bxc3 "wins a knight" for exactly one ply; bxc3 takes the bishop
    # straight back. The OLD check measured material after ...Bxc3 only and
    # flagged a3 as a sound KNIGHT SACRIFICE; settled, it is an even trade.
    board = chess.Board()
    for san in ["Nf3", "d5", "c4", "e6", "Nc3", "Bb4"]:
        board.push_san(san)
    mat_before = material_balance(board)  # before White's a3
    board.push_san("a3")
    reply = board.parse_san("Bxc3+") if board.is_legal(board.parse_san("Bxc3+")) else None
    assert reply is not None
    is_sac, is_brill, invested = detect_sacrifice(
        mat_before, board, reply, chess.WHITE, eval_after_norm_white=150, cp_loss=10
    )
    assert not is_sac, "an offered bishop-for-knight trade must not be a 'sound sacrifice'"
    assert not is_brill
    assert invested < 1.5


def test_true_sacrifice_still_fires_after_settling():
    # A Greek-gift-shaped Bxh7+ Kxh7: the mover has NO recapture on h7, so the
    # invested material survives the settling step and the flag still fires.
    board = chess.Board("rnbq1rk1/pppp1ppp/5n2/2b5/8/3B1N2/PPPP1PPP/RNBQK2R w KQ - 0 1")
    mat_before = material_balance(board)
    board.push_san("Bxh7+")
    reply = board.parse_san("Kxh7")
    is_sac, _brill, invested = detect_sacrifice(
        mat_before, board, reply, chess.WHITE, eval_after_norm_white=300, cp_loss=0
    )
    assert invested >= 1.5, "bishop for pawn with no recapture is a real investment"
    assert is_sac


# --------------------------------------------------------------------------
# Item 11 — ground truth for what the ENGINE'S move attacks.
# --------------------------------------------------------------------------

def _mv(tier=2, **overrides):
    kwargs = dict(
        ply=1, move_number=1, side="White",
        san="e4", uci="e2e4",
        fen_before=START_FEN, fen_after=AFTER_E4,
        eval_before_cp=20, mate_before=None,
        eval_after_cp=25, mate_after=None,
        best_move_san="d4", best_move_uci="d2d4",
        best_pv_san="1. d4", cp_loss=15,
    )
    kwargs.update(overrides)
    return _move_to_dict(MoveAnalysis(**kwargs), tier)


def test_best_attacks_emitted_even_when_empty():
    # An empty list is affirmative evidence: the engine's move attacks NOTHING,
    # so the narrator may not write that it "strikes at the centre".
    d = _mv(tier=2, best_move_attacks=[])
    assert d["best_attacks"] == []


def test_best_attacks_lists_real_targets():
    d = _mv(tier=3, best_move_attacks=["pawn on d5"])
    assert d["best_attacks"] == ["pawn on d5"]


def test_best_attacks_absent_when_best_equals_played():
    d = _mv(tier=2, best_move_san="e4", best_move_uci="e2e4", cp_loss=0)
    assert "best_attacks" not in d


def test_best_attacks_absent_below_tier_two():
    d = _mv(tier=1, best_move_attacks=["pawn on d5"])
    assert "best_attacks" not in d


# --------------------------------------------------------------------------
# Item 16 — a "pawn fork" on a defended, unsupported square is not a threat.
# --------------------------------------------------------------------------

def test_defended_unsupported_fork_square_is_suppressed():
    # The exact game position: JamesTortoise vs. mpena06 after 17...Bd6. The old
    # detector reported "allows e7, a pawn fork hitting the queen on d8 and the
    # rook on f8" — but the d8-queen (and the d6-bishop) guard e7 and nothing of
    # White's supports it, so e7 would simply be captured.
    from analyzer import detect_allowed_pawn_fork
    board = chess.Board()
    for san in ["Nf3", "d5", "c4", "Nf6", "cxd5", "Nxd5", "e4", "Nb6",
                "Nc3", "e6", "d4", "Bb4", "Be3", "O-O", "Bd3", "Nc6",
                "a3", "Be7", "O-O", "Nd7", "Qc2", "b6", "Nb5", "Bb7",
                "Rfd1", "a6", "d5", "Nc5", "Nc3", "Nxd3", "Rxd3", "Na7",
                "dxe6", "Bd6"]:
        board.push_san(san)
    result = detect_allowed_pawn_fork(board, chess.BLACK)
    assert result is None or "e7" not in result, (
        "e7 is guarded by the d8-queen and unsupported — not a real fork threat"
    )


def test_supported_fork_still_detected():
    # The canonical real fork: Black rook on f4 + bishop on h4 invite g3. The
    # h4-bishop technically guards g3, but the push is supported by the f2/h2
    # pawns, so ...Bxg3 loses material — the fork is genuine and must survive.
    from analyzer import detect_allowed_pawn_fork
    board = chess.Board("6k1/8/8/8/5r1b/8/5PPP/6K1 w - - 0 1")
    result = detect_allowed_pawn_fork(board, chess.BLACK)
    assert result is not None and "g3" in result


# --------------------------------------------------------------------------
# Item 6 — the garbled 1883 fragment must never survive the quote guard.
# --------------------------------------------------------------------------

GARBLED_1883 = (
    "12, 8!, 13, 152, 15}, 6, 91, 71, 13, 6,16 = 123 —14 0 The analytical "
    "results of the Tournament are of no great importance."
)


def test_garbled_ocr_fragment_is_rejected():
    assert _best_quotable_sentence(GARBLED_1883, ["tournament", "analytical"]) == ""


def test_digit_dense_fragment_rejected_even_without_braces():
    text = (
        "12, 8, 13, 152, 15, 6, 91, 71 the analytical results of the "
        "Tournament are of no great importance."
    )
    assert _best_quotable_sentence(text, ["tournament", "analytical"]) == ""


def test_zero_overlap_sentence_is_not_featured():
    # An irrelevant aside is worse than no quote at all: with no query-word
    # overlap the sentence must not be selected.
    text = "This perfectly clean sentence has nothing whatever to do with the theme."
    assert _best_quotable_sentence(text, ["endgame", "zugzwang"]) == ""


def test_clean_relevant_sentence_still_selected():
    text = (
        "The analytical results of the tournament are of lasting importance "
        "to every student of the openings."
    )
    got = _best_quotable_sentence(text, ["tournament", "openings"])
    assert got.startswith("The analytical results")


# --------------------------------------------------------------------------
# Item 3 — non-checkmate endings marked visibly.
# --------------------------------------------------------------------------

def test_termination_reason_priorities():
    assert termination_reason({}, "Qg7#") == "checkmate"
    assert termination_reason(
        {"Termination": "JamesTortoise won by resignation", "Result": "1-0"}, "Kf5"
    ) == "resignation"
    assert termination_reason({"Termination": "Time forfeit", "Result": "0-1"}, "a3") == "on time"
    assert termination_reason({"Result": "1-0"}, "Kf5") == "resignation"
    assert termination_reason({"Result": "1/2-1/2"}, "Kf5") == "draw"
    assert termination_reason({"Result": "*"}, "e4") == ""


def _one_move_game(result="1-0", headers=None):
    move = MoveAnalysis(
        ply=1, move_number=1, side="White",
        san="e4", uci="e2e4",
        fen_before=START_FEN, fen_after=AFTER_E4,
        eval_before_cp=20, mate_before=None,
        eval_after_cp=25, mate_after=None,
        best_move_san="e4", best_move_uci="e2e4",
        best_pv_san="1. e4", cp_loss=0,
    )
    return GameAnalysis(
        headers=headers or {"White": "Alice", "Black": "Bob", "Result": result,
                            "Termination": "Alice won by resignation"},
        moves=[move],
        result=result,
        final_eval_cp=25,
        final_mate=None,
    )


def test_move_list_marks_resignation():
    listing = format_move_list(_one_move_game())
    assert listing.endswith("1-0 (resignation)")


def test_viewer_payload_carries_result_and_reason():
    html = build_pgn_viewer(_one_move_game())
    assert '"result": "1-0"' in html
    assert '"term": "resignation"' in html
    assert "gv-result" in html  # the move-list marker is rendered by the JS


# --------------------------------------------------------------------------
# Items 2 & 4 — viewer sounds and steppable, parenthetical engine lines.
# --------------------------------------------------------------------------

def test_viewer_has_sound_toggle_and_synth():
    html = build_pgn_viewer(_one_move_game())
    assert 'id="gv-sound"' in html
    assert "moveSound" in html
    assert "greco_viewer_muted" in html  # preference persists


def test_viewer_has_variation_stepping():
    html = build_pgn_viewer(_one_move_game())
    assert "enterVar" in html and "exitVar" in html
    assert "Escape" in html  # Esc leaves the variation


def test_pv_plies_carry_display_labels():
    plies = _pv_to_fen_plies(START_FEN, "1. e4 e5 2. Nf3")
    assert [p["lbl"] for p in plies] == ["1. ", "", "2. "]
    board = chess.Board()
    board.push_san("e4")
    plies = _pv_to_fen_plies(board.fen(), "1...c5 2. Nf3")
    assert [p["lbl"] for p in plies] == ["1... ", "2. "]


# --------------------------------------------------------------------------
# Prompt-content assertions — the new narrator rules must stay in the prompt.
# --------------------------------------------------------------------------

def test_prompt_diagram_first_rule():
    assert "The diagram comes first, the words after." in SYSTEM_PROMPT_BASE


def test_prompt_no_allusion_rule():
    assert "Never discuss a move only by allusion." in SYSTEM_PROMPT_BASE


def test_prompt_no_logistics_restatement():
    assert "Don't restate logistics the player already knows." in SYSTEM_PROMPT_BASE


def test_prompt_club_reader_bare_san():
    assert "The inverse holds for stronger readers:" in SYSTEM_PROMPT_BASE


def test_prompt_zwischenzug_pattern():
    assert "Reflexive replies and the zwischenzug." in SYSTEM_PROMPT_BASE


def test_prompt_plan_inference_before_pejoratives():
    assert "Infer the plan from the follow-up moves" in SYSTEM_PROMPT_BASE


def test_prompt_psychology_vs_optimal_shape():
    assert "psychology-versus-optimal contrast" in SYSTEM_PROMPT_BASE


def test_prompt_contextualize_engine_and_best_attacks():
    assert "Contextualize an unnatural engine suggestion" in SYSTEM_PROMPT_BASE
    assert "best_attacks" in SYSTEM_PROMPT_BASE


def test_prompt_trade_vs_sacrifice_rule():
    assert "TRADE — never call it a \"sacrifice.\"" in SYSTEM_PROMPT_BASE


def test_prompt_battery_definition():
    assert '"Battery" has a precise meaning' in SYSTEM_PROMPT_BASE


def test_prompt_doubled_pawn_prohibition():
    assert "NEVER assert doubled, isolated, or backward pawns" in SYSTEM_PROMPT_BASE


def test_prompt_fork_threat_defender_check():
    assert "under-defended target square" in SYSTEM_PROMPT_BASE


def test_prompt_pin_lever_and_piece_roles():
    assert "A pin is a lever" in SYSTEM_PROMPT_BASE
    assert "knights close in, bishops work from afar" in SYSTEM_PROMPT_BASE


def test_prompt_quote_quality_gate():
    assert "Quality gate" in SYSTEM_PROMPT_BASE
    assert "fourth-wall" in SYSTEM_PROMPT_BASE
