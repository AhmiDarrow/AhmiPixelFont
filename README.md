# Ahmi Pixel

An 8-bit style typeface in two weights, drawn for [Ahmi Darrow's site](https://r20ohhka.rf.gd/).
It was made because the pixel font the site used before had a capital C that read as an O and a 5 that read as an S. In Ahmi Pixel every look-alike pair is checked by a script before the fonts are built.

Version 1.000. The public release is [v1.0.0](https://github.com/AhmiDarrow/AhmiPixelFont/releases/tag/v1.0.0).

![Ahmi Pixel specimen](specimen.png)

## What's here

| Path | What it is |
|---|---|
| `fonts/` | Ready-to-use files: `AhmiPixel-Regular` and `AhmiPixel-Bold`, each as `.ttf` and `.woff2` |
| `glyphs/ahmi-pixel.txt` | The source. Every character drawn as a grid of `#` and `.` |
| `build.py` | Turns the glyph file into the font files |
| `check.py` | Fails if any two characters could be mistaken for each other |
| `specimen.html` | Open in a browser to see every character |
| `LICENSE` | SIL Open Font License 1.1 |
| `CHANGELOG.md` | Release history |

## Using it on a web page

```css
@font-face {
  font-family: "Ahmi Pixel";
  src: url("fonts/AhmiPixel-Regular.woff2") format("woff2");
  font-weight: 400;
}
@font-face {
  font-family: "Ahmi Pixel";
  src: url("fonts/AhmiPixel-Bold.woff2") format("woff2");
  font-weight: 700;
}
h1 { font: 700 64px/1.1 "Ahmi Pixel", sans-serif; }
```

One font pixel is 1/8 of the font size, so the letters are only pixel-sharp at sizes that are multiples of 8px: 16, 24, 32, 40, 48, 64 and so on. Other sizes work but look slightly soft.

## The two weights

- **Regular** is exactly the pixels in the glyph file: 1-pixel strokes, capitals 7 pixels tall, lowercase 5.
- **Bold** thickens every pixel one step to the right, giving 2-pixel stems and 1-pixel bars, the look of arcade and console lettering. Where that would close up a counter, the glyph file carries a hand-drawn bold version (currently only the zero).

## Characters

Basic Latin (A–Z, a–z, 0–9 and the standard keyboard punctuation), plus curly quotes, en and em dashes, ellipsis, bullet, middle dot, multiplication sign, left and right arrows, and a diamond (◆). 109 characters in all. No accented letters yet.

## Changing a letter

1. Edit its grid in `glyphs/ahmi-pixel.txt`. The comments at the top of that file explain the layout.
2. Run the checks, then rebuild:

```bash
pip install fonttools brotli
python check.py
python build.py
```

`check.py` enforces three rules in both weights:

- every letter and digit has the right number of closed counters (a C with a closed counter is an O);
- C and c keep an opening at least 3 pixels tall;
- look-alike pairs (C/O, 5/S, 0/O, 1/l/I, 8/B, 2/Z and others) differ by at least 3 pixels and a tenth of their ink, or stand at clearly different heights.

## License

Ahmi Pixel is licensed under the [SIL Open Font License, Version 1.1](LICENSE). You can use it freely in personal and commercial projects, embed it in apps and websites, and modify or redistribute it under the same license. The font itself may not be sold on its own.
