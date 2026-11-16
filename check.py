#!/usr/bin/env python3
"""
Checks for Ahmi Pixel. Run after editing anything in glyphs/:

    python check.py

It reads the same pixel grids the fonts are built from and fails if a
character is missing or could be mistaken for another one, in either weight:

  1. Coverage: every character in TARGET (below) is drawn, in Regular and
     Bold, and the built font files in fonts/ (if present) map all of them
     and carry the current version.
     Their line metrics keep the 1.000 values (hhea and OS/2 typo ascender
     896, descender -256, line gap 0, USE_TYPO_METRICS set) and
     usWinAscent/usWinDescent cover every glyph's ink.
  2. Ink: every character has pixels except the spaces, which have none and
     the right widths (figure space = a digit, punctuation space = a period).
  3. Counters: the letters and digits in HOLES have the number of closed
     counters they should have, and no letter or digit gains or loses a
     closed counter in Bold. A "C" with one closed counter is an "O".
  4. Openings: C and c keep an opening at least 3 pixels tall on the right.
  5. Look-alikes: every pair of letters and digits (several thousand pairs,
     all scripts) plus the pairs in LOOKALIKES must differ by at least 3
     pixels and a tenth of their ink, or stand at clearly different heights
     (n and h differ by the ascender, and that is enough). Two letters
     carrying the same accents are told apart by their base letters, so
     those bases are compared (as placed, shortened if they were); the
     shared accent pixels would only water the share down. Exempt are only
     the same letter in upper and lower case, and the intended look-alikes
     in HOMOGLYPHS, which are drawn the same on purpose.
"""
from __future__ import annotations

import sys
import unicodedata
from itertools import combinations

from build import OUT, PX, ROWS, DESC_ROWS, VERSION, advance, bitmaps, composition, embolden

# ---------------------------------------------------------------- coverage

# The characters every weight must have (FreeSpeak's font target).
TARGET = (
    set(range(0x0020, 0x007F))                      # Basic Latin
    | set(range(0x00A0, 0x0100))                    # Latin-1 Supplement
    | set(range(0x0100, 0x0180))                    # Latin Extended-A
    | {0x0192, 0x0218, 0x0219, 0x021A, 0x021B}      # ƒ, Romanian Ș ș Ț ț
    | {0x02C6, 0x02C7} | set(range(0x02D8, 0x02DE))  # spacing accents
    | {0x2010, 0x2011, 0x2012, 0x2013, 0x2014, 0x2015, 0x2018, 0x2019, 0x201A,
       0x201C, 0x201D, 0x201E, 0x2020, 0x2021, 0x2022, 0x2026, 0x2030, 0x2032,
       0x2033, 0x2039, 0x203A, 0x203C, 0x2044}      # general punctuation
    | {0x2007, 0x2008, 0x2009, 0x200A, 0x202F}      # spaces
    | {0x20AC, 0x20B9, 0x20BD, 0x20BA, 0x20A9, 0x20AA, 0x20AB, 0x20B1, 0x20B4,
       0x20B8, 0x20BF}                              # currency
    | {0x2122, 0x2116}                              # ™ №
    | set(range(0x2190, 0x2196)) | {0x21E7}         # arrows
    | {0x2212, 0x221E, 0x221A, 0x2248, 0x2260, 0x2264, 0x2265}  # maths
    | {0x25FB, 0x25B2, 0x25BC, 0x25BA, 0x25C4, 0x23F4, 0x23F5, 0x23F6, 0x23F7,
       0x2713, 0x2717, 0x25CF, 0x25CB}              # shapes the UI toolkit draws
    | {0x0386, 0x0388, 0x0389, 0x038A, 0x038C} | set(range(0x038E, 0x03A2))
    | set(range(0x03A3, 0x03CF))                    # monotonic Greek
    | set(range(0x0400, 0x0460))                    # Cyrillic
    | {0x0490, 0x0491, 0x0492, 0x0493, 0x049A, 0x049B, 0x04A2, 0x04A3, 0x04AE,
       0x04AF, 0x04B0, 0x04B1, 0x04BA, 0x04BB, 0x04D8, 0x04D9, 0x04E8, 0x04E9}
)

