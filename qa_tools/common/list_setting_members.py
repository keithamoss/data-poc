"""The declared set in force for a run's period, as a relation in the run's own
view schema, and the gates over the checks that read it (REQ-QAC-297 criteria
3, 4 and 13; REQ-QAC-300 criteria 4, 5, 7 and 9).

GENERIC. A set-member check names a LIST SETTING (its member_setting), never a
set: the setting is resolved for each of the collection's datasets by the one
mechanism (asset_model/amber_setting.py), on the ROUND DATE of the round
whose slot fills the run's period (REQ-QAC-300 criterion 4), and written as
rows of one relation, RELATION, which the tests read through dbt's source().
Nothing here names a setting, a dataset or a collection.

BUILT WITH THE PERIOD'S VIEWS, NOT AT STAGING (REQ-QAC-297 criterion 3):
staging runs before filing, when the period is not known, so the relation is
written by period_overlay.rebuild_for_arrival's one build of the run's view
schema, and only there. A run filed to no period has no relation, and its
set-member checks are left out of the dbt selection and recorded not
evaluated (criterion 4) - never a pass, never a tool error.

NOT A TABLE ANY DATASET OWNS, so no check declares it in reads_tables
(REQ-PIPE-331 criterion 2's gate would refuse it); it is never passed through
dbt --vars, which re-parses every run.

THE DECLARATIONS ARE asset_model/set_member_checks.py (REQ-PIPE-380
criterion 2): which set-member checks the schema files declare, and the
gates over them, read configuration only, which the generator reads too.
Everything here takes a connection - writing and reading the relation in a
run's view schema - so it stays in the real pipeline.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta


#: The relation's name in a run's view schema, and the source() table the
#: set-member tests read.
RELATION = "list_setting_members"

#: The structured reason a set-member check records where its run has no
#: period (REQ-QAC-297 criterion 4).
NO_PERIOD = "declared-set-needs-period"
NO_PERIOD_REASON = ("The declared set this check compares against is the one in force for "
                    "the supply's period, and this supply is filed to no period, so there is "
                    "no set to compare it with. This check did not fail - it could not be "
                    "evaluated.")


#: A TRIAL'S reason (post-build-review #299 item 3): a staged-only trial is
#: filed to no period by design and decides nothing, so its set-member checks
#: are recorded no data, as every check a trial cannot evaluate is.
TRIAL_NO_PERIOD = "declared-set-not-in-trial"
TRIAL_NO_PERIOD_REASON = ("A trial is checked without being filed, so no period - and no "
                          "declared set in force for one - applies to it, and this check "
                          "was not run. It did not fail; a trial decides nothing.")


@dataclass(frozen=True)
class InForce:
    """A list setting as it stood for one table in one period."""

    setting: str
    members: tuple
    version: str          # the effective_from of the version in force
    added: tuple          # the members it added to the version before it

    def as_record(self) -> dict:
        """What a set-member check's result carries (REQ-QAC-300 criterion 9),
        so the page shows the set without re-resolving configuration."""
        return {"member_setting": self.setting, "member_set_version": self.version,
                "member_set": list(self.members), "member_set_added": list(self.added)}


def _round_date(dataset_id: str, period: str) -> date | None:
    from asset_model import schedule

    try:
        found = next((p for p in schedule.periods_for_dataset(dataset_id) if p.name == period),
                     None)
    except (schedule.ScheduleConfigError, LookupError, ValueError,
            # NO CALENDAR, NO ROUND (REQ-PIPE-434): a not-yet-agreed dataset
            # beside a calendared one is in no period's overlay (REQ-TEST-437
            # criterion 5's test).
            schedule.NoCalendarAgreed):
        return None
    return found.round_date if found is not None else None


def in_force(dataset_id: str, period: str, *, doc: dict | None = None) -> list[InForce]:
    """Every list setting resolved for a dataset on its period's round date,
    with the members its version added to the one before it (none for the
    first). Empty where the dataset does not owe the period."""
    from asset_model import amber_setting

    doc = doc if doc is not None else amber_setting.load_doc()
    on = _round_date(dataset_id, period)
    if on is None:
        return []
    out = []
    for key in amber_setting.list_setting_keys(doc):
        r = amber_setting.resolve_on_date(dataset_id, on, doc=doc, key=key)
        if r is None:
            continue
        before = amber_setting.resolve_on_date(
            dataset_id, date.fromisoformat(r.version) - timedelta(days=1), doc=doc, key=key)
        added = () if before is None else tuple(m for m in r.value if m not in before.value)
        out.append(InForce(setting=key[-1], members=tuple(r.value), version=r.version,
                           added=added))
    return out


def rows_for(tables, period: str, *, doc: dict | None = None) -> list[tuple]:
    """(table_name, setting, ordinal, member, version, added) for every list
    setting in force for each table's dataset in `period`."""
    from asset_model import hierarchy

    rows = []
    for table in tables:
        try:
            dataset_id = hierarchy.dataset_for_table(table).dataset_id
        except Exception:  # noqa: BLE001 - a table no dataset owns has no setting
            continue
        for s in in_force(dataset_id, period, doc=doc):
            for i, m in enumerate(s.members):
                rows.append((table, s.setting, i + 1, str(m), s.version, m in s.added))
    return rows


def create(conn, run_schema: str, rows: list[tuple]) -> None:
    """The relation, as a view of literal rows in the run's own schema."""
    body = ("SELECT * FROM (VALUES " + ", ".join(
        "(%s, %s, %d, %s, %s, %s)" % (_lit(t), _lit(s), i, _lit(m), _lit(v), "TRUE" if a else "FALSE")
        for t, s, i, m, v, a in rows) + ") AS v(table_name, setting, ordinal, member, version, added)"
        if rows else
        "SELECT NULL::text AS table_name, NULL::text AS setting, NULL::int AS ordinal, "
        "NULL::text AS member, NULL::text AS version, NULL::boolean AS added WHERE FALSE")
    conn.execute(f'CREATE OR REPLACE VIEW "{run_schema}".{RELATION} AS {body}')


def _lit(value: str) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def exists(conn, run_schema: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM information_schema.tables WHERE table_schema = ? AND table_name = ?",
        [run_schema, RELATION]).fetchone() is not None


def read(conn, run_schema: str, table: str, setting: str) -> InForce | None:
    """The set as the run's relation holds it for one table - what a result
    records, read from the same rows the check compared against."""
    rows = conn.execute(
        f'SELECT member, version, added FROM "{run_schema}".{RELATION} '
        "WHERE table_name = ? AND setting = ? ORDER BY ordinal", [table, setting]).fetchall()
    if not rows:
        return None
    return InForce(setting=setting, members=tuple(r[0] for r in rows), version=rows[0][1],
                   added=tuple(r[0] for r in rows if r[2]))
