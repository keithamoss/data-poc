# The on-disk delivery format

**Status: normative.** This is the format `qa_tools/common/delivery.py`
writes and reads, and the one delivery recognition (sprint 7) is built
against. It exists because Keith settled, 2026-09-22, that sprint 2
DEFINES the format sprint 7 consumes — *"it must be a DELIBERATE
ARTEFACT of this sprint... rather than something sprint 7
reverse-engineers"*. `REQ-GEN-043`.

## What a delivery is

**One physical arrival of one or more files.** Not an obligation, not a
period, not a dataset — those are a *slot*, and one slot may be filled
by several deliveries (`REQ-GEN-042`).

```
data/
  deliveries/
    BDM_20260824/                 <- one delivery. The directory IS the boundary.
      birth_registrations.csv
    dcp-extract-aug/              <- another. Six files, one arrival.
      cp_clients.csv
      cp_notifications.csv
      ...
  receipts/
    BDM_20260824.json             <- OURS. Outside every delivery.
    dcp-extract-aug.json
```

### The boundary is a directory, and it is observable without opening anything

One directory under `data/deliveries/` is one delivery. You can see
where a delivery starts and stops from a listing alone — no file needs
parsing to establish it.

This is what a real transport gives you: one S3 prefix, one SFTP
session, one folder drop. A format that could not be produced by one of
those would not be standing in for anything.

### The delivery asserts only what physically happened

These files landed together. That is the whole of it.

A delivery does **not** say which period it is for, which slot it
fills, or which dataset version it supersedes. Those are judgments we
would have to trust, and across a varied supplier base we cannot
enforce them. A folder drop is a fact we can see for ourselves.
`plans/supply-model.md` Thread B rejected the supplier-declared
manifest for exactly this reason, and nothing in this format is allowed
to reintroduce it by a back door.

So: **no code that files a supply may read a statement of intent from
inside a delivery.** If a supplier puts one there anyway, it is an
artefact to report, not a value to use.

## Delivery names mean nothing

A delivery directory's name is whatever the supplier called their drop.
`BDM_20260824`, `dcp-extract-aug`, `upload_final_v2`, `2026Q3`, a bare
UUID — all equally valid, and none of them parseable.

This is deliberate, and the reason is a testing argument rather than a
modelling one. **If we name the drop ourselves, delivery recognition
passes by parsing a name we wrote, which proves nothing.** Leaving the
name arbitrary makes recognition do real work against a boundary it did
not choose. The generator is therefore *required* to emit names
following no common pattern (`REQ-GEN-043` criterion 15).

Nothing may derive the receipt time, the period, the dataset or the
ordering from a delivery's name.

## Files are named so their dataset is derivable

A file's name is the one thing inside a delivery that carries meaning,
and only through each dataset's **own configured pattern** — the
`arrivalPattern` block in that dataset's ODCS contract, matched by
`qa_tools/common/file_arrival.py`.

A file matching no pattern is not an error in the format. It is a real
thing suppliers do (a `readme.txt`, a spreadsheet of notes, a PDF), and
the pipeline has to have somewhere to put it. It is reported, not
swallowed.

Three shapes a delivery may legitimately contain, all of which the
generator can emit on purpose so recognition is tested against them:

| Shape | Example | Why it exists |
|---|---|---|
| Two files matching one dataset's pattern | `cp_clients.csv`, `cp_clients_part2.csv` | Suppliers split large extracts |
| A file matching no pattern | `readme.txt`, `notes.pdf` | Suppliers include covering notes |
| A file unparseable as the format its name claims | a `.csv` holding HTML | Truncated uploads, error pages saved as data |

**Legitimate to RECEIVE is not the same as processed unattended**, and
the first row is where the two part company. A delivery carrying two
files for one dataset is HELD for a human every time - `REQ-PIPE-059`,
Keith's call 2026-09-24 - because nothing here can tell a split extract
apart from a duplicate, a wrong file or two periods of the same table,
and every rule for choosing between them drops a file the supplier will
later say they sent.

Assembling split extracts properly, and the related shape where a
dataset arrives as add/update/delete DELTA files, are both deliberately
out of scope for this PoC. See `plans/running-thoughts.md` #39 and #40.

## The receipt record is ours

```json
{
  "delivery": "BDM_20260824",
  "received_at": "2026-08-24T14:36:03.084997+08:00"
}
```

One file per delivery, at `data/receipts/<delivery name>.json`.

**Three rules, and they are all the same rule seen from different
angles.**

1. **It lives OUTSIDE the delivery**, in a directory the supplier has no
   path to write to. The delivery area is theirs; the receipt area is
   ours.
2. **We ignore any timestamp a supplier could have written** — a column
   in their data, a field in a file they included, a file modification
   time. Only the instant recorded on our side of the boundary counts.
3. **A file inside a delivery that looks like a receipt record is an
   anomaly**, reported and never read. The moment the receipt time
   lives in a file rather than somewhere only we control, a supplier
   writing a file of that name would be setting our own clock.

`received_at` always carries its UTC offset (`REQ-PIPE-048`). It is the
only timestamp in this format.

### It is simulated, and that is stated rather than hidden

A generated history spans years but is written in seconds, so a real
file modification time would collapse every arrival onto one instant
and destroy every injected scenario. The receipt instant is therefore
**supplied by the generator standing in for the transport layer**, not
read from the filesystem.

This is the one place the synthetic stand-in genuinely cannot be a
filesystem fact. In a real deployment it is object metadata the
transport records at the moment of upload. Labelled here rather than
quietly relied upon.

## The generator's bookkeeping is not part of the format

The generator knows things no supplier would tell us: which scenario a
delivery came from, which slot it was built to fill, what row counts it
injected. That is real and worth keeping — it is how a test asserts
that recognition got the right answer.

It lives in **`data/generator_bookkeeping.json`**, outside every
delivery, and it is subject to one hard rule:

> **No pipeline, QA or dashboard-build module may read it, and no part
> of it may be embedded into committed `qa_results/`.**

A pipeline that reads it is making filing decisions from a declaration
rather than from arrival plus slot state — which is the rejected
supplier manifest wearing our own badge. Tests may read it. Nothing
that files a supply may.

## What stays out

- **Nothing here is committed to git.** `data/` is gitignored and stays
  that way. In a real deployment this directory holds real Birth
  Registrations and Child Protection extracts, and no part of this
  format may require committing a delivery's contents.
- **No character that is illegal or awkward in a path on a non-Linux
  filesystem.** This repo gets run on other people's machines, and an
  ISO-8601 instant contains colons — which is one of the reasons the
  receipt instant is in a file rather than a directory name.
- **Everything that reads a delivery is invoked through `mothman`.**