SPACES = {0x0020, 0x00A0, 0x2007, 0x2008, 0x2009, 0x200A, 0x202F}

# ---------------------------------------------------------------- counters

# closed counters each character must have (regular, bold)
HOLES = {
    **{c: (0, 0) for c in "CEFGHIJKLMNSTUVWXYZcfhijklmnrstuvwxyz12357"},
    **{c: (1, 1) for c in "ADOPQRabdegopq469"},
    **{c: (2, 2) for c in "B8"},
    "0": (2, 1),  # the slash splits the regular zero's counter in two
    "Ø": (2, 2),
}

MIN_OPENING = {"C": 3, "c": 3}

# ---------------------------------------------------------------- look-alikes

# Pairs checked on top of all letter/digit pairs (punctuation and symbols).
LOOKALIKES = [
    "CO", "CG", "OQ", "OD", "O0", "D0", "5S", "2Z", "8B", "1l", "1I", "lI", "il",
    "6b", "9q", "9g", "gq", "uv", "UV", "ce", "co", "eo", "ao", "nh", "ij", "08",
    "38", "56", "G6", "rn", "S8", "Z7", "71", "hb", "vy", "KX", "PR", "EF", "l|", "I|",
    "x×", "x✗", "×✗", "O○", "o○", "0○", "•●", "i¡", "!¡", "<‹", ">›", "'′", '"″',
    ",‚", "|¦", "+÷", "+±", "=≠", "=≈", "<≤", ">≥", "Y¥", "Ұ¥", "T₸", "Ŧ₸",
    "З3", "Э3", "б6", "Ч4", "О○",
]

# Characters drawn the same on purpose. Each group is one shape shared by
# letters of different scripts (Latin A, Greek Alpha, Cyrillic A) or by two
# encodings of one letter; all are pixel-identical except the Romanian
# pairs at the end. No other pair of letters may look alike.
HOMOGLYPHS = [
    # Latin / Greek / Cyrillic capitals that are the same letter shape
    "AΑА", "BΒВ", "EΕЕ", "ZΖ", "HΗН", "IΙІ", "KΚК", "MΜМ", "NΝ", "OΟО",
    "PΡР", "TΤТ", "XΧХ", "YΥҮ", "CС", "SЅ", "JЈ", "ΓГ", "ΠП", "ΦФ",
    "ÈЀ", "ËЁ", "ÏЇΪ", "ŸΫ",
    # lowercase
    "aа", "eе", "oοо", "pр", "cс", "xх", "yу", "sѕ", "iі", "jј", "vν", "hһ",
    "ĸκк", "ħћ", "µμ", "φф", "èѐ", "ëё", "ïї", "óό",
    # one letter, two encodings: Đ (Croatian) and Ð (Icelandic eth)
    "ĐÐ",
    # Θ and Ө are the same barred O in both scripts
    "ΘӨ",
    # Romanian comma-below letters and the older cedilla encodings of the
    # same letters: they differ only by the cedilla/comma, 1 pixel
    "ŞȘ", "şș", "ŢȚ", "ţț",
]

MIN_PIXELS = 3
MIN_SHARE = 0.10
MIN_HEIGHT_GAP = 2


def cells(grid: list[str]) -> set[tuple[int, int]]:
    return {(x, y) for y, row in enumerate(grid) for x, c in enumerate(row) if c == "#"}


