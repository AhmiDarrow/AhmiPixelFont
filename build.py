#!/usr/bin/env python3
"""
Build the Ahmi Pixel fonts from the glyph files in glyphs/.

    python build.py            # writes fonts/AhmiPixel-{Regular,Bold}.{ttf,woff2}

Needs: pip install fonttools brotli

The glyph files are the only source. Regular is exactly the drawn pixels.
Bold thickens every pixel one step to the right (2px stems, 1px bars) unless
a glyph file gives a hand-drawn "@bold" version.

Accented letters are not drawn out: a line such as

    @ U+00E9 eacute = e + m.acute

builds the glyph from the base letter and a mark that is drawn once (see
"Composed glyphs" at the top of glyphs/ahmi-pixel.txt for the rules).

Metrics: one font pixel is 1/8 of the em, so text is pixel-sharp at any size
that is a multiple of 8px (16, 24, 32, 40, 48, 64 ...). Capitals are 7 pixels
tall; the 8th row of the em, above the capitals, holds accents. Line spacing
(hhea, OS/2 typo, USE_TYPO_METRICS) is kept as in 1.000: 7 pixels up, 2 down;
only usWinAscent/usWinDescent grow to cover every glyph.
"""
from __future__ import annotations

import math
import sys
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parent
GLYPHS = ROOT / "glyphs"
OUT = ROOT / "fonts"

FAMILY = "Ahmi Pixel"
VERSION = "1.100"
UPM = 1024
PX = 128          # one drawn pixel, in font units (8 pixels per em)
TOP_ROWS = 1      # the row above the capitals, inside the em, for accents
CAP_ROWS = 7      # rows from the cap line down to the baseline
DESC_ROWS = 2     # rows below the baseline
ROWS = TOP_ROWS + CAP_ROWS + DESC_ROWS
CAP = TOP_ROWS                    # grid row of the cap line
XTOP = CAP + 2                    # grid row of the x-height (top of 'x')
BASELINE = CAP + CAP_ROWS - 1     # last grid row that stands on the baseline

MARK_KINDS = ("above", "below", "ogonek", "side", "tonos")

Bitmap = list[str]


@dataclass
class Entry:
    name: str
    cp: int | None                 # None for a part (marks, short capitals)
    where: str
    rows: Bitmap = field(default_factory=list)
    lift: int = 0                  # rows drawn above the cap line (^1)
    recipe: list[tuple[str, int | None]] | None = None
    advance: str | None = None     # explicit advance: pixels, or a glyph name to copy (spaces)
    kind: str | None = None        # mark kind, for parts that are marks

    def grid(self) -> Bitmap:
        if not self.rows:
            raise ValueError(f"{self.where}: {self.name} has no rows")
        width = max(len(r) for r in self.rows)
        top = CAP - self.lift
        if top < 0 or top + len(self.rows) > ROWS:
            raise ValueError(f"{self.where}: {self.name} has too many rows")
        out = ["." * width] * top + [r.ljust(width, ".") for r in self.rows]
        return out + ["." * width] * (ROWS - len(out))


def source_files() -> list[Path]:
    files = sorted(GLYPHS.glob("*.txt"))
    main = GLYPHS / "ahmi-pixel.txt"
    return [main] + [f for f in files if f != main]


