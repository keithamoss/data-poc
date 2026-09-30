# Supply thoughts - the transport layer, not yet scoped

A capture buffer for questions about **how a supply physically gets to
us**, opened 2026-10-01 at Keith's own ask after a long conversation
about REQ-PIPE-077 kept running into them. Everything here is a
question or a sketch; nothing in it is agreed, and nothing should be
built from it without going through `delivery-scoper` and a sign-off
the way any other requirement does.

**How this differs from the other buffers**, since there are now three
and a fourth would be a mess rather than a filing system:

- `plans/running-thoughts.md` is Keith's own forward-looking ideas,
  landed in a batch and not yet scoped - ticketing, gamification, an
  AWS MVP. Where an idea came from HIM, unprompted, it goes there.
- `plans/road-testing.md` is what turns up while USING the dashboard or
  the CLI. A sighting rather than a diagnosis.
- **This file** is the transport layer specifically: what a delivery
  IS, what carries it, what signals its boundaries, where it lands and
  where it goes afterwards. It exists because `plans/supply-model.md`
  is about the LIFECYCLE of a supply once we have it - arrival
  classification, filing, promotion, the decision log - and that file
  is already very large. This is the layer underneath it.

A thing here graduates by becoming a requirement, at which point the
entry is deleted rather than marked done - the standing rule in
CLAUDE.md, and the reason `decisions:` exists on a requirement.

---

0. **[todo, 2026-10-01]** **[Docs & process]** The open threads from
   the 2026-09-30 conversation, written down so they survive the
   session that produced them.

   Not design work - a register of what is genuinely waiting, because
   several of these are decisions only Keith can make and they were
   accumulating in chat.

   **Waiting on Keith, and blocking:**
   - **`REQ-PIPE-077`: whole delivery, or just the off-cycle supply?**
     Criterion 1 as signed withholds EVERY supply in a spanning
     delivery. In the partial-participation case that means five
     healthy quarterly tables wait on a person because one
     semi-annual table rode along. His own words were that the
     off-cycle DATASET needs a human decision; whether that extends to
     its five siblings is unanswered, and it is a change to a signed
     criterion either way. Possibly two different conditions wearing
     one gate.
   - **`REQ-PIPE-079` risk call.** Swapping `borrow_views()` for
     `create_overlay_views()` changes what every CP cross-table check
     reads, so recorded verdicts will move. Happy for them to shift,
     or want a before/after comparison first?
   - **`REQ-PIPE-079` vs `REQ-PIPE-105` criterion 5 - a live
     contradiction between two SIGNED requirements.** 079 criterion 10
     says a run overlays only the tables of the delivery under test
     and draws in no staged supply belonging to another delivery. 105
     criterion 5 says read the one version staged for the PERIOD. 105
     is signed later and is explicitly about this unit, but its
     criterion 9 names `REQ-PIPE-035` and `036` for amendment and NOT
     079 - so that amendment is a consequence nobody wrote down. These
     two have to be decided together.
   - **`REQ-PIPE-110`-`113`** remain unsigned, 64 criteria, and
     `REQ-GEN-044` criteria 8-11 wait on them.

   **Recorded, not blocking:**
   - `REQ-PIPE-077`'s **blind spot**: the catch-up drop it exists to
     catch trips it only while the older period is unfilled AND not
     closed by monotonic filling. Once that period is filled - the
     commoner case - the older table files into the current period as
     a resupply and nothing notices. A limit of the signed criteria,
     not a build defect.
   - `REQ-PIPE-115` (an unreadable table is red and never stops the
     run) is drafted, unsigned, parked pending research, and has NOT
     been through `delivery-scoper`.
   - `REQ-PIPE-078` criteria 9 and 10 are now 115's.
   - `plans/data-generation.md` #11 - the generator ignores
     `delivery_months`, so the synthetic corpus contradicts its own
     configured participation.
   - CI speed-ups, deferred by Keith to "later today" on 2026-09-30
     and not picked up.