def holes(grid: list[str]) -> int:
    """Count background regions that cannot reach the outside."""
    ink = cells(grid)
    w, h = len(grid[0]) + 2, len(grid) + 2
    seen = set()

    def flood(start):
        stack = [start]
        while stack:
            x, y = stack.pop()
            if (x, y) in seen or not (0 <= x < w and 0 <= y < h) or (x - 1, y - 1) in ink:
                continue
            seen.add((x, y))
            stack += [(x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)]

    flood((0, 0))
    count = 0
    for y in range(h):
        for x in range(w):
            if (x, y) not in seen and (x - 1, y - 1) not in ink:
                count += 1
                flood((x, y))
    return count


def opening(grid: list[str]) -> int:
    """Rows, between the top and bottom ink rows, whose right edge is empty."""
    ink = cells(grid)
    right = max(x for x, _ in ink)
    top, bottom = min(y for _, y in ink), max(y for _, y in ink)
    return sum(1 for y in range(top + 1, bottom) if (right, y) not in ink)


def height(ink: set[tuple[int, int]]) -> int:
    ys = [y for _, y in ink]
    return max(ys) - min(ys) + 1


def difference(ca: set, cb: set) -> tuple[int, float]:
    """Fewest differing pixels over small sideways shifts, and that as a share of ink."""
    best = min(len(ca ^ {(x + dx, y) for x, y in cb}) for dx in (-1, 0, 1))
    return best, best / max(len(ca), len(cb))


def is_letter(ch: str) -> bool:
    """Letters and digits that spell words: not the spacing accents (Lm)
    or the superscript digits."""
    return unicodedata.category(ch) in ("Lu", "Ll", "Lt", "Lo", "Nd")


def same_letter(a: str, b: str) -> bool:
    return a.lower() == b.lower() or a.upper() == b.upper()


def intended(a: str, b: str) -> bool:
    return any(a in g and b in g for g in HOMOGLYPHS)


def check_files(failures: list[str]) -> None:
    try:
        from fontTools.ttLib import TTFont
    except ImportError:
        print("fontTools not installed: built files not checked")
        return
    for style in ("Regular", "Bold"):
        for ext in ("ttf", "woff2"):
            path = OUT / f"AhmiPixel-{style}.{ext}"
            if not path.exists():
                failures.append(f"{path.name} is missing: run build.py")
                continue
            font = TTFont(path)
            missing = TARGET - set(font.getBestCmap())
            if missing:
                failures.append(f"{path.name} lacks {len(missing)} characters: run build.py")
            hhea, os2 = font["hhea"], font["OS/2"]
            line = {
                "hhea ascender": (hhea.ascent, 896), "hhea descender": (hhea.descent, -256),
                "hhea lineGap": (hhea.lineGap, 0), "sTypoAscender": (os2.sTypoAscender, 896),
                "sTypoDescender": (os2.sTypoDescender, -256), "sTypoLineGap": (os2.sTypoLineGap, 0),
            }
            for what, (got, want) in line.items():
                if got != want:
                    failures.append(f"{path.name}: {what} is {got}, 1.000 had {want}")
            if os2.version < 4 or not os2.fsSelection & 0x80:
                failures.append(f"{path.name}: USE_TYPO_METRICS is not set")
            gs = font.getGlyphSet()
            from fontTools.pens.boundsPen import BoundsPen
            hi, lo = 0, 0
            for name in font.getGlyphOrder():
                pen = BoundsPen(gs)
                gs[name].draw(pen)
                if pen.bounds:
                    hi, lo = max(hi, pen.bounds[3]), min(lo, pen.bounds[1])
            if os2.usWinAscent < hi or os2.usWinDescent < -lo:
                failures.append(f"{path.name}: usWin {os2.usWinAscent}/{os2.usWinDescent} does not cover glyphs reaching {hi}/{lo}")
            version = font["name"].getDebugName(5)
            if version != f"Version {VERSION}":
                failures.append(f"{path.name} says {version!r}, build.py says {VERSION}: run build.py")


