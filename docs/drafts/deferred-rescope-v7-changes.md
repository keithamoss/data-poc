# One-offs v7: what changed from v6, for re-signing (2026-11-21)

v7 takes v6 and applies Keith's answers to its six questions. Those answers are
at the end of `deferred-rescope-reviews-v5.md`. This file covers v6 to v7 only;
for v5 to v6, see `deferred-rescope-v6-changes.md`. Nothing has been applied to
requirements.yaml. Every requirement in `deferred-rescope-v7.yaml` and every
amendment in `deferred-rescope-amendments-v7.yaml` is a proposal until Keith
signs it.

Each change below is tagged:

- **[BEHAVIOUR]**: it changes what the v6 draft said the system does.
- **[SETTLED]**: Keith's answer confirms what v6 already drafted, and the
  PROVISIONAL mark comes off.
- **[STRUCTURE]**: something moved or was renumbered, and the meaning is the
  same.

Every change has a `v7, ...` or `SETTLED by Keith ... (v6 Qn)` decision on its
requirement.

## The new id

**REQ-PIPE-448** is new. It was split out of REQ-PIPE-446 (Q6 (b)). It is the
next free number:

- requirements.yaml's highest id is 432.
- The v1 to v6 drafts use 433 to 447.
- 445 was used in v2 and rejected. I did not reuse it, so it can never be
  confused with that draft.
- No file under docs/ or plans/ mentions 448.

Its title: "`mothman check` gates one-off folders - every (gate, kind) declared,
changed folders and changed templates gated in full and every other folder by a
digest pass, reported one row per gate - and no CI workflow or session-start
hook touches one."

## What moved out of REQ-PIPE-446 into REQ-PIPE-448

| v6 REQ-PIPE-446 | v7 REQ-PIPE-448 |
|---|---|
| c10: each (gate, kind) declared; not-applicable words per kind; `_has_synthetic` | c1 |
| c11: changed folders gated in full plus their digest; the digest pass over the rest; untracked files | c2 |
| c12: check's output (counts, one line for not-applicable gates, the failing file) | c3 |
| c13: the collections gate accepts a kind's shared adapter | c4 |
| c14: the test that no CI workflow or hook loops over, selects or loads a one-off | c5 |
| c20: a kind's template is gated when it changes | c6 |

- **NFRs that moved:** SCALABILITY (2,000 interpreter starts), COST (CI's shell
  loops and yamllint), MAINTAINABILITY (validate-config.yml never checks
  one-offs).
- **Decisions that moved:**
  - EACH (GATE, KIND) DECLARES
  - THE EXTRACTION KIND'S DECLARATIONS
  - round 5 Q2 (b)
  - REUSE (adapter registry, check rows)
  - v6 GATES (K)
  - v6 DIGEST HOLES (H)
  - v6 check's OUTPUT (C5)
  - v6 THE TEMPLATE IS GATED
- **Dependencies:** REQ-PIPE-385 moved from 446 to 448. 448 also depends on
  REQ-PIPE-446 and REQ-PIPE-440.

446 keeps v6's c1 to c9, and v6's c15 to c19 become c10 to c14. 446 goes from
20 criteria to 14; 448 has 6.

**Repointed references:**

- 440 c5 now points at "REQ-PIPE-448's digest pass".
- 437 depends on 448.
- 446's own decisions and SECURITY NFR now refer to c11, c13 and c14.
- The following now cite 446 c13 for the project and c14 for never-GitHub:
  - 444's and 439's decisions
  - 440's push decision
  - 437's never-GitHub decision
  - 433's never-GitHub decision
