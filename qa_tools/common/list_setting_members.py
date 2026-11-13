"""The declared set in force for a run's period, as a relation in the run's own
view schema, and the gates over the checks that read it (REQ-QAC-297 criteria
3, 4 and 13; REQ-QAC-300 criteria 4, 5, 7 and 9).

GENERIC. A set-member check names a LIST SETTING (its member_setting), never a
set: the setting is resolved for each of the collection's datasets by the one
mechanism (qa_tools/common/amber_setting.py), on the ROUND DATE of the round
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
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parent.parent.parent

#: The relation's name in a run's view schema, and the source() table the
#: set-member tests read.
RELATION = "list_setting_members"

#: The three set-member generic tests (dbt_project/tests/generic/), by the
#: kind of violation each counts.
TESTS = ("missing_set_members", "duplicated_set_members", "unexpected_set_members")

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
    from qa_tools.common import schedule

    try:
        found = next((p for p in schedule.periods_for_dataset(dataset_id) if p.name == period),
                     None)
    except (schedule.ScheduleConfigError, LookupError, ValueError):
        return None
    return found.round_date if found is not None else None


def in_force(dataset_id: str, period: str, *, doc: dict | None = None) -> list[InForce]:
    """Every list setting resolved for a dataset on its period's round date,
    with the members its version added to the one before it (none for the
    first). Empty where the dataset does not owe the period."""
    from qa_tools.common import amber_setting

    doc = doc if doc is not None else amber_setting._doc()
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
    from qa_tools.common import hierarchy

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


# ---- the gates (REQ-QAC-297 criterion 13; REQ-QAC-300 criteria 5 and 7) ----

@dataclass(frozen=True)
class SetMemberCheck:
    dataset_id: str
    test: str
    check_id: str | None
    key_columns: tuple
    column: str | None
    member_setting: str | None
    changelog: tuple


#: A dbt schema file's (path, mtime_ns, size) -> its parsed document.
_SCHEMAS: dict = {}


def _schema(path: Path) -> dict:
    """A dbt schema file, parsed once per version of it. declared() is asked
    for every geocoding file the generator writes (through
    member_setting_of), and re-parsing every schema file each time was 84% of
    a Linkage Products generation (post-build-review #318). Keyed by the
    file's stat, so an edited file - or a test's copy - is read afresh. Read,
    never mutated, by declared()."""
    stat = path.stat()
    key = (str(path), stat.st_mtime_ns, stat.st_size)
    if key not in _SCHEMAS:
        _SCHEMAS[key] = yaml.safe_load(path.read_text()) or {}
    return _SCHEMAS[key]


def declared(root: Path = REPO) -> list[SetMemberCheck]:
    """Every set-member check the collections' dbt schema files declare."""
    from qa_tools import collections

    out = []
    for coll in collections.all_collections():
        path = root / coll.dbt_schema
        if not path.is_file():
            continue
        doc = _schema(path)
        tables = {d.table: d.dataset_id for d in coll.datasets}
        for model in doc.get("models") or []:
            table = str(model.get("name", "")).removeprefix("stg_")
            if table not in tables:
                continue
            for column in model.get("columns") or []:
                for test in column.get("tests") or column.get("data_tests") or []:
                    if not isinstance(test, dict):
                        continue
                    for name, body in test.items():
                        if name not in TESTS:
                            continue
                        body = body or {}
                        args = body.get("arguments") or body
                        meta = body.get("meta") or {}
                        out.append(SetMemberCheck(
                            dataset_id=tables[table], test=name, check_id=meta.get("check_id"),
                            key_columns=tuple(args.get("key_columns") or ()),
                            column=column.get("name"),
                            member_setting=args.get("member_setting"),
                            changelog=tuple(meta.get("changelog") or ())))
    return out


def problems(root: Path = REPO) -> list[str]:
    """Each gate's refusals, naming the dataset, the check or the period."""
    from qa_tools.common import amber_setting, linked_datasets

    doc = amber_setting._doc(linked_datasets._asset_folder(root) / "data-asset.yaml")
    checks = declared(root)
    return (_declaration_problems(checks, doc, root) + _coverage_problems(checks, doc)
            + _breaking_entry_problems(checks, doc))


def _declaration_problems(checks, doc, root) -> list[str]:
    """REQ-QAC-297 criterion 13: every set-member check has key columns, a
    member column and a member_setting naming a declared list setting; and a
    GEOCODING DATASET - a linked product with one source and no code
    (REQ-QAC-294 decision 8) - has all three set-member checks, a value-share
    check and both identifier checks."""
    from qa_tools.common import amber_setting, linked_datasets

    names = {k[-1] for k in amber_setting.list_setting_keys(doc)}
    out = []
    for c in checks:
        if not c.key_columns:
            out.append(f"{c.dataset_id}: {c.test} declares no key columns.")
        if not c.column:
            out.append(f"{c.dataset_id}: {c.test} declares no member column.")
        if c.member_setting not in names:
            out.append(f"{c.dataset_id}: {c.test} names the member_setting "
                       f"{c.member_setting!r}, which is no declared list setting.")
    have = {(c.dataset_id, c.test) for c in checks}
    asset = yaml.safe_load((linked_datasets._asset_folder(root) / "data-asset.yaml").read_text()) or {}
    for _agency, coll, ds in linked_datasets._walk(asset):
        linked = ds.get("linked_datasets") or []
        if len(linked) != 1 or linked[0].get("code") is not None:
            continue
        did = ds.get("id")
        missing = [t for t in TESTS if (did, t) not in have]
        tails = {cid.rsplit(".", 1)[-1] for cid, _a, _b in _soda_checks(root, coll, ds)}
        for kind in ("value_share_soda", "expected_ids_soda", "no_surplus_ids_soda"):
            if kind not in tails:
                missing.append(kind)
        if missing:
            out.append(f"{did} is a geocoding dataset without {', '.join(missing)} "
                       f"(REQ-QAC-297 criterion 13).")
    return out


def _soda_checks(root, coll, ds):
    from qa_tools.common import linked_datasets

    folder, _, name = str(coll.get("contract", "")).rpartition("/")
    stem = name.removesuffix("-contract.yaml")
    return linked_datasets._soda_bodies(linked_datasets._asset_folder(root) / folder / f"{stem}-soda-checks.yml",
                                        ds.get("table"))


def _coverage_problems(checks, doc) -> list[str]:
    """REQ-QAC-300 criterion 5: no period a reader of a list setting owes may
    lack a version - refused, naming the dataset and the period, never
    answered by the nearest version."""
    from qa_tools.common import amber_setting, schedule

    out = []
    for dataset_id, setting in sorted({(c.dataset_id, c.member_setting) for c in checks
                                       if c.member_setting}):
        try:
            periods = [p for p in schedule.periods_for_dataset(dataset_id) if p.expected]
        except (schedule.ScheduleConfigError, LookupError, ValueError):
            continue
        for p in periods:
            if amber_setting.resolve_on_date(dataset_id, p.round_date, doc=doc,
                                             key=(amber_setting.LIST_SETTINGS, setting)) is None:
                out.append(f"{dataset_id} owes {p.name} (round {p.round_date.isoformat()}), "
                           f"which no version of {setting} covers (REQ-QAC-300 criterion 5).")
                break
    return out


def _breaking_entry_problems(checks, doc) -> list[str]:
    """REQ-QAC-300 criterion 7: each version that changes a set needs a
    breaking changelog entry, dated its effective_from, on every set-member
    check whose set it changes - the set is no part of a check's definition
    fingerprint, so no other gate would notice."""
    from qa_tools.common import amber_setting

    out = []
    for c in checks:
        if not c.member_setting:
            continue
        key = (amber_setting.LIST_SETTINGS, c.member_setting)
        line = amber_setting.timeline(c.dataset_id, doc=doc, key=key)
        dated = {str(e.get("date", ""))[:10] for e in c.changelog
                 if isinstance(e, dict) and e.get("breaking") is True}
        for before, after in zip(line, line[1:]):
            if before["value"] != after["value"] and after["from"] not in dated:
                out.append(f"check {c.check_id} has no breaking changelog entry dated "
                           f"{after['from']} for the version of {c.member_setting} it "
                           f"changes to (REQ-QAC-300 criterion 7).")
    return out