def main() -> int:
    failures: list[str] = []
    for weight, col in (("regular", 0), ("bold", 1)):
        table = bitmaps(weight)
        grids = {chr(cp): grid for cp, (_, grid) in table.items()}
        names = {chr(cp): name for cp, (name, _) in table.items()}
        ink = {ch: cells(g) for ch, g in grids.items()}

        def compared(a: str, b: str) -> tuple[set, set]:
            """The ink to compare: just the bases when both carry the same
            accents in the same place."""
            ca, cb = composition(names[a]), composition(names[b])
            if ca and cb and ca[1] == cb[1]:
                ga, gb = ca[0], cb[0]
                if weight == "bold":
                    ga, gb = embolden(ga), embolden(gb)
                ba, bb = cells(ga), cells(gb)
                if ink[a] - ba == ink[b] - bb:
                    return ba, bb
            return ink[a], ink[b]


        missing = sorted(TARGET - {ord(c) for c in grids})
        for cp in missing:
            failures.append(f"{weight}: U+{cp:04X} {chr(cp)!r} is not drawn")

        for ch in grids:
            cp = ord(ch)
            if cp in SPACES:
                if ink[ch]:
                    failures.append(f"{weight}: space U+{cp:04X} has pixels")
            elif not ink[ch]:
                failures.append(f"{weight}: U+{cp:04X} {ch!r} has no pixels")
        widths = {
            0x00A0: advance(weight, 0x20),
            0x2007: advance(weight, ord("0")),
            0x2008: advance(weight, ord(".")),
            0x2009: 2, 0x200A: 1, 0x202F: 2,
        }
        for cp, want in widths.items():
            if advance(weight, cp) != want:
                failures.append(f"{weight}: space U+{cp:04X} is {advance(weight, cp)}px wide, should be {want}px")

        for ch, want in HOLES.items():
            got = holes(grids[ch])
            if got != want[col]:
                failures.append(f"{weight}: '{ch}' has {got} closed counter(s), should have {want[col]}")
        for ch, want in MIN_OPENING.items():
            got = opening(grids[ch])
            if got < want:
                failures.append(f"{weight}: '{ch}' opening is {got}px tall, needs {want}px")

        pairs = {tuple(p) for p in LOOKALIKES}
        letters = sorted(ch for ch in grids if is_letter(ch))
        pairs |= {(a, b) for a, b in combinations(letters, 2) if not same_letter(a, b)}
        worst = None
        checked = 0
        for a, b in sorted(pairs):
            if a not in ink or b not in ink:
                failures.append(f"look-alike pair {a!r}/{b!r}: character not drawn")
                continue
            if intended(a, b):
                continue
            checked += 1
            taller = abs(height(ink[a]) - height(ink[b])) >= MIN_HEIGHT_GAP
            if taller:
                continue
            px, share = difference(*compared(a, b))
            if px < MIN_PIXELS or share < MIN_SHARE:
                failures.append(f"{weight}: '{a}' and '{b}' differ by only {px}px ({share:.0%} of ink)")
            if worst is None or share < worst[2]:
                worst = (a, b, share, px)
        print(
            f"{weight}: {len(TARGET) - len(missing)}/{len(TARGET)} target characters, "
            f"{len(HOLES)} counters, {len(MIN_OPENING)} openings, {checked} look-alike pairs checked; "
            f"closest pair '{worst[0]}'/'{worst[1]}' differs by {worst[3]}px ({worst[2]:.0%})"
        )

    regular = {cp: g for cp, (_, g) in bitmaps("regular").items()}
    for cp, (_, g) in bitmaps("bold").items():
        if chr(cp) in HOLES or not is_letter(chr(cp)):
            continue
        r, b = holes(regular[cp]), holes(g)
        if r != b:
            failures.append(f"bold: U+{cp:04X} {chr(cp)!r} has {b} closed counter(s), regular has {r}")

    check_files(failures)
    for f in failures:
        print("FAIL", f)
    print("all checks passed" if not failures else f"{len(failures)} problem(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
