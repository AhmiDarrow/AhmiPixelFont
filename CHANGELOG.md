# Changelog

## 1.100 — unreleased

- 583 characters per weight (was 109): all of Latin-1 and Latin Extended-A, Romanian Ș ș Ț ț and ƒ, spacing accents, modern Greek, Cyrillic for Russian, Ukrainian, Belarusian, Bulgarian, Serbian, Macedonian, Kazakh and Central Asian languages, general punctuation and spaces, currency signs, ™ №, arrows, maths, and the shapes the egui toolkit draws.
- Accented letters are composed by `build.py` from a base letter and an accent drawn once in `glyphs/marks.txt`. Accented capitals are 6 or 5 pixels tall so the accent fits inside the em.
- **Metrics change:** the ascent is now 8 pixels (1024 units, the full em) instead of 7, so accents above capitals stay clear of the line above. With `line-height: normal` lines are one font pixel taller than in 1.000 (10 pixels instead of 9). The 109 original glyphs are unchanged.
- The glyph source is split into several files in `glyphs/`.
- `check.py` now verifies the full character list in both weights, that every non-space glyph has pixels and the spaces have the right widths, that no letter gains or loses a counter in Bold, and compares every pair of letters and digits in all scripts, with an explicit list of intended cross-script look-alikes (Latin A, Greek Α, Cyrillic А ...).
- Specimen updated.

## License update — 2026-11-14

- Ahmi Pixel is now open source under the SIL Open Font License 1.1 (previously all rights reserved). The font files are unchanged.

## 1.0.0 — 2026-11-14

First public release. The font's own version string is 1.000.

- Regular and Bold, each as TrueType (`.ttf`) and WOFF2 (`.woff2`)
- 109 characters: Basic Latin, plus curly quotes, dashes, ellipsis, bullet, middle dot, multiplication sign, arrows, and a diamond
- `check.py` checks closed counters, the C and c openings, and look-alike pairs in both weights