1. **[investigate, 2026-10-01]** **[Pipeline & publishing]** What IS a
   delivery, now that the answer has moved twice?

   **Today** it is a directory. `delivery.py`'s own spec: "A DELIVERY
   IS ONE PHYSICAL ARRIVAL of one or more files, and one directory
   under `data/deliveries/` is one delivery. The boundary is the
   directory, observable from a listing without opening anything -
   which is what a real transport gives you: one S3 prefix, one SFTP
   session, one folder drop." One receipt instant per delivery, ours,
   recorded outside the delivery so a supplier cannot set our clock.

   **`REQ-PIPE-105` replaces that with the file**, and drops
   delivery-level completeness rather than replacing it - nothing
   waits for a folder to be finished, because nothing can know when it
   is. Four alternatives are recorded as rejected there: a
   supplier-written marker, the DynamoDB arrival counter (built and
   tested, then discarded), a quiet period, and a deadline backstop.

   **What is unresolved is what the word then MEANS.** Three things
   currently lean on it and each would need re-pointing: the receipt
   (one per delivery today, one per file after), `REQ-PIPE-059`'s hold
   (defined "within ONE arrival", which may become unreachable - see
   `REQ-PIPE-105`'s own open questions), and `REQ-PIPE-077`'s
   mixed-period gate (whose whole premise is that a delivery is a unit
   that can span periods).

   Worth deciding explicitly rather than by accident: is "delivery"
   retired as a concept, or does it survive as a *grouping* that
   carries no completeness claim - a label on a set of arrivals rather
   than a thing that has to be finished?

2. **[todo, 2026-10-01]** **[Pipeline & publishing]** Zip file support.

   **Nothing in this system understands an archive.** Checked
   2026-09-30: neither `docs/delivery-format.md`,
   `contract/data-asset.yaml`, `delivery.py` nor
   `arrival_patterns.py` mentions zip, tar or any container, and every
   arrival pattern matches a bare `.csv`. A zip arriving today matches
   no dataset and is reported as an unrecognised artefact - which is
   at least honest, but it is not support.

   **Why it is more interesting than a format convenience.** A zip is
   the one thing that gives an atomic multi-file boundary a transport
   can actually guarantee: our storage either took the object or it
   did not, so "the whole package arrived" needs no signal, no
   counter and no timeout. It is `REQ-PIPE-105`'s completeness problem
   solved by the supplier's own packaging rather than by us inferring
   anything. It also restores a case for `REQ-PIPE-059`'s hold, which
   may otherwise have no producer once every file is its own arrival.

   **Questions to settle**: whether the zip or its members get the
   receipt instant; whether a member is an arrival or the zip is;
   whether the arrival patterns match member names, the archive name,
   or both; what happens to a zip carrying files for two collections
   (a delivery may already span collections, settled 2026-09-24); and
   the security surface, which is real - zip bombs, path traversal on
   extraction, and a member whose name is potentially identifying
   before anything is read.

3. **[investigate, 2026-10-01]** **[Pipeline & publishing]** An
   "upload beginning" / "upload complete" signal from suppliers who
   automate.

   **Keith's framing, 2026-10-01**: suppliers who automate their
   uploads could bracket a batch with signals either side - which he
   noted might just BE zipping the package, or might need to allow
   several files or zips between the two signals.

   **This reopens something `REQ-PIPE-105` explicitly rejected**, and
   the difference is worth being precise about rather than assuming it
   is either the same idea or a new one. What was rejected was a
   supplier-written COMPLETION MARKER, and the reason was an unbounded
   wait: a signal that never comes leaves a real supply sitting
   unQA'd, unreported, with nothing to say it is stuck. The DynamoDB
   counter was rejected for the identical failure one door along - a
   genuine five-of-six partial never completes.

   **A bracketed session is a different shape from a marker**, and
   might survive the same objection: an OPENING signal means we know a
   batch is in flight from the start, so a batch that never closes is
   VISIBLE rather than silent. That is the whole difference. The marker
   had no opening signal, so a delivery that never finished was
   indistinguishable from one that never started.

   **So the question is not "should suppliers signal" but "what do we
   do when the closing signal never arrives"** - and it has to be
   answered before this is worth building. A session that can be
   reported as open-and-stale is a queue item somebody drains; one
   that cannot is the same dead end under a new name. Note
   `in_flight_log` already reports a delivery present with no receipt
   record, which is a thin version of exactly this.

   **Also unresolved**: whether a session is per supplier, per
   collection or per asset; what an overlapping pair of sessions
   means; and whether the signals are files, API calls, or S3 object
   tags. Keith's own instinct that "it could just be a zip" is worth
   taking seriously as the cheap answer that needs no protocol at all.

4. **[todo, 2026-10-01]** **[Pipeline & publishing]** Data moving out
   of the place it was uploaded to.

   Today `data/deliveries/` accumulates and nothing ever removes it.
   CLAUDE.md already flags it, with `data/receipts/`, as arguably
   state that ought not live in the repository - `REQ-PIPE-104` and
   `REQ-PIPE-105` own the filing and receipt records, and the
   supplier's own files are the part with no home yet.

   **It has already bitten once.** Twenty-six `handfiled-*` directories
   left behind by a CLI test became REAL RUNS, two of them captured
   into a committed characterisation fixture - so a landing zone that
   nobody clears is not just untidy, it changes what the pipeline
   thinks arrived.

   **The real questions are retention and reach**, and they are
   governance rather than plumbing: does the raw supplier file survive
   staging at all, and for how long; who can read the landing zone
   once the data is in the warehouse; and what the answer is for a
   Child Protection extract specifically, where a FILENAME is
   potentially identifying before anything is opened (`arrivals.py`
   already states that rule for unmatched files).

   A separate, smaller thread: once a supply is promoted its staged
   table MOVES rather than being copied (`REQ-PIPE-075`), and the same
   reasoning arguably applies one layer up - the landing zone should
   empty as things are taken from it, rather than being swept on a
   schedule nobody remembers to run.

5. **[investigate, 2026-10-01]** **[QA checks & contract]** The
   cross-table flicker, if files arrive one by one.

   `REQ-PIPE-105`'s own NFR 1 already names it: during the minutes a
   delivery is landing, a viewer can see a cross-table check red for a
   table that has not arrived yet. Criterion 13 is what keeps it
   legible rather than merely loud, and `REQ-QAC-037` criterion 4
   re-evaluates a cross-table check whenever a dataset it reads
   receives an arrival, so the reds are transient by construction.

   **It is smaller than it first sounds**, and the correction is
   recorded on 105: because a run reads the one version staged for the
   PERIOD rather than only its own arrival, the run triggered by the
   last file of a six-file delivery sees all six and resolves
   normally, with nothing promoted at all.

   **What is left is a display question more than a pipeline one.**
   Options worth weighing: let it flicker and label the reason
   (criterion 13's line); render "not yet evaluated" as its own state
   rather than as red, which is REQ-PIPE-115's territory and probably
   the same mechanism; suppress re-evaluation until a batch is known
   complete, which needs #3 and inherits its unbounded-wait problem;
   or simply do not publish a dashboard build mid-batch, which is free
   and may be enough.

   The thing to avoid is stated already and is the reason this is not
   cosmetic: a dashboard red for reasons about our own timing rather
   than about the data is how people learn to ignore red.

6. **[investigate, 2026-10-01]** **[Pipeline & publishing]** Parquet
   support for uploads - and no, one file cannot hold several tables.

   **The direct answer to Keith's question**: a single Parquet file is
   ONE table - one schema, one set of row groups. There is no
   multi-table Parquet file. What people mean by "a Parquet dataset"
   is a DIRECTORY of files sharing a schema, usually partitioned,
   which is several files again rather than one. Formats that do hold
   several tables in one file are a different family: a DuckDB
   database file, SQLite, or HDF5 - and a zip of Parquets, which is
   #2 rather than this.

   **Worth wanting anyway**, for reasons that have nothing to do with
   bundling: the schema travels WITH the data, so column types stop
   being something the loader infers and gets wrong. This project has
   already been bitten by CSV's typelessness - `csv_io.py` exists to
   carry explicit nulls through a read, and the `"N/A"`-becomes-NULL
   bug is in this repo's own history. Parquet would make a whole class
   of that go away, and DuckDB reads it natively so the staging path
   would barely change.

   **What it would cost**: arrival patterns currently match `\.csv`;
   `dirty.py`'s injected defects assume text; and a supplier sending
   Parquet is asserting a schema, which raises an interesting question
   for the contract - is a file whose declared types disagree with the
   ODCS contract a failed load, or a check result? Probably the
   latter, and probably a good check to have.
