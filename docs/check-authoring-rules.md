# Check authoring rules

How to write the three hand-authored prose fields every QA check
carries: `description`, `failure_indicates` and `technical_note`. These
are the fields a data steward actually reads in the dashboard's check
drawer, so they are the only part of a check definition written for
someone who does not know dbt, Soda, datacontract-cli or Evidently.

**This file is the standing standard.** It applies to every check
authored from here on, across all four tools and every dataset - not
just to the checks `REQ-QAC-024` rewrote. Read it before adding a check
or editing any of the three fields.

**Where the rules came from.** They were settled with Keith on
2026-09-20 over 25 real checks, reviewed three at a time. Every rule
below came from him rejecting a specific draft, which is why each one
carries the draft it replaced - the rejected wording is usually the
clearest statement of what the rule is actually for. Nothing here was
drafted up front.

**What is the source of truth for what, so this file and the code
cannot quietly disagree:**

- `qa_tools/common/check_lifecycle.py`'s `CheckMetadata` defines the
  fields themselves - names, types, which are optional, and which sit
  outside the config hash. If this file and that dataclass ever
  disagree about the mechanics, the dataclass wins.
- This file carries the authoring standard, which no code can express:
  what good prose looks like, and what has already been rejected.
- `requirements.yaml`'s `REQ-QAC-024` carries the decisions about that
  one migration pass - its measured counts, its dependency on
  `REQ-QAC-023`, the shape of the work. It does not restate the rules
  below, deliberately, so there is only ever one copy of each.

**Nothing below is CI-enforced, and that is a known weakness.** The
lifecycle gate checks that `failure_indicates` is present (a real value
or the `self-evident` sentinel) and nothing more. It cannot tell whether
a description names an agency or lists allowed values. The bar is
"sounds right to a non-technical colleague", the check's own maintainer
authors it, and there is no review step - Keith's explicit call, with
no reading-age target, no length cap and no external style guideline.

**These fields are published on a public site.** Also Keith's explicit,
informed decision, made with that consequence named. There is no limit
on what a failure's consequence may say. If this is ever pointed at real
production data rather than synthetic, that is a decision to revisit
deliberately, not an unexamined default.

---

## The three fields

| Field | Who reads it | Required |
|---|---|---|
| `description` | Anyone looking at the check in the dashboard | Yes |
| `failure_indicates` | Same reader, when the check has failed | Yes - a real value, or the literal `self-evident` |
| `technical_note` | A contributor reading the check definition. **Never published.** | No, and expect it to stay near-empty |

`description` answers **what does this check verify**.
`failure_indicates` answers **what has most likely gone wrong upstream
if it failed**. They are separate questions and a good description
answers only the first.

`technical_note` is contributor-facing and is deliberately not embedded
into the built page. There are tests asserting it never reaches the
dashboard. Do not publish it.

---

## Rules for `description`

### State what the check verifies, and only that

Many descriptions written before this standard welded the failure
meaning on and never said what the check does at all. The worked
example: *"A registration date earlier than the birth date indicates a
corrupt or misjoined record"* never says the dates have to be in order.
Split it - the ordering rule is the description, the corrupt-record
reading is `failure_indicates`.

### No agency names

*"BDM's unique registration identifier"* became *"Every registration
identifier must be unique"*. The reader already knows whose data they
are looking at from where they are standing in the dashboard, and a
hard-coded agency name goes stale the moment a check is reused.

### No enumerated value lists

*"Sex must be one of the closed value set M, F, or X"* became *"one of
the values the contract allows"*. The values already exist structurally
in the check definition, and often on the column too, so prose is a
third copy - and the only one of the three that cannot be filtered,
counted or validated.

This is the rule that prompted `plans/running-thoughts.md` #16: a
histogram of real arrived value counts answers "which values" far
better than a sentence restating the contract, because it shows a value
that is technically allowed but has collapsed to almost nothing.

### For an invalid-values check, state the tolerance, not the purpose

*"Must be one of the allowed values"* is what that check type **is** -
saying so tells a reader nothing that distinguishes this instance from
any other. What actually differs between instances is the tolerance: one
tolerates none, another tolerates a few and only fails on a sustained
rise, a third scopes itself to the most recent supplies only.

That is also why shared wording is dangerous here specifically - see
"Shared wording is permission, not obligation" below.

---

## Rules for `failure_indicates`

### "Most likely" is not a licence to guess

Author a real value only where the upstream cause is genuinely known.
Where the honest answer is a plausible-sounding story you constructed to
fill the field, the value is the literal sentinel:

```yaml
failure_indicates: self-evident
```

Two of the first three drafts reviewed were rejected on exactly this,
and both became `self-evident`. Roughly half of the 25 checks reviewed
did. **Expect the sentinel to be the common case, not the exception** -
reaching for it is the correct instinct, not a failure to try hard
enough.

**What the sentinel does to the page:** nothing shows. The drawer omits
the "What a failure means" heading entirely, exactly as it does for a
check that has no value at all, so that heading only ever appears with
something real underneath it. The authored string does travel through
to the built page data - it is resolved in the template rather than at
the builders (Keith, 2026-09-20) - so it is visible in page source, and
that is fine: it is an authoring marker, not contributor prose. Unlike
`technical_note`, it is not something a viewer must not see.

Write it as a plain scalar. A `>` block scalar folds a trailing newline
onto it, which the template trims for exactly this reason, but a plain
scalar is what the rest of the tooling expects.

