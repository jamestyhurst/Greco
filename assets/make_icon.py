# -*- coding: utf-8 -*-
"""Generate Greco's app icon.

A medieval-style chess KING (♚) in ivory on a gold-rimmed wine-red medallion —
clearly chess, with an old/heraldic, regal feel (an homage to Greco's 1600s era).
Writes assets/greco.ico (multi-size: 16-256) and assets/greco.png (256).

Re-run with:  python assets/make_icon.py
"""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

OUT = Path(__file__).resolve().parent
S = 1024  # render large, then downscale for crispness

# Medieval palette: antique gold, wine red, ivory.
GOLD = (198, 158, 56, 255)
GOLD_HI = (230, 198, 112, 255)
WINE = (114, 26, 36, 255)
WINE_DK = (70, 14, 22, 255)
IVORY = (244, 235, 208, 255)
SHADOW = (35, 8, 12, 150)

KING = "♚"  # ♚ BLACK CHESS KING (solid silhouette)
FONT_PATH = r"C:\Windows\Fonts\seguisym.ttf"


def centered_glyph(size, glyph, font, fill, dx=0, dy=0):
    """Return an RGBA layer with `glyph` centered by its INK bounds (not font metrics)."""
    probe = Image.new("RGBA", size, (0, 0, 0, 0))
    ImageDraw.Draw(probe).text((0, 0), glyph, font=font, fill=fill, anchor="lt")
    bbox = probe.getbbox()
    if not bbox:
        return probe
    gw, gh = bbox[2] - bbox[0], bbox[3] - bbox[1]
    px = (size[0] - gw) // 2 - bbox[0] + dx
    py = (size[1] - gh) // 2 - bbox[1] + dy
    out = Image.new("RGBA", size, (0, 0, 0, 0))
    ImageDraw.Draw(out).text((px, py), glyph, font=font, fill=fill, anchor="lt")
    return out


img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
d = ImageDraw.Draw(img)
c = S / 2

# Medallion: gold disk -> lighter gold -> wine field, leaving a gold rim.
for r, col in ((0.480, GOLD), (0.455, GOLD_HI), (0.430, WINE)):
    d.ellipse([c - S * r, c - S * r, c + S * r, c + S * r], fill=col)
# Thin dark inner ring for depth.
rf = 0.430
d.ellipse([c - S * rf, c - S * rf, c + S * rf, c + S * rf],
          outline=WINE_DK, width=int(S * 0.013))

font = ImageFont.truetype(FONT_PATH, int(S * 0.60))
# Drop shadow, then the ivory king.
img.alpha_composite(centered_glyph((S, S), KING, font, SHADOW, dx=int(S * 0.012), dy=int(S * 0.02)))
img.alpha_composite(centered_glyph((S, S), KING, font, IVORY, dy=int(S * 0.005)))

png = OUT / "greco.png"
img.resize((256, 256), Image.LANCZOS).save(png)

ico = OUT / "greco.ico"
img.save(ico, sizes=[(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)])

print("wrote:", png)
print("wrote:", ico)
