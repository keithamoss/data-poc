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

#: Where a tool invocation's own native output is recorded
#: (REQ-PIPE-038): qa_results/<agency>/<collection>/_raw/<run_id>/.
#:
#: A THIRD scope beside the datasets and the cross-table one, because
#: raw_output describes an INVOCATION and a Child Protection scan is
#: one Scan() over all six tables - its scanStartTimestamp, hasErrors
#: and hasFailures are facts about the run, not about any one table.
#: Copying it into six dataset files would have each claim a raw output
#: that is not its own, and filtering it would break the
#: genuinely-unmodified guarantee that makes keeping it worthwhile. So
#: it is recorded once, where it is true.
#:
#: Also holds the two PSEUDO-TOOLS - `dataset_stats` and `tables_read`
#: - for the same reason: both describe a run rather than a dataset.
#:
#: Named for what it holds rather than for the level it sits at.
#: `_collection` would read as "collection-scoped RESULTS", which is
#: what `_cross-table` already is.
RAW_SCOPE = "_raw"

#: The pseudo-tools that describe a RUN. Neither is a real QA tool;
#: both reuse write_qa_result()'s file shape, and both belong in
#: RAW_SCOPE rather than under any one dataset.
RUN_SCOPED_TOOLS = ("dataset_stats", "tables_read")

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

#: The two BUSINESS-RULE shapes, added 2026-09-26 after the first three
#: turned out to cover only the mechanical ones. Six real checks - three
#: dbt singular tests and their three SodaCL twins - joined a second
#: table and declared nothing, and the gate said the repo was clean.
#:
#: They hid because a business rule does not announce itself in its
#: check TYPE the way `relationships` and "must exist in" do: it is an
#: ordinary `failed rows` or an ordinary singular test, and the join is
#: in its SQL. So these two scans read the SQL rather than the type,
#: which is what the contract scan already did - and the reason that
#: one alone caught the datacontract third of each pair.
_DBT_REF = re.compile(r"ref\(\s*['\"](\w+)['\"]\s*\)")
_DBT_MODEL_PREFIX = "stg_"
_SODA_QUERY_KEYS = ("fail query", "warn query", "failed rows query")


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


def _dbt_singular_cross_table_checks(path: Path) -> list[tuple[str, str]]:
    """(check_id, why) for every dbt SINGULAR test whose SQL joins.

    A singular test is a `.sql` file beside the models with its metadata
    declared under this schema's own top-level `tests:` key, so neither
    half tells the whole story: the name and the check_id are in the
    YAML, and the joins are in the file. This reads both.

    Two or more distinct `ref()`s is the signal. That is deliberately
    the shape rather than "names a known table", because a singular
    test cannot name a physical table at all - it goes through `ref()`
    by construction, which makes this the reliable scan of the two
    added here.
    """
    tests_dir = path.parents[2] / "tests"
    found = []
    for entry in (_yaml(path).get("tests") or []):
        if not isinstance(entry, dict):
            continue
        name = entry.get("name", "")
        meta = ((entry.get("config") or {}).get("meta") or {})
        sql = tests_dir / f"{name}.sql"
        if not sql.exists():
            continue
        try:
            refs = {m.removeprefix(_DBT_MODEL_PREFIX) for m in _DBT_REF.findall(sql.read_text())}
        except OSError:
            continue
        if len(refs) < 2 or meta.get("reads_tables"):
            continue
        found.append((meta.get("check_id") or name,
                       f"dbt singular test {name} joins {sorted(refs)}"))
    return found


def _soda_cross_table_checks(path: Path, known: set[str] | None = None) -> list[tuple[str, str]]:
    """(check_id, why) for every SodaCL check that reads another table.

    Two shapes. The sentence form ("must exist in X") announces itself
    in the check text. The BUSINESS-RULE form does not: it is a plain
    `failed rows` whose join lives in a `fail query`, so the only way to
    see it is to read the SQL and look for a table that is not the one
    this `checks for` block is about.

    `known` is optional so a caller testing the sentence form alone
    need not build the hierarchy; without it the query scan is skipped
    rather than guessing what counts as a table name.
    """
    doc = _yaml(path)
    found = []
    for key, checks in (doc.items() if isinstance(doc, dict) else []):
        if not key.startswith("checks for") or not isinstance(checks, list):
            continue
        owner = key.removeprefix("checks for").strip()
        for check in checks:
            if isinstance(check, str):
                text, body, attributes = check, {}, {}
            elif isinstance(check, dict) and len(check) == 1:
                text, body = next(iter(check.items()))
                body = body if isinstance(body, dict) else {}
                attributes = body.get("attributes") or {}
            else:
                continue
            if attributes.get("reads_tables"):
                continue
            match = _SODA_CROSS_TABLE.search(text)
            if match:
                found.append((attributes.get("check_id") or text,
                               f"soda check {text!r} reads {match.group(1)}"))
                continue
            if not known:
                continue
            query = " ".join(str(body.get(k, "")) for k in _SODA_QUERY_KEYS)
            others = sorted(table for table in known
                             if table != owner
                             and re.search(rf"\b{re.escape(table)}\b", query))
            if others:
                found.append((attributes.get("check_id") or text,
                               f"soda {text!r} on {owner} queries {others}"))
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

    A MECHANICAL GATE, not a proof. It catches the five shapes this
    project actually writes:

    * a dbt `relationships` test,
    * a dbt singular test whose SQL `ref()`s two models,
    * a SodaCL "must exist in" sentence,
    * a SodaCL `failed rows` whose `fail query` names another table,
    * an ODCS SQL rule whose query names a real table (its own being
      `{model}`).

    So a clean result says those five are complete, not that no check
    anywhere reads a table by some other means.

    Stated that way round deliberately, and it earned the phrasing the
    day after it was written: the first version claimed three shapes
    and was read as a guarantee, while six real business rules joined a
    second table beneath it. They were found by eye, from a duplicated
    section on a dataset page, not by the gate. A sixth shape will
    happen the same way.
    """
    known = _known_tables()
    problems = []
    if dbt_schema is not None and Path(dbt_schema).exists():
        for check_id, why in _dbt_cross_table_checks(Path(dbt_schema), known):
            problems.append(f"{check_id}: {why}, but declares no reads_tables")
        for check_id, why in _dbt_singular_cross_table_checks(Path(dbt_schema)):
            problems.append(f"{check_id}: {why}, but declares no reads_tables")
    for path in soda_checks:
        if Path(path).exists():
            for check_id, why in _soda_cross_table_checks(Path(path), known):
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
