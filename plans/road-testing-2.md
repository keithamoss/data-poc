# Road testing, part 2

A second road-testing file, started 2026-11-13 at Keith's ask ("these
should both be in a NEW road testing part 2 file"), for what turns up when
the QA checks themselves are looked at the way a data engineer would use
them. Same kind of entry as `plans/road-testing.md`: a SIGHTING, written
down before it is diagnosed, then played back and investigated. Same
conventions: a closed status, one or more component tags, a date (the day
it was raised, unchanged when its status moves), and a feedback card
straight after each entry's title line.

READ BY THE FEEDBACK GATE AND THE DASHBOARD'S FEEDBACK TAB, like the first
file (Keith, 2026-11-14): both read every `plans/road-testing*.md`
(`dashboard/plans_md.py`'s `feedback_files`), so every entry here carries a
card the gate checks, and a card error names this file. The introduction's
sprint list stays in the first file only. The Plans tab and `plans/INDEX.md`
read this file as they read every plans file.

Anything here that becomes real build work becomes a requirement in
`requirements.yaml`, and the entry's prose comes out when it lands; its
card stays.

1. **[investigate, 2026-11-13]** **[QA checks & contract]** **Type-driven drift detection on every column, and ad hoc drift within a period.**

- **You told us:** From time to time you need drift checked between supplies in the same period, and drift should be easy to turn on for every column, with the method following the column's type.
- **What we heard:** One generic drift framework that knows each column's kind and picks the method from it, used by the pipeline against the last promoted supply and by a person running a report by hand for supplies within a period.

     Keith, 2026-11-13 (dictated); played back the same day, and Keith
     chose on 2026-11-14 not to answer the questions yet. Two uses of ONE
     generic framework:
     - **In the pipeline**: drift between a supply and the previous promoted
       supply (the previous period), as today - but over all (or nearly all)
       columns, table-level measures too (row counts and the like), with the
       method chosen from each column's kind (numeric, categorical, date,
       free text, code, identifier), so enabling it is a small piece of
       configuration per dataset rather than a hand-written check per column.
     - **Ad hoc, from time to time**: drift between supplies WITHIN one
       period slot - not yet known whether against the previous supply in
       the period (resupply 2 against 1, 5 against 4) or against the period's
       first supply. Probably not in the pipeline at all: a person reruns a
       QA report by hand on their laptop and reads a local HTML report. Keep
       the pipeline simple; ad hoc things are humans running commands.
     - **What exists, played back the same day**: it is NOT easy today. Drift
       is six hand-authored Evidently PSI checks, categorical only, one
       column each (sex, concern_type, triage_category, age_group,
       match_level twice), each with its own id, bands, prose and changelog.
       No numeric or date drift. Column kinds are declared nowhere a
       framework could read them - the contracts say only date or string,
       and the one categorical/numeric notion is the collection adapter's
       hand-listed stats spec (three columns for Child Protection). The drift
       reference is built from recorded value counts, recorded only for
       listed columns. Right already: the reference is the last promoted
       supply (REQ-QAC-108), and row counts have a row_drop check on every
       dataset.
     - **Questions put to Keith**: (1) where a column's kind lives -
       recommended the ODCS contract, per column; (2) one drift check per
       dataset with a per-column breakdown and per-kind default bands
       (recommended) or one generated check per column; (3) previous or first
       supply for ad hoc - recommended a choice on the command, defaulting to
       previous; (4) the ad hoc run records nothing - recommended a local
       Evidently HTML report only.

2. **[investigate, 2026-11-13]** **[QA checks & contract]** **Date columns: report the full range, and surface the outliers inside it.**

- **You told us:** A date column should show its whole range, and pick out the few odd records inside it - ten records in 1964 when the series starts in the early 1990s - as part of its check.
- **What we heard:** Every date column reports its full native range, and its check says how many rows fall below the expected start and above the expected end, so the stragglers are visible without the supply necessarily going red.

     Keith, 2026-11-13 (dictated); played back the same day, and Keith
     chose on 2026-11-14 not to answer the questions yet. He expected that a
     supply holding a few
     1964 records may not go red, because those rows fall outside the
     thresholds; what he wants is the report saying clearly how many rows
     fall below and above the threshold. "That gives us all we need."
     - **What exists, played back the same day**: no "series begins in 1990"
       check anywhere. The only date bounds are date of birth >= 1900-01-01
       (Birth Registrations also <= today), as dbt accepted_range, a Soda
       failed-rows check and a contract rule, each warn >10 / fail >20 ROWS.
       Child Protection's event dates (notification_date, case_opened_date,
       placement_start/end, start_date, end_date) have no range check at all.
       So ten 1964 rows pass on date of birth and go unseen on an event date;
       even under a 1990 floor ten rows would pass (warn is >10). The page's
       date aggregate shows min/max/histogram of the FAILING rows only, never
       the column's full range.
     - **Questions put to Keith**: (1) where a date column's expected start
       comes from - recommended declared per column in the contract, event
       dates defaulting to the dataset's first owed period; (2) whether rows
       outside change the status - recommended report the counts and warn on
       any, keeping fail for impossible dates; (3) record and show every date
       column's full range always - recommended yes, as the date kind's
       default in entry 1's framework.