@lru_cache(maxsize=None)
def parse() -> tuple[dict[int, Entry], dict[int, Entry], dict[str, list[Entry]], dict[str, Entry]]:
    """Return (glyphs by codepoint, bold overrides, parts by name, everything by name)."""
    glyphs: dict[int, Entry] = {}
    bold: dict[int, Entry] = {}
    parts: dict[str, list[Entry]] = {}
    names: dict[str, Entry] = {}
    for path in source_files():
        current: Entry | None = None
        target = None
        for n, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            where = f"{path.name}:{n}"
            line = raw.rstrip()
            if line.startswith("@"):
                head, _, recipe = line.partition(" = ")
                tokens = head.split()
                tag = tokens[0]
                if tag in ("@", "@bold"):
                    if len(tokens) < 3 or not tokens[1].startswith("U+"):
                        raise ValueError(f"{where}: expected '@ U+XXXX name', got {line!r}")
                    cp, name, opts = int(tokens[1][2:], 16), tokens[2], tokens[3:]
                elif tag == "@part":
                    if len(tokens) < 2:
                        raise ValueError(f"{where}: expected '@part name', got {line!r}")
                    cp, name, opts = None, tokens[1], tokens[2:]
                else:
                    raise ValueError(f"{where}: unknown header {tag!r}")
                entry = Entry(name, cp, where)
                for opt in opts:
                    if opt.startswith("^"):
                        entry.lift = int(opt[1:])
                    elif opt.startswith("advance="):
                        entry.advance = opt.split("=", 1)[1]
                    elif opt in MARK_KINDS:
                        entry.kind = opt
                    else:
                        raise ValueError(f"{where}: unknown option {opt!r}")
                if recipe.strip():
                    comps = []
                    for comp in recipe.split("+"):
                        comp = comp.strip()
                        cname, _, x = comp.partition("@")
                        comps.append((cname, int(x) if x else None))
                    entry.recipe = comps
                if tag == "@bold":
                    bold[cp] = entry
                elif tag == "@part":
                    parts.setdefault(name, []).append(entry)
                    names.setdefault(name, entry)
                else:
                    if cp in glyphs:
                        raise ValueError(f"{where}: U+{cp:04X} defined twice")
                    if name in names:
                        raise ValueError(f"{where}: name {name!r} used twice")
                    glyphs[cp] = entry
                    names[name] = entry
                current = entry
            elif not line or line.startswith("# ") or (line == "#" and current is None):
                continue  # blank line or comment (a lone '#' inside a glyph is a pixel)
            else:
                if set(line) - {"#", "."}:
                    raise ValueError(f"{where}: only '#' and '.' allowed in a glyph row: {line!r}")
                if current is None:
                    raise ValueError(f"{where}: glyph row before any '@' header")
                if current.recipe is not None:
                    raise ValueError(f"{where}: {current.name} is composed and cannot also have rows")
                current.rows.append(line)
    return glyphs, bold, parts, names


# ---------------------------------------------------------------- composing

def ink(grid: Bitmap) -> set[tuple[int, int]]:
    return {(x, y) for y, row in enumerate(grid) for x, c in enumerate(row) if c == "#"}


def paste(grid: Bitmap, mark: Bitmap, x: int, y: int) -> Bitmap:
    """Overlay mark's ink with its box at (x, y). The grid widens on either
    side only where ink lands outside it; the mark's empty columns do not count."""
    cells = [(x + dx, y + dy) for dy, row in enumerate(mark) for dx, c in enumerate(row) if c == "#"]
    left = min(0, min(cx for cx, _ in cells))
    right = max(len(grid[0]), max(cx for cx, _ in cells) + 1)
    out = [list("." * -left + r + "." * (right - len(r))) for r in grid]
    for cx, cy in cells:
        out[cy][cx - left] = "#"
    return ["".join(r) for r in out]


def trim_rows(rows: Bitmap) -> Bitmap:
    """A mark is its drawn rows, padded to one width. Empty rows under the
    ink are kept: they hold the mark higher (the macron)."""
    width = max(len(s) for s in rows)
    return [r.ljust(width, ".") for r in rows]


def drop_blank_bottom(rows: Bitmap) -> Bitmap:
    while rows and "#" not in rows[-1]:
        rows = rows[:-1]
    return rows


