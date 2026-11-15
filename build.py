#!/usr/bin/env python3
"""
Build the Ahmi Pixel fonts from glyphs/ahmi-pixel.txt.

    python build.py            # writes fonts/AhmiPixel-{Regular,Bold}.{ttf,woff2}

Needs: pip install fonttools brotli

The glyph file is the only source. Regular is exactly the drawn pixels.
Bold thickens every pixel one step to the right (2px stems, 1px bars) unless
the glyph file gives a hand-drawn "@bold" version.

Metrics: one font pixel is 1/8 of the em, so text is pixel-sharp at any size
that is a multiple of 8px (16, 24, 32, 40, 48, 64 ...).
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "glyphs" / "ahmi-pixel.txt"
OUT = ROOT / "fonts"

FAMILY = "Ahmi Pixel"
VERSION = "1.000"
UPM = 1024
PX = 128          # one drawn pixel, in font units (8 pixels per em)
CAP_ROWS = 7      # rows above the baseline
DESC_ROWS = 2     # rows below it

Bitmap = list[str]


def parse(path: Path = SOURCE) -> tuple[dict[int, tuple[str, Bitmap]], dict[int, Bitmap]]:
    """Return ({codepoint: (name, rows)}, {codepoint: bold rows})."""
    regular: dict[int, tuple[str, Bitmap]] = {}
    bold: dict[int, Bitmap] = {}
    current: tuple[bool, int, str] | None = None
    rows: Bitmap = []

    def flush() -> None:
        nonlocal rows
        if current is None:
            return
        is_bold, cp, name = current
        if not rows:
            raise ValueError(f"{name}: no rows")
        if len(rows) > CAP_ROWS + DESC_ROWS:
            raise ValueError(f"{name}: {len(rows)} rows, at most {CAP_ROWS + DESC_ROWS} allowed")
        width = max(len(r) for r in rows)
        grid = [r.ljust(width, ".") for r in rows]
        grid += ["." * width] * (CAP_ROWS + DESC_ROWS - len(grid))
        if is_bold:
            bold[cp] = grid
        else:
            if cp in regular:
                raise ValueError(f"U+{cp:04X} defined twice")
            regular[cp] = (name, grid)
        rows = []

    for n, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.rstrip()
        if line.startswith("@"):
            flush()
            parts = line.split()
            if len(parts) != 3 or not parts[1].startswith("U+"):
                raise ValueError(f"line {n}: expected '@ U+XXXX name', got {line!r}")
            current = (parts[0] == "@bold", int(parts[1][2:], 16), parts[2])
        elif not line or line.startswith("# ") or (line == "#" and current is None):
            continue  # blank line or comment (a lone '#' inside a glyph is a pixel)
        else:
            if set(line) - {"#", "."}:
                raise ValueError(f"line {n}: only '#' and '.' allowed in a glyph row: {line!r}")
            if current is None:
                raise ValueError(f"line {n}: glyph row before any '@' header")
            rows.append(line)
    flush()
    return regular, bold


def embolden(grid: Bitmap) -> Bitmap:
    """Thicken one pixel to the right: the classic 8-bit bold."""
    out = []
    for row in grid:
        cells = [c == "#" for c in row] + [False]
        out.append("".join("#" if cells[x] or (x > 0 and cells[x - 1]) else "." for x in range(len(cells))))
    return out


def bitmaps(weight: str) -> dict[int, tuple[str, Bitmap]]:
    """Final pixel grids for 'regular' or 'bold'."""
    regular, bold = parse()
    if weight == "regular":
        return regular
    out = {}
    for cp, (name, grid) in regular.items():
        if cp in bold:
            out[cp] = (name, bold[cp])
        elif any("#" in r for r in grid):
            out[cp] = (name, embolden(grid))
        else:
            out[cp] = (name, grid)  # spaces keep their width
    return out


def outline(grid: Bitmap) -> list[list[tuple[int, int]]]:
    """Trace the pixel grid into closed contours (pixel units, y up).

    Outer contours come out clockwise and counters counter-clockwise, which is
    what TrueType expects. Pixels that only touch at a corner stay separate.
    """
    cells = {
        (x, CAP_ROWS - 1 - r)
        for r, row in enumerate(grid)
        for x, c in enumerate(row)
        if c == "#"
    }
    edges: set[tuple[tuple[int, int], tuple[int, int]]] = set()
    for x, y in cells:
        for a, b in (
            ((x, y), (x, y + 1)),
            ((x, y + 1), (x + 1, y + 1)),
            ((x + 1, y + 1), (x + 1, y)),
            ((x + 1, y), (x, y)),
        ):
            if (b, a) in edges:
                edges.remove((b, a))  # shared wall between two pixels
            else:
                edges.add((a, b))
    outgoing: dict[tuple[int, int], list[tuple[int, int]]] = {}
    for a, b in edges:
        outgoing.setdefault(a, []).append(b)

    contours = []
    while outgoing:
        start = min(outgoing)
        prev, cur = start, outgoing[start].pop()
        if not outgoing[start]:
            del outgoing[start]
        loop = [start]
        while cur != start:
            loop.append(cur)
            options = outgoing[cur]
            dx, dy = cur[0] - prev[0], cur[1] - prev[1]
            # where two pixels meet at a corner, take the right-hand turn
            nxt = min(options, key=lambda p: dx * (p[1] - cur[1]) - dy * (p[0] - cur[0]))
            options.remove(nxt)
            if not options:
                del outgoing[cur]
            prev, cur = cur, nxt
        # drop points that sit on a straight run
        slim = []
        for i, p in enumerate(loop):
            a, b = loop[i - 1], loop[(i + 1) % len(loop)]
            if (p[0] - a[0]) * (b[1] - p[1]) != (p[1] - a[1]) * (b[0] - p[0]):
                slim.append(p)
        contours.append(slim)
    return contours


def build(weight: str) -> Path:
    from fontTools.fontBuilder import FontBuilder
    from fontTools.pens.ttGlyphPen import TTGlyphPen

    is_bold = weight == "bold"
    style = "Bold" if is_bold else "Regular"
    grids = bitmaps(weight)

    order = [".notdef"]
    cmap: dict[int, str] = {}
    glyphs = {}
    metrics = {}

    def add(name: str, grid: Bitmap) -> None:
        pen = TTGlyphPen(None)
        xs = []
        for contour in outline(grid):
            pts = [(x * PX, y * PX) for x, y in contour]
            xs += [p[0] for p in pts]
            pen.moveTo(pts[0])
            for p in pts[1:]:
                pen.lineTo(p)
            pen.closePath()
        glyphs[name] = pen.glyph()
        metrics[name] = ((len(grid[0]) + 1) * PX, min(xs) if xs else 0)

    box = ["#####"] + ["#...#"] * 5 + ["#####"] + ["....."] * DESC_ROWS
    add(".notdef", embolden(box) if is_bold else box)
    for cp in sorted(grids):
        name, grid = grids[cp]
        order.append(name)
        cmap[cp] = name
        add(name, grid)

    ascent, descent = CAP_ROWS * PX, DESC_ROWS * PX
    fb = FontBuilder(UPM, isTTF=True)
    fb.setupGlyphOrder(order)
    fb.setupCharacterMap(cmap)
    fb.setupGlyf(glyphs)
    fb.setupHorizontalMetrics(metrics)
    fb.setupHorizontalHeader(ascent=ascent, descent=-descent, lineGap=0)
    fb.setupNameTable(
        {
            "familyName": FAMILY,
            "styleName": style,
            "uniqueFontIdentifier": f"{FAMILY} {style} {VERSION}",
            "fullName": f"{FAMILY} {style}" if is_bold else FAMILY,
            "psName": f"AhmiPixel-{style}",
            "version": f"Version {VERSION}",
            "copyright": "Copyright 2026 Ahmi Darrow",
            "designer": "Ahmi Darrow",
            "designerURL": "https://github.com/AhmiDarrow",
        }
    )
    fb.setupOS2(
        sTypoAscender=ascent,
        sTypoDescender=-descent,
        sTypoLineGap=0,
        usWinAscent=ascent,
        usWinDescent=descent,
        sxHeight=5 * PX,
        sCapHeight=CAP_ROWS * PX,
        usWeightClass=700 if is_bold else 400,
        fsSelection=0x20 if is_bold else 0x40,
        achVendID="AHMI",
    )
    fb.setupPost(isFixedPitch=0)
    fb.font["head"].macStyle = 1 if is_bold else 0

    OUT.mkdir(exist_ok=True)
    ttf = OUT / f"AhmiPixel-{style}.ttf"
    fb.font.save(ttf)
    fb.font.flavor = "woff2"
    fb.font.save(ttf.with_suffix(".woff2"))
    return ttf


def main() -> int:
    for weight in ("regular", "bold"):
        path = build(weight)
        print(f"built {path.relative_to(ROOT)} and .woff2 ({len(bitmaps(weight))} characters)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
