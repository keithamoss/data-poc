"""`mothman check`'s collections gate (REQ-PIPE-240 criteria 7 to 10).

TWO HALVES.

THE CONFIGURATION (criterion 7): every collection the hierarchy declares has
an adapter and every adapter names a declared collection; shorts and run
prefixes are unique, no run prefix begins another, each is a-z, 0-9 and
underscore only, and short enough that every name built from it fits
PostgreSQL's 63 bytes; dataset ids and table names are unique across the
asset; every collection's contract file exists.

THE CHECK FILES (REQ-QAC-241 criteria 2, 5 and 9): every collection has its
contract, Soda and Evidently check files, each in its agency's folder
contract/<agency-id>/ (a retired sibling may be absent); only the asset-wide
files sit at the top of contract/; and every dbt model, source, schema file
and singular test sits in a collection's own folder, with no singular test
name declared by two collections - dbt names a singular test by its file.

THE LITERALS (criteria 8 to 10): no product file names a collection by
writing it down - a hierarchy id as a string, an id as a whole
segment of one, or an f-string that begins with a run prefix and goes on to
build a run name. Each such site is a place a thirtieth collection would be
skipped or handed another collection's behaviour, so each is either rewired
onto the registry or listed below with the requirement that rewires it -
and the list may only shrink: a file listed that no longer holds such a
literal fails the gate too.
"""
from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent

#: Where product code lives (criterion 8).
SCANNED = ("qa_tools", "pipeline", "generator", "cli", "dashboard")

#: EXEMPT, each for its reason (criterion 9).
EXEMPT_DIRS = {
    "contract": "the configuration itself - where collections are declared",
    "qa_tools/collections": "the adapters - code that is, by design, one collection's",
    "generator/collections": "the generator's per-collection providers (REQ-GEN-246)",
    "aws": "reaches collections only through the processing pass (position.md call 9)",
}
#: In the scenario register, only these assignments' values: a scenario is
#: planted in a named dataset, which is what a scenario IS - and a correction's
#: riders (REQ-GEN-334, 2026-10-30) are the datasets whose supplies ride it.
SCENARIO_REGISTER = "generator/scenario_injection.py"
SCENARIO_EXEMPT_NAMES = ("INJECTIONS", "INHERITING_DATASET", "CORRECTION_RIDERS")

#: THE MIGRATION ALLOWLIST (criterion 10): every file still holding a
#: collection literal when REQ-PIPE-240 landed, with the requirement that
#: rewires it. It may only shrink.
ALLOWLIST: dict[str, str] = {}

#: The longest run name a run prefix is part of: the per-run view schema
#: (supply_db.RUN_SCHEMA_PREFIX, `qa_`) over a trial reference's
#: `adhoc_ref_` form, then the prefix, then the longest suffix recorded runs
#: carry - a 20-digit receipt key and a knock-on re-run's `__99__r99`.
LONGEST_SUFFIX = "_" + "9" * 20 + "__99__r99"
NAME_FORMS = ("qa_{p}", "qa_adhoc_{p}", "qa_adhoc_ref_{p}", "qa_ref_{p}")
PG_IDENTIFIER_BYTES = 63
RUN_PREFIX_PATTERN = re.compile(r"[a-z0-9_]+")
AGENCY_SHORT_PATTERN = re.compile(r"[a-z0-9]+")


# ---- criterion 7: the configuration ---------------------------------------

#: REQ-PIPE-240's temporary pointers, all removed by REQ-PIPE-248 (REQ-TEST-249
#: criterion 9): an adapter still declaring one is named, not a traceback.
TEMPORARY_POINTERS = ("dashboard_json", "dashboard_datasets", "results_json")


def _pointer_problem(c, exc: TypeError) -> str:
    where = f"qa_tools/collections/{c.module_name}.py"
    pointer = next((p for p in TEMPORARY_POINTERS if f"'{p}'" in str(exc)), None)
    if pointer is None:
        return f"{where} cannot build its adapter: {exc}"
    return (f"{where} declares {pointer!r}, a temporary pointer REQ-PIPE-248 removed - a "
            f"collection's report files are named by the registry, and every dashboard file "
            f"lists its datasets under `datasets`")


