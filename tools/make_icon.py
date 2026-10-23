#!/usr/bin/env python3
"""Draw the MBToolkit application icon from scratch.

Every size is rendered from vector-like shapes at 4x and downsampled, so the
icon stays sharp at any size (unlike enlarging a small bitmap). The design
keeps the style of the original MBSniffer icon: dark-blue rounded tile, cyan signal line
with end nodes, magnifying glass with a square wave, and the product name in
bold italic ("MB" white, "Toolkit" cyan). At 16-32 px no text is readable, so
those sizes show the symbol only, larger.

Usage (from the project folder):
    python -B tools/make_icon.py --ico "MBToolkit vX.Y/MBToolkit.ico" --png tools/MBToolkit_icon_1024.png

Requires Pillow. Uses tools/fonts/DejaVuSans-Bold.ttf.
"""

import argparse
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

TOOLS_DIR = Path(__file__).resolve().parent
FONT_BOLD = TOOLS_DIR / "fonts" / "DejaVuSans-Bold.ttf"

ICO_SIZES = (16, 20, 24, 32, 40, 48, 64, 96, 128, 256)
TEXT_MIN_SIZE = 48          # smaller icons show the symbol only
SUPERSAMPLE = 4

NAVY_TOP = (18, 42, 78)
NAVY_BOTTOM = (6, 17, 36)
EDGE = (60, 96, 140)
CYAN = (38, 182, 255)
CYAN_DARK = (8, 120, 200)
GLASS_TOP = (24, 70, 130)
GLASS_BOTTOM = (8, 28, 60)
RING_LIGHT = (236, 242, 248)
RING_DARK = (150, 165, 182)
WHITE = (255, 255, 255)


def _vertical_gradient(size, top, bottom):
    width, height = size
    gradient = Image.new("RGB", (1, height))
    for y in range(height):
        t = y / max(1, height - 1)
        gradient.putpixel((0, y), tuple(int(a + (b - a) * t) for a, b in zip(top, bottom)))
    return gradient.resize((width, height))


def _rounded_mask(size, radius):
    mask = Image.new("L", size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, size[0] - 1, size[1] - 1),
                                           radius=radius, fill=255)
    return mask


def _italic_text(text_parts, font, shear=0.22):
    """Render [(text, colour), ...] on one line, then shear it into italics."""
    widths = [font.getbbox(text)[2] for text, _colour in text_parts]
    ascent, descent = font.getmetrics()
    width = sum(widths) + int((ascent + descent) * shear) + 8
    height = ascent + descent + 8
    image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    x = 4
    for (text, colour), part_width in zip(text_parts, widths):
        draw.text((x, 4), text, font=font, fill=colour + (255,))
        x += part_width
    return image.transform(image.size, Image.AFFINE,
                           (1, shear, -shear * height * 0.5, 0, 1, 0),
                           resample=Image.BICUBIC)