def shorten(name: str, grid: Bitmap, top: int) -> Bitmap:
    """The base letter redrawn so its ink starts at row `top`, same baseline.

    A hand-drawn part "<name>.<height>" wins. Otherwise rows are dropped
    where a row repeats the one below it (the straight runs of stems and
    sides), from the longest run first, upper run on a tie.
    """
    cells = ink(grid)
    t, b = min(y for _, y in cells), max(y for _, y in cells)
    height = b - top + 1
    _, _, parts, _ = parse()
    drawn = parts.get(f"{name}.{height}")
    if drawn:
        g = resolve(drawn[0].name)
        gt, gb = min(y for _, y in ink(g)), max(y for _, y in ink(g))
        if gb - gt + 1 != height:
            raise ValueError(f"{drawn[0].where}: {drawn[0].name} must be {height} rows tall")
        shift = b - gb
        return (["." * len(g[0])] * shift + g)[:ROWS] if shift >= 0 else g[-shift:] + ["." * len(g[0])] * -shift
    rows = list(grid)
    for _ in range(top - t):
        ys = [y for _, y in ink(rows)]
        lo, hi = min(ys), max(ys)
        runs = []
        y = lo
        while y <= hi:
            end = y
            while end + 1 <= hi and rows[end + 1] == rows[y]:
                end += 1
            if end > y:
                runs.append((-(end - y + 1), y))
            y = end + 1
        if not runs:
            raise ValueError(f"{name}: cannot shorten to {height} rows automatically; draw '@part {name}.{height}'")
        _, y = min(runs)
        rows = ["." * len(rows[0])] + rows[:y] + rows[y + 1:]
    return rows


def pick_mark(name: str, base: Bitmap | None, cap: bool) -> tuple[Entry, Bitmap]:
    """Choose the mark variant: '<mark>.cap' over capitals, then a drawing
    whose box width has the base's parity so it centres exactly (the widest
    that fits over the base, else the narrowest)."""
    _, _, parts, _ = parse()
    variants = (cap and parts.get(f"{name}.cap")) or parts.get(name)
    if not variants:
        raise ValueError(f"unknown mark {name!r}")
    if base is not None:
        xs = [x for x, _ in ink(base)]
        width = max(xs) - min(xs) + 1
        same = [v for v in variants if len(trim_rows(v.rows)[0]) % 2 == width % 2]
        if same:
            sizes = sorted(same, key=lambda v: len(trim_rows(v.rows)[0]))
            fits = [v for v in sizes if len(trim_rows(v.rows)[0]) <= width]
            v = fits[-1] if fits else sizes[0]
            return v, trim_rows(v.rows)
    return variants[0], trim_rows(variants[0].rows)