def config_problems(package: Path | None = None) -> list[str]:
    """`package` is the adapter package's directory - the real one unless a
    test names another."""
    from qa_tools import collections
    from qa_tools.common import hierarchy

    problems: list[str] = []
    try:
        declared = collections.all_collections()
    except ValueError as exc:
        # A hierarchy that cannot be read at all - a dataset id declared
        # twice, a collection missing its short - is reported, not raised.
        return [str(exc)]
    package = package or ROOT / "qa_tools" / "collections"
    modules = {p.stem for p in package.glob("*.py") if p.stem not in ("__init__", "base")}
    wanted = {c.module_name: c for c in declared}
    loaded = {}
    for c in declared:
        if c.module_name not in modules:
            problems.append(f"collection {c.id!r} has no adapter "
                            f"(qa_tools/collections/{c.module_name}.py)")
        else:
            try:
                adapter = collections.adapter(c)
            except TypeError as exc:
                problems.append(_pointer_problem(c, exc))
                continue
            loaded[c.id] = adapter
            if adapter.collection_id != c.id:
                problems.append(f"qa_tools/collections/{c.module_name}.py is the adapter of "
                                f"{adapter.collection_id!r}, not {c.id!r}")
    # REQ-QAC-242 criterion 5, closed by REQ-QAC-247 criterion 5 and REQ-PIPE-248
    # criterion 6: every legacy flag is retired, so legacy.KNOWN is empty and
    # any flag an adapter declares fails.
    from qa_tools.tools import legacy
    for c in declared:
        if c.id in loaded:
            for flag in sorted(loaded[c.id].legacy - set(legacy.KNOWN)):
                problems.append(f"qa_tools/collections/{c.module_name}.py declares legacy flag "
                                f"{flag!r}, but every legacy flag is retired (REQ-QAC-247, REQ-PIPE-248) - "
                                f"remove it, or unify the behaviour it preserved")
    for orphan in sorted(modules - set(wanted)):
        problems.append(f"qa_tools/collections/{orphan}.py names no declared collection")

    # REQ-PIPE-248 criterion 7: an agency's short names its collections'
    # report files, so it must be unique and safe in a file name.
    agency_shorts: dict[str, str] = {}
    for agency_id, short in dict((c.agency_id, c.agency_short) for c in declared).items():
        if not AGENCY_SHORT_PATTERN.fullmatch(short):
            problems.append(f"agency {agency_id!r}'s short {short!r} is not made only of "
                            f"a-z and 0-9")
        if short in agency_shorts:
            problems.append(f"agencies {agency_id!r} and {agency_shorts[short]!r} share the "
                            f"short {short!r}")
        agency_shorts[short] = agency_id

    for field in ("short", "run_prefix", "label"):
        seen: dict[str, str] = {}
        for c in declared:
            value = getattr(c, field)
            if value in seen:
                problems.append(f"{c.id!r} and {seen[value]!r} share the {field} {value!r}")
            seen[value] = c.id
    for c in declared:
        if not RUN_PREFIX_PATTERN.fullmatch(c.run_prefix):
            problems.append(f"{c.id!r}'s run_prefix {c.run_prefix!r} is not made only of "
                            f"a-z, 0-9 and underscore")
        for other in declared:
            if other is not c and other.run_prefix.startswith(c.run_prefix) \
                    and other.run_prefix != c.run_prefix:
                problems.append(f"{other.id!r}'s run_prefix {other.run_prefix!r} begins with "
                                f"{c.id!r}'s {c.run_prefix!r}")
        for form in NAME_FORMS:
            name = form.format(p=c.run_prefix) + LONGEST_SUFFIX
            if len(name.encode()) > PG_IDENTIFIER_BYTES:
                problems.append(f"{c.id!r}'s run_prefix {c.run_prefix!r} makes {name!r}, "
                                f"{len(name.encode())} bytes - over PostgreSQL's "
                                f"{PG_IDENTIFIER_BYTES}")
        if not (hierarchy.DATA_ASSET_YAML.parent / c.contract).is_file():
            problems.append(f"{c.id!r}'s contract file contract/{c.contract} is missing")

    for field in ("dataset_id", "table"):
        seen = {}
        for d in hierarchy.all_datasets():
            value = getattr(d, field)
            if value in seen and seen[value] != d.collection_id:
                problems.append(f"collections {seen[value]!r} and {d.collection_id!r} both "
                                f"declare the {'dataset id' if field == 'dataset_id' else 'table'}"
                                f" {value!r}")
            seen[value] = d.collection_id
    return problems


# ---- REQ-QAC-241 criteria 2, 5 and 9: the check files ----------------------

#: The only files at the top of contract/ - the asset's own, not a
#: collection's (REQ-QAC-241 criterion 2).
ASSET_WIDE = ("data-asset.yaml", "calendar.yaml", "people.yaml", "environments.yaml",
              "file-checks.yaml", "scripted_decisions.yaml", "presentation.yaml")
