"""The set-member checks the collections' dbt schema files DECLARE, and the
gates over those declarations (REQ-QAC-297 criterion 13; REQ-QAC-300 criteria
5 and 7) - split out of qa_tools/common/list_setting_members.py by
REQ-PIPE-380 criterion 2.

THE OTHER HALF, qa_tools/common/list_setting_members.py, writes the declared
set in force for a run's period into the run's view schema and reads it back,
which takes a connection. The cut sits there: these declarations are
configuration, which the generator reads to plan a geocoding file, and
asset_model/ opens no connection.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType

from asset_model import config_yaml

REPO = Path(__file__).resolve().parent.parent


#: The three set-member generic tests (dbt_project/tests/generic/), by the
#: kind of violation each counts.
TESTS = ("missing_set_members", "duplicated_set_members", "unexpected_set_members")


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


#: Each dbt schema file's set-member checks, keyed on the file's path, the
#: tables asked about, and the file's text as read on this call
#: (REQ-PIPE-401, REQ-PIPE-254): bounded and behind a lock, as the other
#: content-keyed stores are.
_SCHEMAS = config_yaml.Built()


def declared(root: Path = REPO) -> list[SetMemberCheck]:
    """Every set-member check the collections' dbt schema files declare.

    EACH FILE IS READ ON EVERY CALL and its checks built once per version of
    its text. declared() is asked for every geocoding file the generator
    writes (through member_setting_of), and re-parsing every schema file each
    time was 84% of a Linkage Products generation (post-build-review #318);
    #318 remembered the parse by the file's mtime and size, which a same-size
    edit inside one clock tick keeps, so it could answer for what the file
    used to say. REQ-PIPE-254 criterion 15 forbids that, and REQ-PIPE-401
    keyed it on the content instead."""
    from asset_model import collections

    out = []
    for coll in collections.all_collections():
        path = root / coll.dbt_schema
        if not path.is_file():
            continue
        tables = tuple(sorted((d.table, d.dataset_id) for d in coll.datasets))
        text = config_yaml.read(path)
        out.extend(_SCHEMAS.get((str(path), tables), text,
                                lambda: _build_checks(path, text, dict(tables))))
    return out


def _freeze(value):
    """A stored value is shared between callers (config_yaml.Built), so what
    a check carries from the file is made immutable."""
    if isinstance(value, dict):
        return MappingProxyType({k: _freeze(v) for k, v in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(v) for v in value)
    return value


def _build_checks(path: Path, text: str, tables: dict) -> tuple[SetMemberCheck, ...]:
    """The set-member checks one schema file's text declares, for the tables
    its collection holds - from the one read declared() made."""
    doc = config_yaml.parse(text, name=str(path)) or {}
    out = []
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
                        changelog=_freeze(list(meta.get("changelog") or ()))))
    return tuple(out)


def problems(root: Path = REPO) -> list[str]:
    """Each gate's refusals, naming the dataset, the check or the period."""
    from asset_model import amber_setting, linked_datasets

    doc = amber_setting.load_doc(linked_datasets.asset_folder(root) / "data-asset.yaml")
    checks = declared(root)
    return (_declaration_problems(checks, doc, root) + _coverage_problems(checks, doc)
            + _breaking_entry_problems(checks, doc))


def _declaration_problems(checks, doc, root) -> list[str]:
    """REQ-QAC-297 criterion 13: every set-member check has key columns, a
    member column and a member_setting naming a declared list setting; and a
    GEOCODING DATASET - a linked product with one source and no code
    (REQ-QAC-294 decision 8) - has all three set-member checks, a value-share
    check and both identifier checks."""
    from asset_model import amber_setting, linked_datasets

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
    asset = config_yaml.load(linked_datasets.asset_folder(root) / "data-asset.yaml") or {}
    for _agency, coll, ds in linked_datasets.walk(asset):
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
    from asset_model import linked_datasets

    folder, _, name = str(coll.get("contract", "")).rpartition("/")
    stem = name.removesuffix("-contract.yaml")
    return linked_datasets.soda_bodies(linked_datasets.asset_folder(root) / folder / f"{stem}-soda-checks.yml",
                                        ds.get("table"))


def _coverage_problems(checks, doc) -> list[str]:
    """REQ-QAC-300 criterion 5: no period a reader of a list setting owes may
    lack a version - refused, naming the dataset and the period, never
    answered by the nearest version."""
    from asset_model import amber_setting, schedule

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
    from asset_model import amber_setting

    out = []
    for c in checks:
        if not c.member_setting:
            continue
        key = (amber_setting.LIST_SETTINGS, c.member_setting)
        line = amber_setting.timeline(c.dataset_id, doc=doc, key=key)
        dated = {str(e.get("date", ""))[:10] for e in c.changelog
                 if isinstance(e, Mapping) and e.get("breaking") is True}
        for before, after in zip(line, line[1:]):
            if before["value"] != after["value"] and after["from"] not in dated:
                out.append(f"check {c.check_id} has no breaking changelog entry dated "
                           f"{after['from']} for the version of {c.member_setting} it "
                           f"changes to (REQ-QAC-300 criterion 7).")
    return out
