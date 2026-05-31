# -*- coding: utf-8 -*-
"""Generate Greco's app icon — tuned to stay CRISP at small sizes (the taskbar and
window title bar use 16-32 px). Each size is rendered on its own with the king
filling most of the frame (bold, high contrast), supersampled then downscaled, and
the .ico is assembled from those distinct per-size bitmaps (PNG-in-ICO). Also writes
assets/icon_preview.png (small sizes zoomed) so the result can be eyeballed.

Re-run with:  python assets/make_icon.py
"""
import io
import struct
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

OUT = Path(__file__).resolve().parent
GOLD = (201, 162, 58, 255)
WINE = (122, 28, 38, 255)
IVORY = (245, 237, 212, 255)
KING = "♚"  # ♚ BLACK CHESS KING (solid silhouette)
FONT = r"C:\Windows\Fonts\seguisym.ttf"
SIZES = [256, 128, 64, 48, 32, 24, 16]


def _centered(box, glyph, font, fill):
    """A `box`x`box` RGBA layer with the glyph centered by its INK bounds."""
    probe = Image.new("RGBA", (box, box), (0, 0, 0, 0))
    ImageDraw.Draw(probe).text((0, 0), glyph, font=font, fill=fill, anchor="lt")
    bb = probe.getbbox()
    if not bb:
        return probe
    gw, gh = bb[2] - bb[0], bb[3] - bb[1]
    out = Image.new("RGBA", (box, box), (0, 0, 0, 0))
    ImageDraw.Draw(out).text(((box - gw) // 2 - bb[0], (box - gh) // 2 - bb[1]),
                             glyph, font=font, fill=fill, anchor="lt")
    return out


def render(size, ss=4):
    """Render one icon bitmap at `size` px (supersampled by `ss`)."""
    R = size * ss
    img = Image.new("RGBA", (R, R), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    c, rad = R / 2.0, R * 0.49
    rim = max(float(ss), R * 0.05)
    d.ellipse([c - rad, c - rad, c + rad, c + rad], fill=GOLD)                       # gold rim
    d.ellipse([c - rad + rim, c - rad + rim, c + rad - rim, c + rad - rim], fill=WINE)  # wine field
    # King sized so its INK fills ~0.74 of the frame (big and clear).
    target = R * 0.74
    fsize = int(R * 0.92)
    font = ImageFont.truetype(FONT, fsize)
    layer = _centered(R, KING, font, IVORY)
    bb = layer.getbbox()
    if bb:
        ink_h = bb[3] - bb[1]
        if ink_h:  # rescale font so the ink hits the target height
            font = ImageFont.truetype(FONT, max(8, int(fsize * target / ink_h)))
            layer = _centered(R, KING, font, IVORY)
    img.alpha_composite(layer)
    return img.resize((size, size), Image.LANCZOS)


def build_ico(images, path):
    """Assemble a PNG-in-ICO from distinct per-size RGBA images."""
    blobs = []
    for im in images:
        b = io.BytesIO()
        im.save(b, format="PNG")
        blobs.append(b.getvalue())
    out = io.BytesIO()
    out.write(struct.pack("<HHH", 0, 1, len(images)))
    offset = 6 + len(images) * 16
    for im, blob in zip(images, blobs):
        w = 0 if im.width >= 256 else im.width
        h = 0 if im.height >= 256 else im.height
        out.write(struct.pack("<BBBBHHII", w, h, 0, 0, 1, 32, len(blob), offset))
        offset += len(blob)
    for blob in blobs:
        out.write(blob)
    Path(path).write_bytes(out.getvalue())


rendered = {s: render(s) for s in SIZES}
build_ico([rendered[s] for s in SIZES], OUT / "greco.ico")
rendered[256].save(OUT / "greco.png")

# Preview: small sizes zoomed with NEAREST so the real pixels are visible.
show, zoom, pad = [16, 24, 32, 48, 64], 9, 12
mw = sum(s * zoom for s in show) + pad * (len(show) + 1)
mh = max(s * zoom for s in show) + pad * 2
prev = Image.new("RGBA", (mw, mh), (105, 105, 105, 255))
x = pad
for s in show:
    big = rendered[s].resize((s * zoom, s * zoom), Image.NEAREST)
    prev.alpha_composite(big, (x, pad))
    x += s * zoom + pad
prev.convert("RGB").save(OUT / "icon_preview.png")

print("wrote greco.ico (sizes %s), greco.png, icon_preview.png" % SIZES)
