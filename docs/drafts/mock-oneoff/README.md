# A worked mock one-off: ED readmissions 2021-2024

Kept at Keith's ask (2026-11-24) so that nothing from the worked example is
lost with the container that made it (running-thoughts #144). The published
page with the same content is a private claude.ai artifact, "One-off
Walkthrough".

- `WALKTHROUGH.md`: the whole run, step by step. Each command's exact output,
  every generated file, the database rows and the findings. Run at db7d7aa1,
  before the four defects it found were fixed (post-build-review #494).
- `screenshots/`: the published page at that commit. They show the defects
  as found; the false green (D1) and the missing check names (D2) are fixed
  since.
- `captures/`: each command's raw output and the folder tree after each step.
- `package/`: the mock extraction package itself (recipe.json and its CSVs),
  with four planted problems. Recipe format v1, the stand-in until the real
  format arrives through a translator (running-thoughts #145).
- `make_package.py.txt`: the seeded script that wrote `package/`. It is kept
  as text on purpose. It is a record, not an entry point, and an entry point
  would need a `mothman` subcommand (CLAUDE.md). To regenerate the package,
  copy it to a scratch directory as a .py file and run it with
  `python3 make_package.py <out-dir>`.

To replay the walkthrough today: `mothman one-off open --kind extraction
docs/drafts/mock-oneoff/package` in a scratch clone with a local bare origin,
then commit and push, then load, decide and publish, as WALKTHROUGH.md shows.
