---
name: web-design-guidelines
description: Review UI code for Web Interface Guidelines compliance. Use when asked to "review my UI", "check accessibility", "audit design", "review UX", or "check my site against best practices".
metadata:
  author: vercel (adapted, 2026-09-19 - see reference/web-interface-guidelines.md's own header for the real provenance note)
  version: "1.0.0"
  argument-hint: <file-or-pattern>
---

# Web Interface Guidelines

Review files for compliance with Web Interface Guidelines.

## How It Works

1. Read the vendored guidelines below - no live fetch
2. Read the specified files (or prompt user for files/pattern)
3. Check against all rules in the vendored guidelines
4. Output findings in the terse `file:line` format

## Guidelines Source

Read the real, vendored ruleset committed at
`.claude/skills/web-design-guidelines/reference/web-interface-guidelines.md`
- a real, unmodified snapshot of `vercel-labs/web-interface-guidelines`'s
own `command.md`, pinned 2026-09-19 (see that file's own header comment
for the full provenance note and how to re-sync it). Deliberately NOT a
live `WebFetch` on every run, unlike the upstream Vercel skill this was
adapted from - Keith's own explicit call, 2026-09-19: this project
prefers a reproducible, offline copy over a live external dependency on
every review (same reasoning as `dashboard/vendor/`'s own vendored
assets). The real content and rules are unchanged from upstream, only
the retrieval mechanism differs.

## Usage

When a user provides a file or pattern argument:
1. Read the vendored guidelines from
   `.claude/skills/web-design-guidelines/reference/web-interface-guidelines.md`
2. Read the specified files
3. Apply all rules from the vendored guidelines
4. Output findings using the format specified in the guidelines

If no files specified, ask the user which files to review.
