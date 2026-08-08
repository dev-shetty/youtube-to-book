#!/usr/bin/env node
'use strict'

const fs = require('node:fs')
const os = require('node:os')
const path = require('node:path')
const { execFileSync } = require('node:child_process')

const SKILL_NAME = 'youtube-to-book'
const SRC = path.join(__dirname, '..', 'skill')
const pkg = require('../package.json')

const args = process.argv.slice(2)
const has = (...flags) => flags.some((f) => args.includes(f))

function targetDir() {
  const i = args.findIndex((a) => a === '--dir' || a === '-d')
  if (i !== -1 && args[i + 1]) return path.resolve(args[i + 1])
  const root = has('--project', '-p') ? process.cwd() : os.homedir()
  return path.join(root, '.claude', 'skills', SKILL_NAME)
}

function usage() {
  console.log(`
${pkg.name} v${pkg.version} — ${pkg.description}

Usage
  npx ${pkg.name} install [options]     Install the skill
  npx ${pkg.name} uninstall [options]   Remove the skill
  npx ${pkg.name} where [options]       Print the install path
  npx ${pkg.name} doctor                Check required external tools

Options
  -p, --project      Install into ./.claude/skills (this repo) instead of ~/.claude/skills
  -d, --dir <path>   Install into an explicit directory
  -f, --force        Overwrite an existing install without asking
  -h, --help         Show this message

After installing, restart Claude Code and paste a YouTube URL:
  "turn this into a textbook: https://youtube.com/watch?v=..."
`.trim())
}

function copyDir(src, dest) {
  fs.mkdirSync(dest, { recursive: true })
  for (const entry of fs.readdirSync(src, { withFileTypes: true })) {
    const from = path.join(src, entry.name)
    const to = path.join(dest, entry.name)
    if (entry.isDirectory()) copyDir(from, to)
    else fs.copyFileSync(from, to)
  }
}

function install() {
  const dest = targetDir()
  if (fs.existsSync(dest) && !has('--force', '-f')) {
    console.error(`✗ ${dest} already exists. Re-run with --force to overwrite.`)
    process.exit(1)
  }
  fs.rmSync(dest, { recursive: true, force: true })
  copyDir(SRC, dest)
  fs.chmodSync(path.join(dest, 'scripts', 'render-figures.py'), 0o755)
  console.log(`✓ Installed ${SKILL_NAME} → ${dest}`)
  console.log('  Restart Claude Code, then give it a YouTube URL.')
  doctor({ quiet: true })
}

function uninstall() {
  const dest = targetDir()
  if (!fs.existsSync(dest)) {
    console.log(`nothing to remove at ${dest}`)
    return
  }
  fs.rmSync(dest, { recursive: true, force: true })
  console.log(`✓ Removed ${dest}`)
}

// The skill shells out to these; a missing one fails the run halfway through,
// so surface it up front instead.
const REQUIRED = [
  ['yt-dlp', 'transcripts, metadata, media URLs', 'brew install yt-dlp'],
  ['ffmpeg', 'key-frame extraction', 'brew install ffmpeg'],
  ['tectonic', 'LaTeX compilation', 'brew install tectonic'],
  ['python3', 'figure-render script', 'preinstalled on macOS/Linux'],
]

function found(bin) {
  try {
    execFileSync(process.platform === 'win32' ? 'where' : 'which', [bin], {
      stdio: 'ignore',
    })
    return true
  } catch {
    return false
  }
}

function doctor({ quiet = false } = {}) {
  const missing = []
  const lines = REQUIRED.map(([bin, why, how]) => {
    const ok = found(bin)
    if (!ok) missing.push([bin, how])
    return `  ${ok ? '✓' : '✗'} ${bin.padEnd(10)} ${why}`
  })
  // PDF→PNG has three interchangeable backends; any one is enough.
  const raster = ['pdftoppm', 'sips', 'magick'].filter(found)
  const rasterOk = raster.length > 0
  if (!rasterOk) missing.push(['pdftoppm', 'brew install poppler'])
  lines.push(
    `  ${rasterOk ? '✓' : '✗'} ${'pdf→png'.padEnd(10)} figure review` +
      (rasterOk ? ` (via ${raster[0]})` : '')
  )

  if (!quiet || missing.length) {
    console.log(`${quiet ? '\n' : ''}Dependencies:`)
    console.log(lines.join('\n'))
  }
  if (missing.length) {
    console.log('\nMissing — install with:')
    for (const [bin, how] of missing) console.log(`  ${bin}: ${how}`)
  }
  return missing.length === 0
}

const cmd = args.find((a) => !a.startsWith('-'))

if (has('--help', '-h') || !cmd) usage()
else if (cmd === 'install') install()
else if (cmd === 'uninstall' || cmd === 'remove') uninstall()
else if (cmd === 'where') console.log(targetDir())
else if (cmd === 'doctor') process.exit(doctor() ? 0 : 1)
else {
  console.error(`unknown command: ${cmd}\n`)
  usage()
  process.exit(1)
}