def compose(entry: Entry) -> Bitmap:
    comps = entry.recipe
    _, _, parts, names = parse()
    first, first_x = comps[0]
    if first in parts and parts[first][0].kind:
        # a spacing accent: the mark alone, standing at the cap line like ` and ^
        mark, rows = pick_mark(first, None, False)
        rows = drop_blank_bottom(rows)
        cols = [x for x in range(len(rows[0])) if any(r[x] == "#" for r in rows)]
        rows = [r[cols[0]: cols[-1] + 1] for r in rows]
        y = CAP if mark.kind == "above" else BASELINE + 1
        return paste(["." * len(rows[0])] * ROWS, rows, 0, y)
    grid = resolve(first)
    base = None
    for mname, mx in comps[1:]:
        cells = ink(grid)
        top = min(y for _, y in cells)
        mark, rows = pick_mark(mname, grid, top <= CAP)
        h, mw = len(rows), len(rows[0])
        if mark.kind == "above":
            if top - 1 - h < 0:
                grid = shorten(first, grid, h + 1)
                cells = ink(grid)
                top = min(y for _, y in cells)
            xs = [x for x, _ in cells]
            centre = (min(xs) + max(xs)) / 2
            x = mx if mx is not None else math.floor(centre - (mw - 1) / 2 + 0.5)
            y = top - 1 - h
        elif mark.kind in ("below", "ogonek"):
            bottom = max(y for _, y in cells)
            xs = [x for x, y in cells if y == bottom]
            y = bottom + 1
            if y + h > ROWS:
                raise ValueError(f"{entry.where}: {mname} does not fit under {first}")
            # the mark's top row hangs from the base: under the middle of the
            # base's bottom row (cedilla, comma) or under its right end (ogonek)
            attach = rows[0].index("#")
            if mx is not None:
                x = mx
            elif mark.kind == "ogonek":
                x = max(xs) - attach
            else:
                x = math.floor((min(xs) + max(xs)) / 2 + 0.5) - attach
        elif mark.kind == "side":
            y = CAP
            right = max(x for x, yy in cells if CAP <= yy < CAP + h + 1)
            x = mx if mx is not None else right + 2
        elif mark.kind == "tonos":
            grid = ["." * (mw + 1) + r for r in grid]
            x, y = 0, CAP
        else:
            raise ValueError(f"{mname} is not a mark")
        if mark.kind in ("above", "side", "tonos"):
            placed = {(x + dx, y + dy) for dy, r in enumerate(rows) for dx, c in enumerate(r) if c == "#"}
            near = {(px + ox, py + oy) for px, py in placed
                    for ox, oy in ((0, 0), (1, 0), (-1, 0), (0, 1), (0, -1))}
            if near & ink(grid):
                raise ValueError(f"{entry.where}: {mname} touches {first} in {entry.name}")
        if base is None:
            base = grid
        before = len(grid[0])
        grid = paste(grid, rows, x, y)
        # keep the base aligned with the grid as it widens
        left = -min(0, x + min(i for r in rows for i, c in enumerate(r) if c == "#"))
        base = ["." * left + r for r in base]
        base = [r + "." * (len(grid[0]) - len(r)) for r in base]
    if base is not None:
        BASES[entry.name] = (tuple(base), tuple(m for m, _ in comps[1:]))
    return grid


# name -> (base grid as placed in the final glyph, mark names) for every
# composed glyph with marks
BASES: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {}


def composition(name: str) -> tuple[Bitmap, tuple[str, ...]] | None:
    """The base letter (shortened as placed, before any mark) and the marks
    of a composed glyph, or None for a drawn one."""
    resolve(name)
    found = BASES.get(name)
    return (list(found[0]), found[1]) if found else None


@lru_cache(maxsize=None)
def _resolve(name: str) -> tuple[str, ...]:
    _, _, parts, names = parse()
    entry = names.get(name)
    if entry is None:
        raise ValueError(f"unknown glyph or part {name!r}")
    if entry.kind:
        raise ValueError(f"{name!r} is a mark and cannot be a base")
    grid = compose(entry) if entry.recipe else entry.grid()
    return tuple(grid)


def resolve(name: str) -> Bitmap:
    return list(_resolve(name))


# ---------------------------------------------------------------- weights

def embolden(grid: Bitmap) -> Bitmap:
    """Thicken one pixel to the right: the classic 8-bit bold."""
    out = []
    for row in grid:
        cells = [c == "#" for c in row] + [False]
        out.append("".join("#" if cells[x] or (x > 0 and cells[x - 1]) else "." for x in range(len(cells))))
    return out


@lru_cache(maxsize=None)
def _bitmaps(weight: str) -> dict[int, tuple[str, tuple[str, ...], str | None]]:
    glyphs, bold, _, _ = parse()
    out = {}
    for cp, entry in glyphs.items():
        grid = resolve(entry.name)
        if weight == "bold":
            if cp in bold:
                grid = bold[cp].grid()
            elif any("#" in r for r in grid):
                grid = embolden(grid)
            # spaces keep their width
        out[cp] = (entry.name, tuple(grid), entry.advance)
    return out


def bitmaps(weight: str) -> dict[int, tuple[str, Bitmap]]:
    """Final pixel grids for 'regular' or 'bold' (ROWS rows; row CAP is the cap line)."""
    return {cp: (name, list(grid)) for cp, (name, grid, _) in _bitmaps(weight).items()}


