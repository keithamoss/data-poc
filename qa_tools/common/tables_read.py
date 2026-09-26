"""What a check read besides its own table (REQ-PIPE-036 criteria 10
and 11).

THE QUESTION THIS ANSWERS is asked a year later, by somebody looking at
a red referential-integrity check: which version of the OTHER table was
it red against? A check filed against cp_placements that reads
cp_carers is making a claim about two supplies, and the run-level
resolution record (REQ-PIPE-068 criterion 5) says what the RUN read -
not what this CHECK read. At ~30 datasets those are very different
lists.

DECLARED, NOT DERIVED, and the trade is deliberate. Deriving it means
four tool-specific parsers - a dbt `to: ref()`, a SodaCL "must exist
in" sentence, a contract SQL query, an Evidently dict - and a parser
that quietly returns nothing for a shape it did not expect produces a
check result that looks complete and names none of what it read. The
failure is silent and the result is wrong in the confident direction.
A missed DECLARATION has a gate: undeclared_cross_table() re-reads each
tool's own source and flags a check that looks cross-table and declares
nothing. A missed derivation has nobody.

WHAT IS RECORDED IS A NAME, NEVER A STATUS (criterion 11). The
temptation is obvious - a reader wanting to know whether cp_carers was
itself red would be saved a click - and it is the wrong shape twice
over. It would freeze another dataset's verdict into this check's
result, where it goes stale the moment that dataset is re-checked; and
it would make one dataset's results depend on another's, which is the
per-dataset independence this requirement's own story is about.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable, Mapping, Sequence

import yaml

ROOT = Path(__file__).resolve().parent.parent.parent

#: The key a check's result carries. Logical name -> physical table.
RESULT_FIELD = "tables_read"

#: Where a cross-table check's result is recorded (REQ-QAC-037
#: criterion 1): a RESERVED FOLDER at collection level, beside the
#: datasets rather than inside one of them -
#: qa_results/<agency>/<collection>/_cross-table/<run_id>/.
#:
#: A reserved NAME rather than a level of its own, so every child of a
#: collection is a scope and the tree stays readable: without it a
#: reader walking `<collection>/` cannot tell whether `cp-clients` is a
#: dataset or a run id. It also means nothing already committed has to
#: move, which is what makes this independent of REQ-PIPE-038's re-key.
CROSS_TABLE_SCOPE = "_cross-table"

#: What makes the name above safe to reserve. No dataset id may begin
#: with it, and that is enforced by the hierarchy gate rather than left
#: as a convention - a reserved name that is only reserved in a comment
#: is a name somebody eventually takes (Keith, 2026-09-26).
RESERVED_SCOPE_PREFIX = "_"


def is_reserved_scope(name: str) -> bool:
    """Whether this name belongs to the tool rather than to a dataset."""
    return bool(name) and name.startswith(RESERVED_SCOPE_PREFIX)


def declared_by_check_id(checks: Iterable) -> dict[str, list[str]]:
    """`check_id` -> the logical tables that check declares it reads.

    Only checks that declare any appear, so the common case - a check
    reading its own table and nothing else - costs nothing and is
    absent rather than present-and-empty. Criterion 10 asks for a
    record WHERE a check reads another table; there is nothing to say
    about the rest.
    """
    return {c.check_id: list(c.reads_tables) for c in checks if getattr(c, "reads_tables", None)}


def _own_table(dataset_id: str | None) -> str | None:
    """The physical table a dataset id names, or the id itself.

    Falling back to the id is right rather than lenient: a result from
    a dataset the tree no longer knows should still have its own table
    excluded where the two happen to coincide, and recording one extra
    name is a far smaller fault than raising in a results writer.
    """
    if not dataset_id:
        return None
    from qa_tools.common import hierarchy

    try:
        return hierarchy.dataset(dataset_id).table
    except Exception:  # noqa: BLE001 - see the docstring
        return dataset_id


def attach(results: Sequence[dict], resolved: Mapping[str, str],
            declared: Mapping[str, Sequence[str]]) -> list[dict]:
    """Record, with each check's own result, the PHYSICAL table name of
    every other table it read.

    `resolved` is the run's own resolution - logical name to the one
    physical table this run read for it. Taken from the run rather than
    looked up afresh, because "which version did this run read" is only
    an observed fact while that run's view schema exists.

    A DECLARED TABLE THE RUN COULD NOT RESOLVE IS RECORDED AS None
    rather than omitted. Omitting it would make "the check read one
    table" and "the check read one table and could not read another"
    identical in the record, and the second is the interesting one -
    it is the shape red-for-unrun exists for.
    """
    out = []
    for result in results:
        names = declared.get(result.get("check_id") or "")
        if not names:
            out.append(result)
            continue
        read = {name: resolved.get(name) for name in sorted(names)}
        # Its OWN table is not "another table it read", whether or not
        # somebody declared it. Criterion 10 is about the others.
        #
        # A RESULT CARRIES A DATASET ID AND A DECLARATION CARRIES A
        # TABLE NAME, and they are not the same string - "cp-placements"
        # against "cp_placements". Comparing them directly silently
        # never matched, so a check that declared its own table
        # recorded itself as something it read. Found by a test that
        # declared both.
        read.pop(_own_table(result.get("dataset_id")), None)
        out.append({**result, RESULT_FIELD: read} if read else result)
    return out


# --------------------------------------------------------------------
# The gate (what makes declaring safe)
# --------------------------------------------------------------------

#: How each tool writes "this check reads another table". Crude on
#: purpose: a false positive costs an author one declaration, and a
#: false negative costs a silently incomplete record.
_DBT_CROSS_TABLE = "relationships"
_SODA_CROSS_TABLE = re.compile(r"must exist in\s+(\w+)", re.I)


def _known_tables() -> set[str]:
    from qa_tools.common import hierarchy

    return {d.table for d in hierarchy.all_datasets()}


def _yaml(path: Path):
    try:
        return yaml.safe_load(path.read_text()) or {}
    except (OSError, yaml.YAMLError):
        return {}


def _dbt_cross_table_checks(path: Path, known: set[str]) -> list[tuple[str, str]]:
    """(check_id, why) for every dbt test that reads another table."""
    found = []
    for model in (_yaml(path).get("models") or []):
        owner = model.get("name", "")
        entries = [(t, None) for t in (model.get("tests") or [])]
        for column in (model.get("columns") or []):
            entries += [(t, column.get("name")) for t in (column.get("tests") or [])]
        for test, _column in entries:
            if not isinstance(test, dict):
                continue
            for name, body in test.items():
                if not isinstance(body, dict):
                    continue
                meta = body.get("meta") or {}
                text = yaml.safe_dump(body)
                others = {t for t in known if t in text and t not in owner}
                if name != _DBT_CROSS_TABLE and not others:
                    continue
                if meta.get("reads_tables"):
                    continue
                found.append((meta.get("check_id") or f"{owner}.{name}",
                               f"dbt {name} test on {owner} names {sorted(others) or 'another model'}"))
    return found


def _soda_cross_table_checks(path: Path) -> list[tuple[str, str]]:
    found = []
    for block in (_yaml(path) or {}).items() if isinstance(_yaml(path), dict) else []:
        key, checks = block
        if not key.startswith("checks for") or not isinstance(checks, list):
            continue
        for check in checks:
            if isinstance(check, str):
                text, attributes = check, {}
            elif isinstance(check, dict) and len(check) == 1:
                text, body = next(iter(check.items()))
                attributes = (body or {}).get("attributes") or {} if isinstance(body, dict) else {}
            else:
                continue
            match = _SODA_CROSS_TABLE.search(text)
            if not match or attributes.get("reads_tables"):
                continue
            found.append((attributes.get("check_id") or text,
                           f"soda check {text!r} reads {match.group(1)}"))
    return found


def _contract_cross_table_checks(path: Path, known: set[str]) -> list[tuple[str, str]]:
    """(check_id, why) for every ODCS SQL rule whose query names a table
    other than the one it is attached to.

    `{model}` is the placeholder for the rule's OWN table, so any real
    table name appearing in a query is by construction another one -
    which makes this the most reliable of the three scans rather than
    the loosest, despite SQL being the most free-form.
    """
    found = []
    doc = _yaml(path)

    def walk(node):
        if isinstance(node, dict):
            if node.get("type") == "sql" and "query" in node:
                props = {p["property"]: p["value"]
                          for p in node.get("customProperties") or []
                          if isinstance(p, dict) and "property" in p}
                others = sorted(t for t in known
                                 if re.search(rf"\b{re.escape(t)}\b", str(node["query"])))
                if others and not props.get("reads_tables"):
                    found.append((props.get("check_id") or str(node.get("description", ""))[:40],
                                   f"contract SQL rule reads {others}"))
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(doc)
    return found


def undeclared_cross_table(dbt_schema: Path | str | None = None,
                            soda_checks: Iterable[Path | str] = (),
                            contracts: Iterable[Path | str] = ()) -> list[str]:
    """Checks that LOOK cross-table and declare nothing.

    A MECHANICAL GATE, not a proof. It catches the three shapes this
    project actually writes - a dbt `relationships` test, a SodaCL
    "must exist in" sentence, and an ODCS SQL rule whose query names a
    real table (its own being `{model}`) - so a clean result says those
    three are complete, not that no check anywhere reads a table by
    some other means.

    Stated that way round deliberately: a gate whose limits are not
    written down gets read as a guarantee, and the next author adds a
    fourth shape it cannot see.
    """
    known = _known_tables()
    problems = []
    if dbt_schema is not None and Path(dbt_schema).exists():
        for check_id, why in _dbt_cross_table_checks(Path(dbt_schema), known):
            problems.append(f"{check_id}: {why}, but declares no reads_tables")
    for path in soda_checks:
        if Path(path).exists():
            for check_id, why in _soda_cross_table_checks(Path(path)):
                problems.append(f"{check_id}: {why}, but declares no reads_tables")
    for path in contracts:
        if Path(path).exists():
            for check_id, why in _contract_cross_table_checks(Path(path), known):
                problems.append(f"{check_id}: {why}, but declares no reads_tables")
    return sorted(problems)


#: The real sources, so a caller does not restate them and drift.
DBT_SCHEMA = ROOT / "dbt_project" / "models" / "staging" / "schema.yml"
SODA_CHECKS = (ROOT / "contract" / "child-protection-soda-checks.yml",
                ROOT / "contract" / "bdm-birth-registrations-soda-checks.yml")
CONTRACTS = (ROOT / "contract" / "child-protection-contract.yaml",
              ROOT / "contract" / "bdm-birth-registrations-contract.yaml")


def undeclared_in_this_repo() -> list[str]:
    """The gate over this repo's own real check sources."""
    return undeclared_cross_table(DBT_SCHEMA, SODA_CHECKS, CONTRACTS)
