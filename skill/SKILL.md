---
name: youtube-to-book
description: Use when the user provides a YouTube video or playlist URL and wants it converted into a LaTeX book. Triggers on "make a book from this video", "convert this to a book", "turn this into a textbook", or any request involving YouTube URLs and book/textbook creation.
---

# YouTube to Book

Convert YouTube videos or playlists into well-written, engaging LaTeX books with diagrams extracted from the video. Output is a compiled PDF in `./textbooks/<book-slug>/`, relative to the current working directory.

If the user has set `$TEXTBOOKS_DIR`, write there instead. If they name an output directory in the request, that always wins.

## Prerequisites

Check these before starting, and tell the user exactly what's missing rather than failing halfway:

| Tool | Purpose | Install |
|------|---------|---------|
| `yt-dlp` | transcripts, metadata, media URLs | `brew install yt-dlp` / `pipx install yt-dlp` |
| `ffmpeg` | frame extraction | `brew install ffmpeg` |
| `tectonic` | LaTeX compilation | `brew install tectonic` |
| `python3` | figure-render script | preinstalled on macOS/Linux |
| `pdftoppm` or `sips` | PDF→PNG for figure review | `brew install poppler` (`sips` ships with macOS) |

## Writing Style

Channel Andy Weir, Randall Munroe, and Daniel Kahneman:
- **Simple but not dumbed down** — write for an engineer with 3-4 years of experience
- **Engaging and conversational** — use humor naturally, not forced. Occasional wit, not comedy
- **Practical examples** — ground every concept in something tangible and real-world
- **Technical accuracy** — don't sacrifice correctness for simplicity
- **Short paragraphs** — no walls of text. Break ideas into digestible pieces
- **Code in small chunks** — never dump large code blocks. Show code in bite-sized, syntax-highlighted pieces with explanation woven between them
- **Callout boxes** — use `tcolorbox` for asides, "why this matters" notes, and practical tips
- **No filler** — skip beginner-level explanations unless the user explicitly asks for them
- **No repetition** — state a concept once to introduce, once to reinforce (e.g., in a callout or summary), then move on. Never repeat the same point 4-5 times. Trust the reader.
- **Fun facts welcome** — historical tidbits, naming origins, surprising connections land well (e.g., "what the B in BTree stands for")

## Workflow

### 1. Setup & Extract (Parallel)

Create the book directory: `./textbooks/<book-slug>/`

Run these in parallel using subagents:

**Agent A — Transcript extraction:**
```bash
# Single video
yt-dlp --write-auto-sub --sub-lang en --skip-download --sub-format vtt -o "<book-dir>/%(title)s.%(ext)s" "<url>"

# Playlist — get all videos
yt-dlp --write-auto-sub --sub-lang en --skip-download --sub-format vtt -o "<book-dir>/transcripts/%(playlist_index)s-%(title)s.%(ext)s" "<playlist-url>"
```

Then clean the VTT transcript: strip timestamps, deduplicate lines, merge into clean text. Save as `transcript.txt` (or `transcripts/01-title.txt`, etc. for playlists).

Also extract video metadata:
```bash
yt-dlp --print title --print duration_string --print description "<url>"
```

**Agent B — Key frame extraction:**

**Prefer targeted extraction over a full scene-detect sweep.** A scene-detect pass streams the *entire* video through ffmpeg — on a long video that's hours of wall-clock and thousands of frames to review, most of them talking-head shots. Instead, decide *which moments you want* first, then grab exactly those frames.

**Targeted extraction (default — always try this first):**