_CHECK_FILE = re.compile(r"(?P<stem>.+)-(?:contract|soda-checks|evidently-checks)(?:-retired)?\.ya?ml")
#: Shared dbt SQL that belongs to no collection (criterion 4).
_SHARED_DBT = ("dbt_project/tests/generic/",)


def check_file_problems(root: Path | None = None) -> list[str]:
    """`root` holds contract/ and dbt_project/ - the repository unless a
    test names another; the hierarchy is read from root/contract."""
    from qa_tools import collections
    from qa_tools.common import hierarchy

    root = root or hierarchy.DATA_ASSET_YAML.parent.parent
    try:
        declared = collections.all_collections()
    except ValueError:
        return []  # config_problems() reports a hierarchy that cannot be read
    problems: list[str] = []
    owner = {}
    for c in declared:
        if not c.contract.startswith(f"{c.agency_id}/"):
            problems.append(f"{c.id!r}'s contract {c.contract!r} is not in its agency's folder "
                            f"{c.folder}/")
        # Its contract is config_problems()'s (REQ-PIPE-240 criterion 7).
        for kind in ("soda", "evidently"):
            if not (root / c.check_file(kind)).is_file():
                problems.append(f"collection {c.id!r} is missing its {kind} check file "
                                f"{c.check_file(kind)}")
        owner[c.stem] = c

    contract = root / "contract"
    agencies = {c.agency_id for c in declared}
    for path in sorted(contract.rglob("*")) if contract.is_dir() else []:
        if not path.is_file():
            continue
        rel = path.relative_to(root).as_posix()
        if path.parent == contract:
            if path.name not in ASSET_WIDE:
                problems.append(f"{rel} is at the top of contract/, where only the asset-wide "
                                f"files belong ({', '.join(ASSET_WIDE)})")
            continue
        m = _CHECK_FILE.fullmatch(path.name)
        c = owner.get(m.group("stem")) if m else None
        if c is None:
            where = path.relative_to(contract).parts[0]
            problems.append(f"{rel} is no collection's check file" + (
                "" if where in agencies else f", in {where}/, which is no agency's folder"))
        elif path.parent != root / c.folder:
            problems.append(f"{rel} is {c.id!r}'s, which belongs in its agency's folder "
                            f"{c.folder}/")

    problems += _dbt_layout_problems(root, declared)
    problems += dbt_cross_collection_ref_problems(root, declared)
    return problems


_DBT_REF = re.compile(r"""ref\(\s*['"]([A-Za-z0-9_]+)['"]\s*\)""")


def dbt_cross_collection_ref_problems(root: Path, declared) -> list[str]:
    """REQ-PIPE-331 criterion 11: a dbt test reading another collection's
    table reads it through source(), never ref() to that collection's model -
    ref() would couple two collections' dbt folders (REQ-QAC-241). Each model
    belongs to the collection whose models folder defines it."""
    owner: dict[str, str] = {}
    for c in declared:
        base = root / c.dbt_models
        for path in sorted(base.glob("*.sql")) if base.is_dir() else []:
            owner[path.stem] = c.id
    problems = []
    for c in declared:
        for folder in (c.dbt_models, c.dbt_tests):
            base = root / folder
            for path in sorted(base.rglob("*")) if base.is_dir() else []:
                if not path.is_file() or path.suffix not in (".sql", ".yml", ".yaml"):
                    continue
                for model in _DBT_REF.findall(path.read_text()):
                    if owner.get(model, c.id) != c.id:
                        problems.append(
                            f"{path.relative_to(root).as_posix()} reads {model}, "
                            f"{owner[model]}'s model, through ref() - read another "
                            f"collection's table through source('raw', ...) instead "
                            f"(REQ-PIPE-331 criterion 11)")
    return problems


def _dbt_layout_problems(root: Path, declared) -> list[str]:
    """Criterion 5: dbt's models, sources, schema files and singular tests
    each in a collection's own folder; generic tests and macros shared."""
    problems = []
    folders = [c.dbt_models + "/" for c in declared] + [c.dbt_tests + "/" for c in declared]
    folders += [c.dbt_retired_schema.rsplit("/", 1)[0] + "/" for c in declared]
    singular: dict[str, str] = {}
    for top in ("dbt_project/models", "dbt_project/tests", "dbt_project/retired"):
        base = root / top
        for path in sorted(base.rglob("*")) if base.is_dir() else []:
            if not path.is_file() or path.suffix not in (".sql", ".yml", ".yaml"):
                continue
            rel = path.relative_to(root).as_posix()
            if rel.startswith(_SHARED_DBT):
                continue
            home = next((f for f in folders if rel.startswith(f)), None)
            if home is None:
                problems.append(f"{rel} sits outside every collection's dbt folder "
                                f"(dbt_project/models/<collection-id>/, "
                                f"dbt_project/tests/<collection-id>/)")
                continue
            if top == "dbt_project/tests" and path.suffix == ".sql":
                if path.stem in singular and singular[path.stem] != home:
                    problems.append(f"singular test {path.stem!r} is declared in both "
                                    f"{singular[path.stem]} and {home} - dbt names a singular "
                                    f"test by its file, so one would shadow the other")
                singular.setdefault(path.stem, home)
    return problems


