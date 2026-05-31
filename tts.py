"""
Text-to-speech for Greco reports.

Uses the Windows built-in speech engine (System.Speech via PowerShell), so it
needs NO pip install and no network — important on this machine, where pip and
SSL are fragile. Two entry points:

  speak_text(text)            -> read the text aloud on the default audio device
  save_audio(text, out_path)  -> synthesize the text to a .wav file

`to_speakable_text(markdown)` strips Markdown/board-image/scene-break noise so
the engine reads clean prose rather than punctuation and file paths.
"""

from __future__ import annotations

import platform
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Optional


def to_speakable_text(markdown: str) -> str:
    """Reduce a Markdown narrative to clean prose suitable for reading aloud."""
    text = markdown

    # Drop fenced code blocks entirely (the move list, etc.).
    text = re.sub(r"```.*?```", "", text, flags=re.DOTALL)
    # Drop image embeds: ![alt](path)
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", text)
    # Turn links [text](url) into just text.
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)
    # Remove scene-break production markers.
    text = text.replace("[SCENE BREAK]", " ")
    # Strip heading hashes but keep the heading words (as their own sentence).
    text = re.sub(r"^#{1,6}\s*", "", text, flags=re.MULTILINE)
    # Strip blockquote markers and horizontal rules.
    text = re.sub(r"^\s*>\s?", "", text, flags=re.MULTILINE)
    text = re.sub(r"^\s*-{3,}\s*$", "", text, flags=re.MULTILINE)
    # Strip emphasis / inline-code characters.
    text = text.replace("**", "").replace("`", "")
    text = re.sub(r"(?<!\w)[*_](?=\w)", "", text)
    text = re.sub(r"(?<=\w)[*_](?!\w)", "", text)
    # Collapse 3+ newlines to a paragraph break; tidy whitespace.
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    return text.strip()


def _run_powershell_speech(text: str, wav_path: Optional[Path], rate: int) -> None:
    """
    Drive System.Speech via a temp PowerShell script. If wav_path is given the
    speech is written there; otherwise it plays on the default audio device.
    """
    if platform.system() != "Windows":
        raise RuntimeError(
            "Greco's text-to-speech currently requires Windows (System.Speech)."
        )

    # Write the narration text to a UTF-8 temp file so we avoid all quoting issues.
    txt_file = Path(tempfile.gettempdir()) / "greco_tts_input.txt"
    txt_file.write_text(text, encoding="utf-8")

    rate = max(-10, min(10, int(rate)))

    if wav_path is not None:
        wav_path = Path(wav_path)
        wav_path.parent.mkdir(parents=True, exist_ok=True)
        output_setup = f'$s.SetOutputToWaveFile("{wav_path}")'
    else:
        output_setup = "$s.SetOutputToDefaultAudioDevice()"

    ps_script = f"""
Add-Type -AssemblyName System.Speech
$s = New-Object System.Speech.Synthesis.SpeechSynthesizer
$s.Rate = {rate}
{output_setup}
$text = [System.IO.File]::ReadAllText("{txt_file}", [System.Text.Encoding]::UTF8)
$s.Speak($text)
$s.Dispose()
"""
    ps_file = Path(tempfile.gettempdir()) / "greco_tts_run.ps1"
    ps_file.write_text(ps_script, encoding="utf-8")

    subprocess.run(
        ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(ps_file)],
        check=True,
    )


def speak_text(text: str, rate: int = 0) -> None:
    """Read `text` aloud on the default audio device (blocks until finished)."""
    _run_powershell_speech(text, wav_path=None, rate=rate)


def save_audio(text: str, out_path: Path, rate: int = 0) -> Path:
    """Synthesize `text` to a .wav file and return its path."""
    out_path = Path(out_path)
    _run_powershell_speech(text, wav_path=out_path, rate=rate)
    return out_path


def list_voices() -> str:
    """Return the installed SAPI voice names (for troubleshooting)."""
    if platform.system() != "Windows":
        return "(not Windows)"
    ps = (
        "Add-Type -AssemblyName System.Speech; "
        "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
        "$s.GetInstalledVoices() | ForEach-Object { $_.VoiceInfo.Name }"
    )
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-Command", ps],
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


if __name__ == "__main__":
    # Quick manual test: python tts.py "Hello from Greco"
    sample = sys.argv[1] if len(sys.argv) > 1 else "Hello, this is Greco."
    print("Installed voices:\n", list_voices())
    speak_text(sample)
