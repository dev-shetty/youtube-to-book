# youtube-to-book

Turn a YouTube video or playlist into a real book — a typeset LaTeX PDF with chapters, syntax-highlighted code, callout boxes, and hand-authored TikZ diagrams.

It is a [Claude Code](https://claude.com/claude-code) skill. You install it once, paste a URL, and Claude does the rest: pulls the transcript, grabs the frames worth keeping, outlines the book, writes each chapter in parallel, reviews the prose, **looks at every rendered diagram to check it's actually correct**, and compiles the PDF.

```
you:    turn this into a textbook: https://www.youtube.com/watch?v=...
claude: ✓ ./textbooks/database-internals/main.pdf — 9 chapters, ~113 pages
```

## Install

```bash
npx youtube-to-book install
```

That copies the skill into `~/.claude/skills/youtube-to-book/` and checks your dependencies. Restart Claude Code and it's live.

Project-local instead of global:

```bash
npx youtube-to-book install --project   # → ./.claude/skills/youtube-to-book/
```

Other commands:

| Command | What it does |
|---|---|
| `npx youtube-to-book install` | Install the skill (`--force` to overwrite, `--dir <path>` for a custom location) |
| `npx youtube-to-book doctor` | Check that the external tools are present |
| `npx youtube-to-book where` | Print the install path |
| `npx youtube-to-book uninstall` | Remove it |

### Dependencies

The skill shells out to these. `doctor` tells you which are missing.

```bash
brew install yt-dlp ffmpeg tectonic poppler
```

| Tool | Used for |
|---|---|
| `yt-dlp` | transcripts, metadata, media URLs |
| `ffmpeg` | key-frame extraction |
| `tectonic` | LaTeX compilation (auto-fetches packages, no TeX Live install) |
| `python3` | the figure-render script |
| `pdftoppm` (poppler), or macOS `sips`, or ImageMagick | rasterising figures for review |

## Usage

Just talk to Claude Code:

- *"make a book from this video: `<url>`"*
- *"turn this playlist into a textbook"* — each video becomes a chapter
- *"convert this to a book, but go deeper on the storage-engine parts"*

Output lands in `./textbooks/<book-slug>/` relative to your working directory. Set `TEXTBOOKS_DIR` to change the default, or just name a directory in your request.

```
textbooks/<book-slug>/
├── main.tex          preamble, title page, TOC
├── chapters/         ch01.tex, ch02.tex, ...
├── frames/           key frames that survived review
├── figrender/        every TikZ figure as a PNG, for the visual review pass
├── transcript.txt
├── outline.md
└── main.pdf          ← the book
```

## How it works

1. **Extract** — transcript via `yt-dlp`, cleaned of VTT timestamps and dedup noise. Frames are pulled *targeted*, not swept: chapter markers or transcript cues pick 10–20 moments, and `ffmpeg -ss` before `-i` seeks by HTTP range so each frame costs seconds instead of streaming the whole video.
2. **Outline** — chapters, key concepts, which figures belong where.
3. **Write** — one subagent per chapter, in parallel, each given only its own transcript slice and an explicit list of TikZ figures to author.
4. **Review** — two independent passes, both load-bearing:
   - a **prose** pass for cross-chapter repetition, factual drift, and tone breaks;
   - a **visual** pass that renders every `tikzpicture` to PNG and *looks at it*.
5. **Compile** — self-correcting `tectonic` loop until the PDF builds.

### Why the visual review exists

A geometrically wrong diagram compiles with zero warnings and reads fine in source.

Real case: the four SQL JOIN types were drawn as Venn diagrams with radius `0.95` and centres `2.0` apart — the circles missed each other by `0.1` and never intersected. INNER JOIN, whose entire meaning *is* the intersection, rendered as two blank circles. It passed the compiler, passed the prose review, and shipped into a 113-page PDF before a human noticed.

Reading the `.tex` cannot catch that. Only looking at the picture can. So the skill renders every figure to its own PNG (`skill/scripts/render-figures.py`) and hands them to an agent that reads them as images and checks the geometry against the caption.

### Style

Chapters are written for an engineer with a few years' experience — conversational, concrete, short paragraphs, code in small annotated chunks, no beginner hand-holding and no repetition. The LaTeX template ships O'Reilly-ish callout boxes (`insight`, `practical`, `warning`, `aside`) and `listings` syntax highlighting.

## Customising

The whole skill is one Markdown file. After installing, edit `~/.claude/skills/youtube-to-book/SKILL.md` — change the writing style, swap the callout colours, adjust the LaTeX preamble. Claude reads it fresh on every run.

## Contributing

Issues and PRs welcome. To work on it locally:

```bash
git clone https://github.com/dev-shetty/youtube-to-book
cd youtube-to-book
node bin/cli.js install --force    # install your working copy
```

## License

MIT © Deveesh Shetty
