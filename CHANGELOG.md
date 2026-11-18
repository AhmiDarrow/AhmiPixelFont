# Changelog

## 1.200 — 2026-11-18 (release v1.2.0)

Five weights, the same set as Remedy Sans UI. The font's own version string is 1.200.

- New Light (300), Semilight (350) and Semibold (600). They draw Regular's pixels with every horizontal run of ink ending at a fraction of a pixel, so stems are 0.6, 0.8 and 1.5 pixels wide and bars stay one pixel tall. Sharp from 16px up; at 8px the pixel hinting rounds them to whole pixels. Semibold glyphs are half a pixel wider so letters keep a one-pixel gap. Each comes as `.ttf`, `.woff2` and `.otf`
- Regular and Bold stay one style-linked family. The new weights carry their own legacy family name ("Ahmi Pixel Light" and so on) and the typographic family Ahmi Pixel (name IDs 16 and 17)
- `check.py` now also checks every weight's built files: weight class, names, glyph set, and the `.otf`
- The fonts now allow installable embedding (OS/2 `fsType` 0). Earlier builds carried fontTools' default of 4, "preview and print only", which is wrong for an OFL font that apps bundle and embed. `check.py` now checks `fsType`.

## 1.100 — 2026-11-16 (release v1.1.0)

- 583 characters per weight (was 109): all of Latin-1 and Latin Extended-A, Romanian Ș ș Ț ț and ƒ, spacing accents, modern Greek, Cyrillic for Russian, Ukrainian, Belarusian, Bulgarian, Serbian, Macedonian, Kazakh and Central Asian languages, general punctuation and spaces, currency signs, ™ №, arrows, maths, and the shapes the egui toolkit draws.
- Accented letters are composed by `build.py` from a base letter and an accent drawn once in `glyphs/marks.txt`. Accented capitals are 6 or 5 pixels tall so the accent fits inside the em.
- Line spacing is unchanged from 1.000: hhea and OS/2 typo ascender 896, descender -256, line gap 0, now with USE_TYPO_METRICS set. Only usWinAscent/usWinDescent grow, to 1024/256, so accents in the 8th row are never clipped on Windows; in tightly set lines they may reach into the line above. The 109 original glyphs are unchanged.
- `check.py` checks that the line metrics keep the 1.000 values and that usWinAscent/usWinDescent cover every glyph.
- The glyph source is split into several files in `glyphs/`.
- `check.py` now verifies the full character list in both weights, that every non-space glyph has pixels and the spaces have the right widths, that no letter gains or loses a counter in Bold, and compares every pair of letters and digits in all scripts, with an explicit list of intended cross-script look-alikes (Latin A, Greek Α, Cyrillic А ...).
- Specimen updated.
- Hinted: every glyph carries a TrueType program that rounds each outline point to the pixel grid on both axes, and the gasp table allows grid-fitting, so the pixels stay sharp at sizes that are not multiples of 8px.
- New `.otf` files for both weights: the same outlines as CFF, with PostScript hints from otfautohint. `build.py` needs `afdko` for them.

## License update — 2026-11-14

- Ahmi Pixel is now open source under the SIL Open Font License 1.1 (previously all rights reserved). The font files are unchanged.

## 1.0.0 — 2026-11-14

First public release. The font's own version string is 1.000.

- Regular and Bold, each as TrueType (`.ttf`) and WOFF2 (`.woff2`)
- 109 characters: Basic Latin, plus curly quotes, dashes, ellipsis, bullet, middle dot, multiplication sign, arrows, and a diamond
- `check.py` checks closed counters, the C and c openings, and look-alike pairs in both weights