def draw_icon(size, with_text):
    """Return an RGBA icon of *size* px."""
    s = size * SUPERSAMPLE
    canvas = Image.new("RGBA", (s, s), (0, 0, 0, 0))

    # Tile: rounded square, vertical navy gradient, thin lighter edge.
    margin = round(s * 0.035)
    tile_size = (s - 2 * margin, s - 2 * margin)
    radius = round(s * 0.2)
    tile = _vertical_gradient(tile_size, NAVY_TOP, NAVY_BOTTOM).convert("RGBA")
    tile.putalpha(_rounded_mask(tile_size, radius))
    shadow = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rounded_rectangle(
        (margin, margin + s * 0.012, s - margin, s - margin + s * 0.012),
        radius=radius, fill=(0, 0, 0, 110))
    canvas.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(s * 0.012)))
    canvas.alpha_composite(tile, (margin, margin))
    draw = ImageDraw.Draw(canvas)
    draw.rounded_rectangle((margin, margin, s - margin - 1, s - margin - 1), radius=radius,
                           outline=EDGE + (255,), width=max(1, round(s * 0.008)))

    # Symbol geometry: with text the symbol sits in the upper part.
    if with_text:
        cy, lens_r, line_w = s * 0.38, s * 0.205, s * 0.022
    else:
        cy, lens_r, line_w = s * 0.46, s * 0.27, s * 0.045
    cx = s * 0.47
    node_r = line_w * 1.55

    # Signal line with end nodes (behind the lens).
    left, right = s * 0.13, s * 0.87
    draw.line((left, cy, right, cy), fill=CYAN + (255,), width=round(line_w))
    for x in (left, right):
        draw.ellipse((x - node_r, cy - node_r, x + node_r, cy + node_r), fill=CYAN + (255,))

    # Handle: diagonal from the lens rim, light metal with a darker edge.
    handle_w = lens_r * 0.32
    hx0, hy0 = cx + lens_r * 0.72, cy + lens_r * 0.72
    reach = 1.36 if with_text else 1.5   # keep the handle clear of the name
    hx1, hy1 = cx + lens_r * reach, cy + lens_r * reach
    draw.line((hx0, hy0, hx1, hy1), fill=RING_DARK + (255,), width=round(handle_w * 1.18))
    draw.line((hx0, hy0, hx1, hy1), fill=RING_LIGHT + (255,), width=round(handle_w))
    cap = handle_w * 0.5
    draw.ellipse((hx1 - cap, hy1 - cap, hx1 + cap, hy1 + cap), fill=RING_LIGHT + (255,))

    # Lens: glass gradient disc with a light ring.
    ring = lens_r * 0.16
    glass_box = (int(cx - lens_r), int(cy - lens_r), int(cx + lens_r), int(cy + lens_r))
    glass_size = (glass_box[2] - glass_box[0], glass_box[3] - glass_box[1])
    glass = _vertical_gradient(glass_size, GLASS_TOP, GLASS_BOTTOM).convert("RGBA")
    glass_mask = Image.new("L", glass_size, 0)
    ImageDraw.Draw(glass_mask).ellipse((0, 0, glass_size[0] - 1, glass_size[1] - 1), fill=255)
    glass.putalpha(glass_mask)
    canvas.alpha_composite(glass, glass_box[:2])
    draw = ImageDraw.Draw(canvas)

    # Square wave inside the lens.
    wave_w = lens_r * 1.25
    wave_h = lens_r * 0.62
    x0 = cx - wave_w / 2
    base, top = cy + wave_h / 2, cy - wave_h / 2
    step = wave_w / 5
    points = [(x0 - lens_r * 0.1, base), (x0, base), (x0, top), (x0 + step, top),
              (x0 + step, base), (x0 + 2 * step, base), (x0 + 2 * step, top),
              (x0 + 3 * step, top), (x0 + 3 * step, base), (x0 + 4 * step, base),
              (x0 + 4 * step, top), (x0 + 5 * step, top), (x0 + 5 * step, base),
              (x0 + 5 * step + lens_r * 0.1, base)]
    draw.line(points, fill=CYAN + (255,), width=round(line_w * 0.95), joint="curve")

    # Highlight on the glass and the ring on top.
    hl = lens_r * 0.62
    draw.arc((cx - hl, cy - hl, cx + hl, cy + hl), start=200, end=255,
             fill=(255, 255, 255, 90), width=max(1, round(lens_r * 0.07)))
    draw.ellipse((cx - lens_r, cy - lens_r, cx + lens_r, cy + lens_r),
                 outline=RING_DARK + (255,), width=round(ring * 1.25))
    draw.ellipse((cx - lens_r + ring * 0.12, cy - lens_r + ring * 0.12,
                  cx + lens_r - ring * 0.12, cy + lens_r - ring * 0.12),
                 outline=RING_LIGHT + (255,), width=round(ring))

    if with_text:
        font = ImageFont.truetype(str(FONT_BOLD), round(s * 0.19))
        text = _italic_text([("MB", WHITE), ("Toolkit", CYAN)], font)
        max_width = s * 0.84
        if text.width > max_width:
            ratio = max_width / text.width
            text = text.resize((round(text.width * ratio), round(text.height * ratio)),
                               Image.LANCZOS)
        tx = round((s - text.width) / 2)
        ty = round(s * 0.88 - text.height)
        outline = text.split()[3].filter(ImageFilter.MaxFilter(5))
        dark = Image.new("RGBA", text.size, NAVY_BOTTOM + (0,))
        dark.putalpha(outline.point(lambda a: int(a * 0.6)))
        canvas.alpha_composite(dark, (tx, ty + round(s * 0.006)))
        canvas.alpha_composite(text, (tx, ty))

    return canvas.resize((size, size), Image.LANCZOS)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--ico", required=True, help="Output .ico path")
    parser.add_argument("--png", help="Optional large PNG (1024 px) for documents")
    parser.add_argument("--preview", help="Optional preview sheet PNG with every size")
    args = parser.parse_args(argv)

    frames = [draw_icon(size, size >= TEXT_MIN_SIZE) for size in ICO_SIZES]
    largest = frames[-1]
    largest.save(args.ico, format="ICO", sizes=[(f.width, f.height) for f in frames],
                 append_images=frames[:-1])
    print(f"wrote {args.ico} ({', '.join(str(s) for s in ICO_SIZES)} px)")

    if args.png:
        draw_icon(1024, True).save(args.png)
        print(f"wrote {args.png}")
    if args.preview:
        sheet = Image.new("RGBA", (sum(ICO_SIZES) + 12 * len(ICO_SIZES) + 12, 280),
                          (240, 242, 245, 255))
        x = 12
        for frame in frames:
            sheet.alpha_composite(frame, (x, 268 - frame.height))
            x += frame.width + 12
        sheet.save(args.preview)
        print(f"wrote {args.preview}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
