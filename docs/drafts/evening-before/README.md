# REQ-GEN-044's evening-before era: built, then shelved

Built overnight 2026-10-15/16 and reverted the same night (revert 61c8d04 of
4e73be1). `evening-before.patch` is the whole change, ready to re-apply with
`git apply` once the blocker below is settled.

## What it does

- Birth Registrations grows twelve days at its OLD end (2026-06-18 to
  2026-06-29), generated AFTER the 85 with seeds of their own
  (`GROWN_DAYS = 12`, `GROWN_BASE_SEED = 40000`), exactly as REQ-GEN-207 grew
  Child Protection. **Byte proof from empty: all 449 existing deliveries
  identical, 12 new.**
- A daily calendar version and a Birth Registrations participation version
  effective 2026-06-18: due 22:00 the evening before (`days_before: 1`), 1h
  grace, 4h claim window.
- TS-3c (Monday 2026-06-22, a 17:00 resupply an hour before the next day's
  window), TS-3d (19 hours late), TS-10a (22:00 the evening before, the day
  before filled) and TS-10b (the same, the day before empty). The register's
  TS-10 splits into TS-10a/TS-10b.
- The era's ordinary days are clean, one on-time supply at 21:00 the evening
  before (PROVISIONAL: a red's resends would land on a scenario's day).
- `check_suppressed_days_are_empty` judges a daily dataset's suppressed day by
  its CLAIM WINDOW rather than the calendar day of receipt, since an
  evening-before supply arrives on the previous calendar day.

## Why it is shelved: two built rules refuse the configuration

The 2026-06-30 participation version omits `days_before`, which the new
version before it states as 1, so `mothman schedule validate` refuses it:
"leaves out days_before ... Restate each value on this version". Restating
`days_before: 0` there is then refused by the agreement freeze (the version
froze at 2026-06-30 and only a declared correction may change it), and every
later version needs the same restatement in turn. A declared correction would
be staged by the replay and shown as "awaiting confirmation" across the
history - not what the scenario is for.

**For Keith** - which of these?

1. Teach both rules that a value equal to its default is the same as leaving
   it out: the freeze sees no change in restating `days_before: 0`, and the
   restatement rule accepts an omission after a version whose value was the
   default. A small change to REQ-PIPE-110/111 behaviour (needs your wording).
2. Widen REQ-PIPE-111 criterion 9's synthetic exemption to "restating a
   frozen version's value at its default".
3. Put the evening-before era somewhere it is the LATEST era instead (it
   would have to be the newest days, which moves the scenarios' outcomes'
   configuration into today's supplies).
4. Leave TS-3c/3d/10 as unit-tested only.