1. Get the moment list. In order of preference:
   - The video's **chapter markers**: `yt-dlp --print "%(chapters)j" "<url>"`
   - A **timestamped outline** in the description, or one the user pastes in (users often have these — it's worth asking).
   - Failing both, **read the cleaned transcript** and pick timestamps yourself: the transcript retains `[HH:MM:SS]` markers, so find where the speaker says "as you can see here", "this diagram", "on the screen", "notice that", and take the timestamp from the nearest marker.
2. Pick 10-20 moments that plausibly show a *diagram, schema, chart, or architecture drawing*. Skip anything that's just narration.
3. Offset each timestamp **+20 to +60 seconds past** the stated mark — a section's slide is usually up shortly *after* the topic starts, not at the boundary.
4. Resolve the media URL once and pull single frames in parallel:

```bash
U=$(yt-dlp -f "bestvideo[height<=1080][ext=mp4]" -g "<url>")
for t in 01:31:20 02:28:50 08:15:40; do
  n=$(echo $t | tr -d ':')
  ffmpeg -nostdin -loglevel error -ss $t -i "$U" -frames:v 1 -q:v 2 "frames/t$n.jpg" -y &
done
wait
```

`-ss` **before** `-i` seeks via HTTP range requests, so each frame costs seconds, not hours. Retry any that time out — the URL is signed and expires in a few hours, so re-resolve `$U` if you come back later.

**Full scene-detect sweep (fallback only — short videos, or when no useful moment list exists):**
```bash
ffmpeg -i "$(yt-dlp -g '<url>')" -vf "select='gt(scene,0.3)',scale=1920:-1" -vsync vfr -q:v 2 "<book-dir>/frames/frame_%04d.jpg"
```
For videos over an hour, raise the threshold to 0.4-0.5. Avoid entirely for videos over ~3 hours.

**Then review the frames as images and be ruthless.** For each one ask: *would a TikZ diagram I draw myself be better?* Usually yes. Lecture frames are 16:9 with the presenter occupying a third of the shot, the diagram is small and off-center, and the text is anti-aliased video — it looks poor at print resolution beside crisp vector type.

- **Keep** only frames that are information-dense, full-screen, and hard to redraw (complex architecture diagrams, real tool screenshots, photographs).
- **Discard and redraw in TikZ** anything that's a simple table, box-and-arrow diagram, Venn diagram, tree, or timeline. These are exactly what TikZ is good at, and a hand-authored version is sharper, theme-consistent, and captionable.
- Rename kept frames descriptively: `architecture-overview.jpg`, `data-flow-diagram.jpg`.

If nothing survives the review, say so plainly and go all-TikZ — that's a legitimate and common outcome, not a failure.

### 2. Outline & Structure

Based on the transcript(s), create a book outline:

- For a **playlist**: each video becomes a chapter
- For a **single long video**: split by topic into chapters
- Each chapter gets: title, key concepts, which frames/diagrams belong to it

Write the outline to `<book-dir>/outline.md` for reference.

### 3. Write the LaTeX Book (Parallel by Chapter)

Use the LaTeX template below. Spawn **one subagent per chapter** to write its content in parallel.

Split the cleaned transcript into per-chapter files first (`sections/01-topic.txt`, ...) so each agent gets only its own slice rather than the whole thing.

Each chapter agent receives:
- The path to its transcript section (have it Read the file — don't paste 15k words into the prompt)
- The list of kept frames assigned to that chapter, plus which TikZ figures it should author
- The writing style guidelines (from above)
- The outline for context of where this chapter fits
- The exact LaTeX conventions available to it: which custom environments exist, which `lstlisting` styles are defined, which TikZ libraries are loaded, and the escaping rules

**TikZ figures are the default illustration path.** Tell each agent explicitly:
- Which TikZ libraries are loaded in the preamble, and that it may use *only* those — an agent that reaches for `trees`, `pgfplots`, or `smartdiagram` will break the build.
- To stick to plain primitives (`\draw`, `\node`, `\fill`, scopes, `clip`) with explicit coordinates.
- To name 2-4 specific figures you want in that chapter, rather than leaving it open-ended — otherwise you get zero figures or ten bad ones.
- To wrap each in `figure` with a `\caption{}` and `\label{}`.

The main agent writes:
- The preamble and document setup
- Title page, table of contents
- Assembles all chapter files

**LaTeX Template (main.tex):**
```latex
\documentclass[11pt,a4paper]{book}
\usepackage[utf8]{inputenc}
\usepackage[T1]{fontenc}
\usepackage{lmodern}
\usepackage{graphicx}
\usepackage{xcolor}
\usepackage{tcolorbox}
\usepackage{listings}
\usepackage{hyperref}
\usepackage[margin=1in]{geometry}
\usepackage{booktabs}
\usepackage{amsmath}
\usepackage{enumitem}
\usepackage{fancyhdr}
\usepackage{tikz}
\usepackage{microtype}

% O'Reilly-style paragraph spacing
\setlength{\parskip}{0.4\baselineskip plus 2pt minus 1pt}
\setlength{\parindent}{0pt}

% Tighter bullet/enum spacing
\setlist{nosep, leftmargin=1.5em, topsep=0.3em, itemsep=0.15em}

% Syntax highlighting setup
\lstset{
  basicstyle=\ttfamily\small,
  breaklines=true,
  frame=single,
  backgroundcolor=\color{gray!5},
  keywordstyle=\color{blue!70!black},
  commentstyle=\color{green!50!black},
  stringstyle=\color{red!60!black},
  numbers=left,
  numberstyle=\tiny\color{gray},
  numbersep=8pt,
  tabsize=2,
  showstringspaces=false
}

% Dark pastel callout boxes — O'Reilly inspired
\definecolor{insightbg}{HTML}{EDE7F6}
\definecolor{insightframe}{HTML}{7E57C2}
\definecolor{practicalbg}{HTML}{E8F5E9}
\definecolor{practicalframe}{HTML}{66BB6A}
\definecolor{warningbg}{HTML}{FBE9E7}
\definecolor{warningframe}{HTML}{E57373}
\definecolor{asidebg}{HTML}{FFF8E1}
\definecolor{asideframe}{HTML}{FFB74D}

\newtcolorbox{insight}[1][Key Insight]{
  colback=insightbg, colframe=insightframe, coltitle=white,
  title={\textbf{#1}}, fonttitle=\sffamily, breakable
}

\newtcolorbox{practical}[1][In Practice]{
  colback=practicalbg, colframe=practicalframe, coltitle=white,
  title={\textbf{#1}}, fonttitle=\sffamily, breakable
}

\newtcolorbox{warning}[1][Watch Out]{
  colback=warningbg, colframe=warningframe, coltitle=white,
  title={\textbf{#1}}, fonttitle=\sffamily, breakable
}

\newtcolorbox{aside}[1][Side Note]{
  colback=asidebg, colframe=asideframe, coltitle=white,
  title={\textbf{#1}}, fonttitle=\sffamily, breakable
}

% Header/footer
\pagestyle{fancy}
\fancyhf{}
\fancyhead[LE]{\leftmark}
\fancyhead[RO]{\rightmark}
\fancyfoot[C]{\thepage}

\begin{document}
% Title page, TOC, then \include{chapters/ch01} etc.
\end{document}
```

Each chapter goes in `chapters/ch01.tex`, `chapters/ch02.tex`, etc.

### 4. Review Pass

Run **two independent reviews**. They catch different things and neither substitutes for the other.

**4a. Prose review subagent** — reads the full assembled LaTeX source and checks:
1. **Cross-chapter repetition** — the biggest risk when N agents write N chapters independently. The same fun fact, analogy, or concept gets re-derived from scratch in three places. Ask explicitly: does more than one chapter introduce the same term, re-tell the same anecdote, or re-explain the same mechanism?
2. Within-chapter repetition — a point made 4-5 times when twice would do
3. Factual accuracy against the transcript, and correctness of technical claims
4. Continuity — "as we saw earlier" pointing at something never covered; chapters contradicting each other on a fact
5. Tone breaks, filler, and beginner hand-holding that slipped in
6. Formatting consistency — e.g. some chapters titling every callout box and others leaving them all bare, which is visible on the page

Ask for a prioritized list of 15-25 fixes that genuinely matter, not an exhaustive nitpick list. Then apply them with **one agent per file in parallel** — the edits are file-scoped, so there are no conflicts.

**4b. Visual diagram review subagent — DO NOT SKIP THIS.**

A geometrically wrong diagram compiles perfectly and reads fine in source. The prose reviewer will not catch it, because catching it means doing arithmetic on TikZ coordinates rather than reading text. The only reliable check is to *look at the rendered picture*.

Render every figure to its own PNG:

```bash
python3 <skill-dir>/scripts/render-figures.py <book-dir>
```

`<skill-dir>` is wherever this skill is installed — `~/.claude/skills/youtube-to-book/` for a user install, or `.claude/skills/youtube-to-book/` for a project install.

This extracts each `tikzpicture` into a standalone document using the book's own preamble, compiles it, converts to PNG via `sips`, and writes `figrender/index.txt` mapping each PNG to its chapter, source line, and caption.

Then spawn a subagent that **reads every PNG as an image** and checks:
- **Semantic correctness** — does the picture actually depict what the caption claims?
- **Geometry contradicting meaning** — circles that should intersect but don't, regions shaded that should be empty, arrows reversed, tree branches not connecting to their parents
- **Overlap** — text on text, labels colliding with shapes, unreadable nodes
- **Clipping** — content running past the image edge
- **Missing or contradictory labels**
- **Consistency** — same entity keeping the same name, colour, and shape across figures

Tell the agent explicitly not to infer correctness from the `.tex` source, and give it enough domain context to judge each diagram's meaning.

> **A real bug this stage caught:** the four JOIN types were drawn as Venn diagrams with radius 0.95 and centres 2.0 apart — so the circles missed each other by 0.1 and never intersected. INNER JOIN, whose entire result *is* the intersection, rendered as two blank circles. It compiled with zero warnings, passed the prose review, and shipped into a 113-page PDF before a human noticed. Assume this class of bug is present until you have looked at the pictures.

After fixing any figure, re-render and look again — verify the fix, don't assume it.

### 5. Compile Loop

Run the self-correcting compile loop:

```bash
cd <book-dir>
tectonic main.tex
```

If compilation fails:
1. Read the error output
2. Fix the LaTeX error (common: unescaped special chars like `_`, `%`, `&`, `#`, `$`; missing `\end{}` tags; bad image paths)
3. Re-run compilation
4. Repeat until success (max 10 attempts)

Tectonic handles package downloads automatically and runs multiple passes (for TOC, references, etc.) in a single invocation.

### 6. Final Output

Report to the user:
- Path to the compiled PDF: `<book-dir>/main.pdf`
- Number of chapters and approximate page count
- Any sections that might need the user's review
- Suggest: "Want me to adjust any chapter's depth or style?"

## Important Notes

- **A clean compile is not a correct book.** Tectonic exiting 0 means the LaTeX parsed — nothing more. Diagrams can be geometrically wrong, tables can contradict the prose, and chapters can repeat each other, all with zero warnings. Both review passes in step 4 are load-bearing.
- **Escape LaTeX special characters** in all transcript content: `_`, `%`, `&`, `#`, `$`, `~`, `^`, `{`, `}`, `\`
- **Image paths** must be relative to `main.tex` location
- **Don't over-extract frames** — quality over quantity. 5-15 good diagrams per chapter max
- **Chapter files** use `\chapter{Title}` at the top, no `\documentclass` or `\begin{document}`
- If transcript quality is poor (auto-generated), clean up grammar and technical terms before using
- For playlists with many videos, ask the user if they want all videos or a subset