# ---- criteria 8 to 10: the literals ---------------------------------------

def _names() -> tuple[set[str], tuple[str, ...]]:
    """(hierarchy ids, run prefixes). NOT SHORTS (post-build-review #235,
    Keith 2026-10-18): a two- or three-letter short collides with ordinary
    text - a keyboard-neighbour table's "wr", an agency short "rs" - while an
    id or run prefix is unambiguous, and a hard-coded short still shows
    itself as a broken command."""
    from qa_tools import collections
    from qa_tools.common import config_yaml, hierarchy

    doc = config_yaml.parse(hierarchy.DATA_ASSET_YAML.read_text()) or {}
    ids = set()
    for agency in ((doc.get("hierarchy") or {}).get("agencies") or []):
        ids.add(agency["id"])
        for coll in agency.get("collections") or []:
            ids.add(coll["id"])
            ids.update(d["id"] for d in coll.get("datasets") or [])
    return ids, tuple(c.run_prefix for c in collections.all_collections())


def _segment_patterns(ids: set[str]) -> list[re.Pattern]:
    return [re.compile(r"(?:^|[-./])" + re.escape(i) + r"(?:$|[-./])") for i in sorted(ids)]


def _names_a_collection(text: str, ids, segments) -> bool:
    return text in ids or any(p.search(text) for p in segments)


def _builds_a_run_name(head: str, next_is_field: bool, prefixes) -> bool:
    for prefix in prefixes:
        if head == prefix and next_is_field:
            return True
        if head.startswith(prefix) and head[len(prefix):len(prefix) + 1].isdigit():
            return True
    return False


def _docstring_nodes(tree: ast.AST) -> set[int]:
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = getattr(node, "body", [])
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
                    and isinstance(body[0].value.value, str):
                found.add(id(body[0].value))
    return found


def _exempt_scenario_nodes(tree: ast.AST) -> set[int]:
    found = set()
    for node in ast.walk(tree):
        targets = []
        if isinstance(node, ast.Assign):
            targets = node.targets
        elif isinstance(node, ast.AnnAssign):
            targets = [node.target]
        if any(isinstance(t, ast.Name) and t.id in SCENARIO_EXEMPT_NAMES for t in targets):
            found.update(id(n) for n in ast.walk(node.value))
    return found


def _python_findings(path: Path, rel: str, ids, prefixes, segments):
    tree = ast.parse(path.read_text(), filename=rel)
    skip = _docstring_nodes(tree)
    if rel == SCENARIO_REGISTER:
        skip |= _exempt_scenario_nodes(tree)
    inside_fstring = {id(v) for n in ast.walk(tree) if isinstance(n, ast.JoinedStr)
                      for v in n.values}
    for node in ast.walk(tree):
        if id(node) in skip:
            continue
        if isinstance(node, ast.JoinedStr) and node.values:
            first = node.values[0]
            if isinstance(first, ast.Constant) and isinstance(first.value, str):
                nxt = len(node.values) > 1 and isinstance(node.values[1], ast.FormattedValue)
                if _builds_a_run_name(first.value, nxt, prefixes):
                    yield node.lineno, first.value
        elif isinstance(node, ast.Constant) and isinstance(node.value, str) \
                and id(node) not in inside_fstring:
            if _names_a_collection(node.value, ids, segments):
                yield node.lineno, node.value


_JS_STRING = re.compile(r"""(?P<q>["'])(?P<s>(?:\\.|(?!(?P=q)).)*?)(?P=q)|`(?P<t>[^`]*)`""")


def _text_findings(path: Path, ids, prefixes, segments):
    for lineno, line in enumerate(path.read_text().splitlines(), start=1):
        for m in _JS_STRING.finditer(line):
            if m.group("t") is not None:
                head, _, _ = m.group("t").partition("${")
                if _builds_a_run_name(head, "${" in m.group("t"), prefixes):
                    yield lineno, m.group("t")
            elif _names_a_collection(m.group("s"), ids, segments):
                yield lineno, m.group("s")