- 448's moved NFRs point at its own c2, c5 and c6.
- amendments-v7 plans_drafts: sprint 29 owns REQ-PIPE-448, and the build order
  puts 448 after 440 (it reads 440's digest).

## By requirement

### REQ-PIPE-446

- [BEHAVIOUR] **Title:** now "selected only by `mothman one-off --id` or its
  TUI, never by MOTHMAN_ASSET". The story no longer mentions the gate cost,
  which went to 448.
- [BEHAVIOUR] **c3** (Q2 (b)): if MOTHMAN_ASSET is **set at all** while a
  one-off is named, the command is refused. In v6 it was refused only if the
  variable named something other than the --id.
- [BEHAVIOUR] **c7:** `handoff()`/`adopt()` carry a one-off selected by --id
  into child processes, and **never write it into MOTHMAN_ASSET**. Today
  `assets.select()` writes the name into os.environ. Doing that for a one-off
  would hand a child process a value c9 refuses. I found this checking
  asset_model/assets.py against Q2.
- [BEHAVIOUR] **c8:** "while a one-off is selected" is gone; it now simply
  states that no collection group is built for a one-off.
- [BEHAVIOUR] **c9** (Q2 (b)): the allowlist (only `one-off`, `check` and
  `--help` run while a one-off is selected) is replaced by a refusal:
  "MOTHMAN_ASSET naming a one-off's id is treated as naming no asset folder,
  refused as REQ-PIPE-363 c4/c6 refuse, and never selects it."
  - Once nothing outside `mothman one-off` can select a one-off, the allowlist
    had nothing left to govern.
  - The architect's A concern stays closed: `pipeline process` can no longer
    reconcile tickets for a one-off.
  - The v6 decision for the allowlist is marked SUPERSEDED.
- [STRUCTURE] **c10** (v6 c15): it now amends 363 criteria **1, 4, 5 and 6**.
  The v6 criterion 2 amendment is withdrawn (see below).
- [STRUCTURE] v6's c16 to c19 become c11 to c14, with no wording change.
- Decisions added: Q2 (b) SETTLED, with (a) REJECTED; the allowlist becoming a
  refusal; no one-off in MOTHMAN_ASSET even internally; c8's reword; Q6 (b)
  SETTLED, with re-signing it at 20 criteria REJECTED.

### REQ-PIPE-448 (new)

- [STRUCTURE] It holds the six criteria above, word for word as in v6 apart from
  the renumbered internal references.
- It has three new decisions:
  - why it was split (Keith's Q6 words)
  - why the CI/hook test came with it (Keith named c14)
  - why it depends on REQ-PIPE-440 and REQ-PIPE-385

### REQ-PIPE-442

- [BEHAVIOUR] **c1:** every `mothman one-off` command runs with MOTHMAN_ASSET
  unset **and is refused with it set** (Q2 (b), pointing at 446 c3).
- [BEHAVIOUR] **c3** (Q1 (a)): load also **records the repository commit it ran
  at** in the one-off's database, beside the package digest.
- [SETTLED] c5 (Q3 (a)): the same package loads again after an unpublished
  drop. The question mark came out of the RESUME decision, and a SETTLED
  decision was added with (b), a committed drop marker, REJECTED.
- [SETTLED] c10 (Q5 (a)): list shows the cheap stages only. The PROVISIONAL
  mark is cleared, and (b), opening every database, is REJECTED.

### REQ-PIPE-435

- [SETTLED] **c1** (Q4 (a)): could-not-load and could-not-check count as
  outcomes. The "(PROVISIONAL, question 4 ...)" text is removed, and the
  PROVISIONAL decision is replaced by a SETTLED one with (b) REJECTED.

### REQ-DASH-444

- [BEHAVIOUR / SETTLED] **c8** (Q1 (a)): the page shows the build commit
  labelled **'built at'** and the commit its checks ran at, labelled
  **'checked at'**. The 'checked at' commit is the one load recorded
  (442 c3). The PROVISIONAL mark is cleared, and (b), the build commit only, is
  REJECTED.

### REQ-PIPE-440

- [SETTLED] **c9** (Q1 (a)): load refuses an uncommitted or unpushed
  **template**, as it refuses such a folder. The "(The template half is
  PROVISIONAL ...)" text is removed and a SETTLED decision is added.
- [STRUCTURE] c5's reference moves to REQ-PIPE-448.

### REQ-TEST-437

- [BEHAVIOUR] **c2:** each page is asserted to carry its 'checked at' and
  'built at' commits.
- [BEHAVIOUR] **c3:** load is now asserted refused **while MOTHMAN_ASSET is
  set**. In v6 the test was refused-if-different. c3 also adds three
  assertions:
  - a command with MOTHMAN_ASSET naming the one-off is refused
  - the same package loads again after an unpublished drop (Q3)
  - load is refused while the template is uncommitted (Q1)
- [STRUCTURE] It now depends on REQ-PIPE-448, and its decisions point at
  446 c14 and at 446 c3 and c9.

### REQ-GHUB-433, REQ-PIPE-439

- [STRUCTURE] Decision references only. 433 now says no command outside
  `mothman one-off` can select a one-off (446 c3, c9). 439 now cites 446 c13.

### Unchanged in v7

REQ-PIPE-434, REQ-DASH-436, REQ-PIPE-438, REQ-PIPE-443, REQ-DASH-447 and
REQ-QAC-441 have no changes beyond the "v7, PROPOSAL until re-signed" source
line.

### Amendments

- [BEHAVIOUR] **REQ-PIPE-363 c1:** MOTHMAN_ASSET names an asset folder only; a
  one-off is named by --id or the TUI, and MOTHMAN_ASSET set beside either is
  refused.
- [BEHAVIOUR] **c2: the v6 amendment is WITHDRAWN.** Criterion 2 as built
  ("none built WHILE MOTHMAN_ASSET is unset or names no asset folder") already
  covers this, because MOTHMAN_ASSET never names a one-off. c2 stays as signed.
- [BEHAVIOUR] **c4, c5, c6:** the one-off half is reworded to Keith's words,
  and a one-off's id counts as "names no asset folder". The full texts are
  below.
- [BEHAVIOUR] **c11 (the new tests):** reworded to match.
- Set A, REQ-PIPE-342, REQ-PIPE-106: unchanged. I checked Set A by diff; it is
  byte-identical to v6.

## REQ-PIPE-363 c4, c5 and c6: the final text, for Keith's approval

### The criteria as amended

**c4.** "IF a command that is not one of the tool commands of criterion 5 is
given WHILE MOTHMAN_ASSET is unset or names no asset folder - a one-off's id
included (REQ-PIPE-446 criterion 9) - THEN THE SYSTEM SHALL answer not 'No such
command' but that MOTHMAN_ASSET is not set, or names no asset folder, naming the
variable, listing the folder names found under assets/, then - WHERE one-off
folders exist - saying 'For one of <n> <kinds>, use mothman one-off.', and
saying there is deliberately no default, in the form environments.current()
uses for MOTHMAN_ENVIRONMENT - reading nothing but those folder names; <n>
<kinds> is each kind that has folders, counted in its plural display word,
joined with 'or' (e.g. '37 extractions or 2 audits'), and WHERE no one-off
folder exists the sentence is left out."

**c5.** "WHILE MOTHMAN_ASSET is unset, THE SYSTEM SHALL run `mothman check`,
`mothman --help`, every `mothman one-off` command (REQ-PIPE-442 criterion 1) and
every command that reads no asset configuration and opens no connection, and
`mothman --help` SHALL say, as one line inside its Collections panel
(REQ-TEST-252 criterion 2's two-panel layout kept), 'Set MOTHMAN_ASSET to one
of: <the asset folder names found>.' followed - WHERE one-off folders exist - by
criterion 4's sentence 'For one of <n> <kinds>, use mothman one-off.'"

**c6.** "IF a command that reads asset configuration or opens a connection runs
WHILE MOTHMAN_ASSET is unset or names no asset folder - a one-off's id included
(REQ-PIPE-446 criterion 9) - THEN THE SYSTEM SHALL refuse before reading any
asset configuration or opening any connection, naming the variable and every
asset folder found, followed - WHERE one-off folders exist - by criterion 4's
sentence 'For one of <n> <kinds>, use mothman one-off.', and SHALL NOT fall back
to a default, a last-used value or the only asset present - except every
`mothman one-off` command (REQ-PIPE-442 criterion 1), which runs with
MOTHMAN_ASSET unset, is refused with it set, and selects its one-off by `--id`
or in its TUI."

### The exact messages a person would see

These assume asset folders `daily` and `quarterly` and 37 extraction folders.
In each refusal, the first sentence, "Set it to one of: ...", and the
"deliberately no default" sentence are the built refusal
(`asset_model/assets.py` `_refusal`), unchanged. Only the one-off sentence is
new.

- **Unset, one-offs exist (c4/c6):** "MOTHMAN_ASSET is not set, so this command
  cannot say which data asset it acts for. Set it to one of: daily, quarterly.
  For one of 37 extractions, use mothman one-off. There is deliberately no
  default - a command that guesses is a command that can act for an asset it was
  not meant to."
- **Mistyped (c4/c6):** "MOTHMAN_ASSET is 'quartely', which names no asset
  folder. Set it to one of: daily, quarterly. For one of 37 extractions, use
  mothman one-off. There is deliberately no default - a command that guesses is
  a command that can act for an asset it was not meant to."
- **Set to a one-off's id (c4/c6, via 446 c9):** "MOTHMAN_ASSET is
  'cohort-2026-a', which names no asset folder. Set it to one of: daily,
  quarterly. For one of 37 extractions, use mothman one-off. There is
  deliberately no default - a command that guesses is a command that can act for
  an asset it was not meant to."
- **No one-offs at all:** "MOTHMAN_ASSET is not set, so this command cannot say
  which data asset it acts for. Set it to one of: daily, quarterly. There is
  deliberately no default - a command that guesses is a command that can act for
  an asset it was not meant to."
- **--help Collections line (c5):** "Set MOTHMAN_ASSET to one of: daily,
  quarterly. For one of 37 extractions, use mothman one-off." With no one-offs:
  "Set MOTHMAN_ASSET to one of: daily, quarterly."

## Still needing Keith

1. **His yes to the 363 c4, c5 and c6 text above.** These were signed wording,
   and he gave the one-off sentence himself.
2. **One extension of his words, inside that yes.** When more than one kind has
   folders, the sentence joins them with "or": "For one of 37 extractions or 2
   audits, use mothman one-off." He only gave the one-kind form; I recommend
   this one.
3. **Not proposed, and offered only in case he wants it:** a person who puts a
   one-off's id in MOTHMAN_ASSET gets the generic "names no asset folder"
   refusal above. It could instead name the one-off ("'cohort-2026-a' is an
   extraction; use mothman one-off load --id cohort-2026-a"). I left this out
   because his sentence already points to `mothman one-off`, and the refusal
   wording is his to change.

Nothing else is open. All six v6 questions are applied, no criterion carries a
PROVISIONAL mark, and the only open_questions entries are the build-detail ones
v6 already had: 433's credential and interval home, and 442's package location.

## Carry-over check (v6 questions to v7)

| v6 question | Keith | Applied where |
|---|---|---|
| Q1 commits | (a) | 442 c3 (load records its commit); 444 c8 ('checked at' and 'built at'); 440 c9 (template refusal settled); 437 c2, c3 |
| Q2 MOTHMAN_ASSET | (b) | 446 title, c3, c7, c8, c9 and decisions; 442 c1; 437 c3; 363 c1, c4, c5, c6, c11; c2 amendment withdrawn |
| Q3 reload after drop | (a) | 442 decision settled; 437 c3 |
| Q4 could-not-check | (a) | 435 c1 and decision settled |
| Q5 list stages | (a) | 442 decision settled |
| Q6 split | (b) | New REQ-PIPE-448; 446 renumbered; every reference repointed (see above) |

6 of 6 applied. Unaccounted: 0.