**Spell it exactly.** `self evident`, `Self_Evident` and `selfevident`
are all rejected by the lifecycle gate rather than quietly accepted.
They have to be: any non-empty value satisfies the "say something" rule,
so a near-miss would pass the gate and then render verbatim under a
heading on the public page - which is the one thing the sentinel exists
to prevent.

### Say what a failure indicates, not what the check verifies in other words

If the sentence you have written is the description rephrased, the
answer is `self-evident`.

### Say nothing about what to do about it

Remediation belongs to the ticket, not to the check definition. A ticket
is a live thing with an owner and a state; a check definition is a
standing fact. The two rot at different rates, and a check definition
that carries a remediation step is wrong the first time the process
changes.

---

## Rules for `technical_note`

`technical_note` is kept, narrowed, and may go entirely unused in a
given pass. It holds standing facts a contributor needs and a viewer
must not see: cross-references between checks, and notes explaining why
a check behaves as it does by construction.

**It must not hold synthetic-data or generator facts.** Those are
meaningless the moment this is pointed at real data.

**It must not hold a note that really describes a GAP.** Fix the gap
instead. The worked example: a Soda completeness check on
`date_of_birth` carried a clause explaining that a silently renamed
column would surface here as 100% missing rather than as a schema
failure. That is not a standing fact about the check - it is a symptom
of nothing checking the column set at all. The clause was dropped and
the gap became `plans/running-thoughts.md` #17 instead.

**It must not hold dated definition changes.** Those belong in the
check's own `changelog`. The boundary is load-bearing and was tested
against the real text before the field was kept: a changelog entry
carries a date, an author and a breaking flag; a standing fact has none
of those. Forcing one into the changelog means inventing a date and an
author for something that never happened, which corrupts the one field
whose whole job is who changed what, when.

When an existing description contains dated definition history, move it
into the changelog - not into `technical_note`.

---

## Rules that apply to all three fields

### Name no tool, macro or statistical method

No `accepted_values`, no `dbt_utils.expression_is_true`, no
`invalid_percent`, no "two-sample K-S test". The reader does not know
which tool ran the check and should not need to.

### Cross-reference nothing a reader cannot follow

No "see the rowCount rule", no file paths, no check ids. A cross-
reference between checks is the one thing `technical_note` is legitimately
for, because that field is never published.

### Real column and table names are fine

Where a real column or table name is the clearest way to say what is
being checked, use it. This is a deliberate exception to the "no jargon"
rule - `date_of_birth` is clearer to a steward than a paraphrase of it,
because it is the name they see on the data itself.

### Never leak run, cadence or delivery mechanics

*"within 7 days of this run's own `date_registered`"* assumes a run
concept that will not exist in production. Neither will *"a day's
registrations"* - that assumes a cadence this data asset does not
guarantee. Compare against **"the previous supply"** instead, which is
true regardless of how often data arrives or what triggered the check.

### Drop measured results; keep the rule they justify

A description states the rule. It does not carry the measurement that
was used to set the rule. *"tolerated null up to ~5%"* stays;
*"(real observed range: 0.9-3.3%)"* goes.

Keith's call, 2026-09-20, taken against three real alternatives that
would each have kept the number somewhere - `evidence:` on the
requirement that owns the check battery, `technical_note`, and a new
requirement invented to hold it. The reasoning that beat all three:
observed ranges are recomputable from committed
`dataset_stats.json` whenever anyone actually wants them, so writing
them into prose buys nothing that cannot be got back, while costing a
sentence that goes stale silently the moment the data moves.

The same applies to a note saying how a check behaves on this project's
own synthetic runs - *"Passes 0/0 on every clean run"* - which is both
a measured result and generator prose, and fails this rule twice over.

### Shared wording is permission, not obligation

Where two tools genuinely check the same thing, their wording may be
identical - there is no requirement to manufacture a difference. But
per-engine wording exists precisely because the checks sometimes differ,
and identical text can paper over a real difference. The worked case:
dbt's `accepted_values` is pass/fail, Soda's `invalid_percent` tolerates
up to 2%, and a third variant scopes to the most recent supplies only.
Same rule, three genuinely different questions, and one shared sentence
would be wrong for two of them.

So splitting wording **apart** is as much part of authoring as reusing
it. Check what the check actually does before copying its sibling's
text.

---

## Mechanics

### Use block scalars

Plain English carries apostrophes, colons and hashes that terse
technical text does not, and most of these fields are hand-edited into
YAML. Two real breakages happened in a single morning just writing
`REQ-QAC-024` itself: a continuation line beginning with a `#` parsed as
a comment, and a `: ` inside a plain scalar split the key.

```yaml
attributes:
  description: >
    Every registration identifier must be unique.
  failure_indicates: >
    The same registration has been supplied twice, or two registrations
    were assigned the same identifier at source.
```

The `check-yaml` pre-commit hook catches YAML that no longer parses. It
does **not** catch a mangled-but-still-valid string, which is the more
dangerous outcome and has bitten this project before.

### Editing wording never changes a check

None of the three fields is part of a check's `config_hash`. Editing any
of them with no change to the check's actual config does not report the
check as changed and does not require a changelog entry - the same
treatment `name` and `description` already had.

There is deliberately **no audit trail** when wording changes, however
material: out of the config hash, out of the changelog. Keith's explicit
call. The committed `dashboard/snapshots/*.html.gz` files become the de
facto record of what wording was live when.

One real trap, worth knowing before adding any field of this kind:
Evidently's parser excludes config-hash fields by an explicit name list
rather than by excluding the whole metadata block the way dbt's and
Soda's do. A new field that is not added to that list changes every
Evidently check's hash.