def _exempt(rel: str) -> bool:
    return any(rel == d or rel.startswith(d + "/") for d in EXEMPT_DIRS)


def literal_findings(root: Path = ROOT) -> list[tuple[str, int, str]]:
    """Every (file, line, literal) criterion 8 names, allowlisted files
    included - the caller decides what the allowlist covers."""
    ids, prefixes = _names()
    segments = _segment_patterns(ids)
    found = []
    for top in SCANNED:
        for path in sorted((root / top).rglob("*")):
            rel = path.relative_to(root).as_posix()
            if not path.is_file() or _exempt(rel) or "__pycache__" in rel \
                    or "/vendor/" in rel or "/snapshots/" in rel:
                continue
            if path.suffix == ".py":
                hits = _python_findings(path, rel, ids, prefixes, segments)
            elif path.name.endswith(".template.html"):
                hits = _text_findings(path, ids, prefixes, segments)
            else:
                continue
            found.extend((rel, line, text) for line, text in hits)
    return found


def literal_problems(root: Path = ROOT, allowlist: dict[str, str] | None = None) -> list[str]:
    allowlist = ALLOWLIST if allowlist is None else allowlist
    findings = literal_findings(root)
    problems = [f"{rel}:{line}: {text!r} names a collection - read it from the registry "
                f"(qa_tools.collections), or list the file on the migration allowlist with "
                f"the requirement that rewires it"
                for rel, line, text in findings if rel not in allowlist]
    holding = {rel for rel, _line, _text in findings}
    problems += [f"{rel} is on the migration allowlist ({req}) but no longer holds a "
                 f"collection literal - take it off, so the allowlist only shrinks"
                 for rel, req in sorted(allowlist.items()) if rel not in holding]
    return problems


def presentation_problems() -> list[str]:
    """REQ-DASH-244 criterion 8: a registered collection the dashboard has no
    words for fails here, naming it, before any build."""
    from qa_tools.common import presentation

    return presentation.problems()


#: REQ-TEST-249 criterion 5: what a QA adapter is expected to cost, in lines
#: of logic. REPORTED, NEVER ENFORCED (position.md call 10) - both real
#: adapters were expected over it from the start, the overage being their
#: tool maps and statistics, which a smaller one-table collection lacks.
ADAPTER_LINE_BUDGET = 150


def logic_lines(path: Path) -> int:
    """The lines of `path` that hold code: every line a statement or
    expression starts on, never a comment, a blank line or a docstring."""
    tree = ast.parse(path.read_text())
    docstrings = set()
    for node in [tree, *ast.walk(tree)]:
        body = getattr(node, "body", None)
        if (isinstance(body, list) and body and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant) and isinstance(body[0].value.value, str)):
            docstrings.update(range(body[0].lineno, body[0].end_lineno + 1))
    return len({n.lineno for n in ast.walk(tree) if hasattr(n, "lineno")} - docstrings)


def line_report(root: Path = ROOT) -> list[str]:
    """Each registered collection's adapter against the budget, and its
    generator provider's lines beside it, outside the budget - a real
    deployment's collections have no synthetic generator at all."""
    from qa_tools import collections

    out = []
    for coll in collections.all_collections():
        adapter = root / "qa_tools" / "collections" / f"{coll.module_name}.py"
        provider = root / "generator" / "collections" / f"{coll.module_name}.py"
        if not adapter.is_file():
            continue  # config_problems() says so
        n = logic_lines(adapter)
        over = f", {n - ADAPTER_LINE_BUDGET} over" if n > ADAPTER_LINE_BUDGET else ""
        made = (f"; its generator provider {logic_lines(provider)}" if provider.is_file()
                else "; no generator provider")
        out.append(f"{coll.id}: adapter {n} lines of logic against a budget of "
                   f"{ADAPTER_LINE_BUDGET}{over}{made}.")
    return out


def main() -> int:
    from qa_tools.common import linked_datasets, run_reads

    problems = (config_problems() + check_file_problems() + literal_problems()
                + presentation_problems() + linked_datasets.problems() + run_reads.declaration_problems())
    for line in line_report():  # reported whether or not the gate passes
        print(f"  {line}")
    if problems:
        for p in problems:
            print(f"  {p}")
        print(f"collections gate FAILED - {len(problems)} problem(s).")
        return 1
    print(f"collections OK - every collection has an adapter, and {len(ALLOWLIST)} file(s) "
          f"still wait on the requirement that rewires them.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
