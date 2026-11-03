# delivery-dashboard-ux on the density of cross-table rows (2026-10-22)

About two thirds of the S6 section is repetition: each check appears once per
tool, with the "Read against" sentence and the description repeated each time.
The real information is five relationships, the supply each read, and one
dual result.

Constraint: each row is a `<button class="scope-check">` (template line about
7842), and a button cannot contain links, buttons or `<details>`. The panel
the row opens already carries the c7 sentence (264 c8). `.sr-only` exists
(line 387).

## Option A (recommended): one row per check, per-tool pills

- The row becomes a container. The check name opens the worst tool's panel,
  and each tool is its own pill button.
- An ordinary row gets a short "vs <dataset> in the warehouse, received <day>"
  or "vs <dataset> received <day>, not in the warehouse yet" (`fmtDay`, with
  the time added only where two supplies share a day).
- The dual row shows both verdicts in words: "Staged Investigations (received
  2 Oct): Pass · Investigations in the warehouse (received 1 Jul): Fail — why
  it is held back".
- The full sentences go in the panel and in each pill's `.sr-only` accessible
  name. The description appears once per row, or only in the panel.
- About 30 lines become about 12; at phone width the pills wrap.
- Criteria: 264 M4 becomes one row per check with pills in tool order; 264 c7
  moves the sentence into the panel and accessible name; 264 NFR 2 becomes one
  labelled row per relationship; 272 c6 is short on the row and full in the
  panel; 272 c4/c5 show both verdicts on the row; new test for the S6 row and
  the accessible names.

## Option B: one row per tool, the sentence once per group heading

Everything stays visible and the rows stay buttons. But the dual row's staging
Pass is shown only in short form, and the section order changes from by
relationship (264 M4, signed) to by supply read.

## Option C: a staging | warehouse column grid

The two views become visible as structure. But most rows fill only one
column, and at 375px the columns stack and the comparison is lost.

Whichever option is chosen, "in place in the warehouse" adds about 17
characters to every long sentence; in A and C that cost stays in the panel.