def advance(weight: str, cp: int) -> int:
    """Advance width in pixels: the drawn width plus one empty column, or the
    glyph's explicit advance= (used by the spaces): a number of pixels, or
    the name of another glyph whose advance it copies in this weight."""
    _, grid, adv = _bitmaps(weight)[cp]
    if adv is None:
        return len(grid[0]) + 1
    if adv.isdigit():
        return int(adv)
    glyphs, _, _, _ = parse()
    other = [c for c, e in glyphs.items() if e.name == adv]
    if not other:
        raise ValueError(f"advance={adv}: no glyph named {adv!r}")
    return advance(weight, other[0])


# ---------------------------------------------------------------- outlines

def outline(grid: Bitmap) -> list[list[tuple[int, int]]]:
    """Trace the pixel grid into closed contours (pixel units, y up).

    Outer contours come out clockwise and counters counter-clockwise, which is
    what TrueType expects. Pixels that only touch at a corner stay separate.
    """
    cells = {
        (x, ROWS - DESC_ROWS - 1 - r)
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


LINE_ASCENT = CAP_ROWS * PX      # 896, as in 1.000
LINE_DESCENT = DESC_ROWS * PX    # 256, as in 1.000
LINE_GAP = 0
USE_TYPO_METRICS = 0x80


def win_bounds(weight: str) -> tuple[int, int]:
    """usWinAscent/usWinDescent: the highest and lowest ink of any glyph."""
    top, bottom = 0, 0
    for _, grid in bitmaps(weight).values():
        for r, row in enumerate(grid):
            if "#" in row:
                y = ROWS - DESC_ROWS - 1 - r      # pixel row, 0 = just above baseline
                top, bottom = max(top, (y + 1) * PX), max(bottom, -y * PX)
    return top, bottom


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

    def add(name: str, grid: Bitmap, adv: int) -> None:
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
        metrics[name] = (adv * PX, min(xs) if xs else 0)

    box = ["....."] * CAP + ["#####"] + ["#...#"] * 5 + ["#####"] + ["....."] * DESC_ROWS
    box = embolden(box) if is_bold else box
    add(".notdef", box, len(box[0]) + 1)
    for cp in sorted(grids):
        name, grid = grids[cp]
        order.append(name)
        cmap[cp] = name
        add(name, grid, advance(weight, cp))

    # Line spacing stays as in 1.000 (hhea and typo: 7 rows up, 2 down, no
    # gap; USE_TYPO_METRICS on). Only the Windows clipping box grows to the
    # real bounds of every glyph, so accents in the 8th row are never cut
    # off; in tightly set lines they may reach into the line above.
    ascent, descent = LINE_ASCENT, LINE_DESCENT
    win_ascent, win_descent = win_bounds(weight)
    fb = FontBuilder(UPM, isTTF=True)
    fb.setupGlyphOrder(order)
    fb.setupCharacterMap(cmap)
    fb.setupGlyf(glyphs)
    fb.setupHorizontalMetrics(metrics)
    fb.setupHorizontalHeader(ascent=ascent, descent=-descent, lineGap=LINE_GAP)
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
        version=4,
        sTypoAscender=ascent,
        sTypoDescender=-descent,
        sTypoLineGap=LINE_GAP,
        usWinAscent=win_ascent,
        usWinDescent=win_descent,
        sxHeight=5 * PX,
        sCapHeight=CAP_ROWS * PX,
        usWeightClass=700 if is_bold else 400,
        fsSelection=(0x20 if is_bold else 0x40) | USE_TYPO_METRICS,
        achVendID="AHMI",
    )
    fb.setupPost(isFixedPitch=0)
    fb.font["head"].macStyle = 1 if is_bold else 0
    fb.font["head"].fontRevision = float(VERSION)

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
