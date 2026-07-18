"""Tests for outputs.archive_reported_pgn — filing reported PGNs into the
'Games with Reports' sub-folder of the PGN library."""

from pathlib import Path

from outputs import REPORTED_GAMES_DIRNAME, archive_reported_pgn


PGN_TEXT = '[White "A"]\n[Black "B"]\n\n1. e4 e5 *\n'


def _make_pgn(folder: Path, name: str = "game.pgn", text: str = PGN_TEXT) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    p = folder / name
    p.write_text(text, encoding="utf-8")
    return p


def test_moves_pgn_from_library_root(tmp_path):
    lib = tmp_path / "lib"
    src = _make_pgn(lib)
    dest = archive_reported_pgn(src, library_dir=lib)
    assert dest == lib / REPORTED_GAMES_DIRNAME / "game.pgn"
    assert dest.is_file()
    assert not src.exists()


def test_ignores_pgn_already_in_subfolder(tmp_path):
    lib = tmp_path / "lib"
    src = _make_pgn(lib / REPORTED_GAMES_DIRNAME)
    assert archive_reported_pgn(src, library_dir=lib) is None
    assert src.is_file()


def test_ignores_pgn_outside_library(tmp_path):
    lib = tmp_path / "lib"
    lib.mkdir()
    src = _make_pgn(tmp_path / "elsewhere")
    assert archive_reported_pgn(src, library_dir=lib) is None
    assert src.is_file()


def test_ignores_missing_file(tmp_path):
    lib = tmp_path / "lib"
    lib.mkdir()
    assert archive_reported_pgn(lib / "nope.pgn", library_dir=lib) is None


def test_identical_collision_drops_duplicate(tmp_path):
    lib = tmp_path / "lib"
    archived = _make_pgn(lib / REPORTED_GAMES_DIRNAME)
    src = _make_pgn(lib)
    dest = archive_reported_pgn(src, library_dir=lib)
    assert dest == archived
    assert not src.exists()
    assert len(list((lib / REPORTED_GAMES_DIRNAME).iterdir())) == 1


def test_differing_collision_gets_numbered_name(tmp_path):
    lib = tmp_path / "lib"
    _make_pgn(lib / REPORTED_GAMES_DIRNAME, text='[White "X"]\n\n1. d4 *\n')
    src = _make_pgn(lib)
    dest = archive_reported_pgn(src, library_dir=lib)
    assert dest == lib / REPORTED_GAMES_DIRNAME / "game (2).pgn"
    assert dest.read_text(encoding="utf-8") == PGN_TEXT
    assert not src.exists()
