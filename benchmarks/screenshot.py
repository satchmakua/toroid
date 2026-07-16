"""Render the flagship demo as a terminal-style PNG for the README.

This does NOT hand-author the text: it *runs* the real buggy-FIFO command, captures its
stdout verbatim, and paints those exact bytes into an image. If the tool's output
changes, so does the screenshot — regenerate with `make screenshot`.

    python -m benchmarks.screenshot        # -> docs/img/demo.png

Needs the `bench` extra (Pillow ships with matplotlib) and a Yosys on PATH (the dev
extra's `yowasp-yosys` is enough).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "docs" / "img" / "demo.png"

CMD = [
    "toroid", "verify", "designs/fifo_buggy.v", "--top", "fifo",
    "--no-llm", "--props", "designs/fifo.props.json",
]

# A dark terminal palette; the verdict colours match the report's ✅/❌ semantics.
BG = (13, 17, 23)
FG = (201, 209, 217)
DIM = (110, 118, 129)
GREEN = (63, 185, 80)
RED = (248, 81, 73)
YELLOW = (210, 153, 34)
PAD = 22
LINE_H = 20
FONT_SIZE = 15


def _colour_for(line: str) -> tuple[int, int, int]:
    if "FALSIFIED" in line or "❌" in line:
        return RED
    if "PROVEN" in line or "✅" in line:
        return GREEN
    if line.startswith("$") or "counterexample ends" in line or "←" in line:
        return YELLOW
    if line.startswith("#") or line.startswith("_"):
        return DIM
    return FG


def _font(size: int, names: tuple[str, ...]):  # type: ignore[no-untyped-def]
    from PIL import ImageFont

    for name in names:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return None


_MONO = ("consola.ttf", "DejaVuSansMono.ttf", "Menlo.ttc", "cour.ttf")
#: The report's verdict badges are emoji; a mono font has no glyph for them and would
#: draw tofu. Fall back to an emoji face for those runs only, so the picture matches
#: what a terminal actually shows.
_EMOJI = ("seguiemj.ttf", "seguisym.ttf", "NotoColorEmoji.ttf", "AppleColorEmoji.ttc")


def _runs(line: str) -> list[tuple[str, bool]]:
    """Split a line into (text, is_emoji) runs so each can use the right face."""
    out: list[tuple[str, bool]] = []
    for ch in line:
        emoji = ord(ch) > 0x2000 and ch not in "—←⟺⋮–’‘“”"
        if out and out[-1][1] == emoji:
            out[-1] = (out[-1][0] + ch, emoji)
        else:
            out.append((ch, emoji))
    return out


def main() -> int:
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        print("needs Pillow: pip install -e '.[bench]'", file=sys.stderr)
        return 2

    proc = subprocess.run(CMD, cwd=REPO, capture_output=True, text=True, timeout=300)
    # A FALSIFIED verdict exits non-zero — that is the demo working, not failing.
    body = (proc.stdout or "").rstrip("\n")
    if not body:
        print(f"no output from {' '.join(CMD)}:\n{proc.stderr}", file=sys.stderr)
        return 1

    lines = [f"$ {' '.join(CMD)}", ""] + body.splitlines()

    mono = _font(FONT_SIZE, _MONO)
    emoji_font = _font(FONT_SIZE, _EMOJI) or mono
    probe = Image.new("RGB", (10, 10))
    measure = ImageDraw.Draw(probe)
    width = max(int(measure.textlength(ln, font=mono)) for ln in lines) + PAD * 2 + 24
    height = len(lines) * LINE_H + PAD * 2

    img = Image.new("RGB", (width, height), BG)
    draw = ImageDraw.Draw(img)
    for i, ln in enumerate(lines):
        colour, x, y = _colour_for(ln), PAD, PAD + i * LINE_H
        for text, is_emoji in _runs(ln):
            face = emoji_font if is_emoji else mono
            if is_emoji:
                # Colour fonts carry their own; embedded_color keeps ✅/❌ readable.
                draw.text((x, y), text, font=face, embedded_color=True)
            else:
                draw.text((x, y), text, font=face, fill=colour)
            x += int(measure.textlength(text, font=face))

    OUT.parent.mkdir(parents=True, exist_ok=True)
    img.save(OUT)
    print(f"screenshot: {OUT}  ({width}x{height}, {len(lines)} lines of real output)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
