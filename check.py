#!/usr/bin/env python3
"""
Legibility checks for Ahmi Pixel. Run after editing glyphs/ahmi-pixel.txt:

    python check.py

It reads the same pixel grids the fonts are built from and fails if a
letter could be mistaken for another one, in either weight:

  1. Counters: every letter and digit has the number of closed counters it
     should have. A "C" with one closed counter is an "O"; this catches it.
  2. Openings: C and c keep an opening at least 3 pixels tall on the right.
  3. Look-alikes: pairs such as C/O, 5/S, 0/O, 1/l/I must differ by at least
     3 pixels and a tenth of their ink, or stand at clearly different
     heights (n and h differ by the ascender, and that is enough).
"""
from __future__ import annotations

import sys

from build import CAP_ROWS, bitmaps

# closed counters each character must have (regular, bold)
HOLES = {
    **{c: (0, 0) for c in "CEFGHIJKLMNSTUVWXYZcfhijklmnrstuvwxyz12357"},
    **{c: (1, 1) for c in "ADOPQRabdegopq469"},
    **{c: (2, 2) for c in "B8"},
    "0": (2, 1),  # the slash splits the regular zero's counter in two
}

MIN_OPENING = {"C": 3, "c": 3}

LOOKALIKES = [
    "CO", "CG", "OQ", "OD", "O0", "D0", "5S", "2Z", "8B", "1l", "1I", "lI", "il",
    "6b", "9q", "9g", "gq", "uv", "UV", "ce", "co", "eo", "ao", "nh", "ij", "08",
    "38", "56", "G6", "rn", "S8", "Z7", "71", "hb", "vy", "KX", "PR", "EF", "l|", "I|",
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


def height(grid: list[str]) -> int:
    ys = [y for _, y in cells(grid)]
    return max(ys) - min(ys) + 1


def difference(a: list[str], b: list[str]) -> tuple[int, float]:
    """Fewest differing pixels over small sideways shifts, and that as a share of ink."""
    ca, cb = cells(a), cells(b)
    best = min(len(ca ^ {(x + dx, y) for x, y in cb}) for dx in (-1, 0, 1))
    return best, best / max(len(ca), len(cb))


def main() -> int:
    failures = []
    for weight, col in (("regular", 0), ("bold", 1)):
        grids = {chr(cp): grid for cp, (_, grid) in bitmaps(weight).items()}
        for ch, want in HOLES.items():
            got = holes(grids[ch])
            if got != want[col]:
                failures.append(f"{weight}: '{ch}' has {got} closed counter(s), should have {want[col]}")
        for ch, want in MIN_OPENING.items():
            got = opening(grids[ch])
            if got < want:
                failures.append(f"{weight}: '{ch}' opening is {got}px tall, needs {want}px")
        worst = None
        for a, b in LOOKALIKES:
            px, share = difference(grids[a], grids[b])
            taller = abs(height(grids[a]) - height(grids[b])) >= MIN_HEIGHT_GAP
            if (px < MIN_PIXELS or share < MIN_SHARE) and not taller:
                failures.append(f"{weight}: '{a}' and '{b}' differ by only {px}px ({share:.0%} of ink)")
            if not taller and (worst is None or share < worst[2]):
                worst = (a, b, share, px)
        print(
            f"{weight}: {len(HOLES)} counters, {len(MIN_OPENING)} openings, {len(LOOKALIKES)} look-alike pairs checked; "
            f"closest pair '{worst[0]}'/'{worst[1]}' differs by {worst[3]}px ({worst[2]:.0%})"
        )
    for f in failures:
        print("FAIL", f)
    print("all checks passed" if not failures else f"{len(failures)} problem(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
