#!/usr/bin/env python3
"""Render every TikZ figure in a book to its own PNG, so an agent can look at them.

A figure that is geometrically wrong still compiles perfectly. Reading the .tex
source does not catch it -- you have to see the picture. This extracts each
tikzpicture into a standalone document, compiles it, and converts it to PNG.

Usage:
    python3 render-figures.py <book-dir> [out-dir]

Defaults out-dir to <book-dir>/figrender. Writes <label>.png per figure plus
an index.txt mapping each PNG back to its chapter, caption, and source lines.
"""

import re
import shutil
import subprocess
import sys
from pathlib import Path

# Preamble lines that break or are pointless inside `standalone`.
DROP = re.compile(
    r"\\(usepackage(\[[^\]]*\])?\{(geometry|fancyhdr|hyperref)\}"
    r"|hypersetup|pagestyle|fancyhf|fancyhead|fancyfoot|renewcommand\{\\headrulewidth\}"
    r"|setlength\{\\(parskip|parindent|emergencystretch)\}"
    r"|hyphenpenalty|tolerance)"
)


def extract_preamble(main_tex: Path) -> str:
    src = main_tex.read_text(encoding="utf-8")
    body = src[: src.index(r"\begin{document}")]
    body = body[body.index("\n", body.index(r"\documentclass")) :]
    return "\n".join(l for l in body.splitlines() if not DROP.search(l))


def find_figures(chapter: Path):
    """Yield (label, caption, tikz_source, line_no) for each tikzpicture."""
    src = chapter.read_text(encoding="utf-8")
    for m in re.finditer(
        r"\\begin\{tikzpicture\}.*?\\end\{tikzpicture\}", src, re.S
    ):
        tikz = m.group(0)
        line = src[: m.start()].count("\n") + 1
        # Look ahead for the enclosing figure's caption/label.
        tail = src[m.end() : m.end() + 1500]
        cap = re.search(r"\\caption\{(.{0,120})", tail, re.S)
        lab = re.search(r"\\label\{([^}]+)\}", tail)
        label = lab.group(1) if lab else f"{chapter.stem}-line{line}"
        # The 120-char window overshoots into \label/\end{figure}; trim it back.
        caption = "(no caption)"
        if cap:
            text = re.split(r"\\label|\\end\{figure\}", cap.group(1))[0]
            caption = " ".join(text.rstrip().rstrip("}").split())
        yield label.replace(":", "-").replace("/", "-"), caption, tikz, line


def pdf_to_png(pdf: Path, png: Path) -> bool:
    """Rasterise a one-page PDF at ~1600px on the long edge.

    `sips` ships with macOS; `pdftoppm` (poppler) and ImageMagick cover Linux.
    """
    if shutil.which("pdftoppm"):
        # -r 200 lands a standalone figure in the right ballpark; -singlefile
        # drops the usual "-1" page suffix so the output path is exact.
        cmd = ["pdftoppm", "-png", "-r", "200", "-singlefile",
               str(pdf), str(png.with_suffix(""))]
    elif shutil.which("sips"):
        cmd = ["sips", "-s", "format", "png", str(pdf),
               "--out", str(png), "-Z", "1600"]
    elif shutil.which("magick"):
        cmd = ["magick", "-density", "200", str(pdf), str(png)]
    else:
        return False
    subprocess.run(cmd, capture_output=True)
    return png.exists()


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__.strip(), file=sys.stderr)
        return 2
    book = Path(sys.argv[1]).resolve()
    if not (book / "main.tex").exists():
        print(f"no main.tex in {book}", file=sys.stderr)
        return 2
    out = Path(sys.argv[2]).resolve() if len(sys.argv) > 2 else book / "figrender"
    out.mkdir(parents=True, exist_ok=True)

    preamble = extract_preamble(book / "main.tex")
    index, failures = [], []

    for chapter in sorted((book / "chapters").glob("*.tex")):
        for label, caption, tikz, line in find_figures(chapter):
            stem = f"{chapter.stem}-{label}"
            tex = out / f"{stem}.tex"
            tex.write_text(
                "\\documentclass[border=6pt,varwidth=\\maxdimen]{standalone}\n"
                + preamble
                + "\n\\begin{document}\n"
                + tikz
                + "\n\\end{document}\n",
                encoding="utf-8",
            )
            r = subprocess.run(
                ["tectonic", "-X", "compile", "--outdir", str(out), str(tex)],
                capture_output=True,
                text=True,
            )
            pdf = out / f"{stem}.pdf"
            if r.returncode or not pdf.exists():
                failures.append(f"{stem}: {r.stderr.strip().splitlines()[-1:]}")
                continue
            if not pdf_to_png(pdf, out / f"{stem}.png"):
                failures.append(f"{stem}: no PDF->PNG converter "
                                "(install poppler, or use macOS sips)")
                continue
            index.append(f"{stem}.png\t{chapter.name}:{line}\t{caption}")

    for f in out.glob("*.tex"):
        f.unlink()
    for f in out.glob("*.pdf"):
        f.unlink()

    (out / "index.txt").write_text("\n".join(index) + "\n", encoding="utf-8")
    print(f"rendered {len(index)} figures to {out}")
    for f in failures:
        print("FAILED:", f)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
