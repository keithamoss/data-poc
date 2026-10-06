"""File checks: the questions only the file as delivered can answer, asked
of its bytes before a row is loaded (REQ-QAC-096).

WHY A FIFTH TOOL AT ALL. Loading answers some questions and destroys the
evidence for others, measured against the real loader on 2026-10-04: a
short row is padded with empty values every data check then reads as a
genuinely empty field; a repeated header is silently renamed; a file whose
every row carries one extra field shifts every column one place without
raising anything. Once loaded, no data check can tell. So these few
questions are asked of the bytes, before the load, and nothing else is
(criterion 2).

DEFINED ONCE, IDS DERIVED PER DATASET (criterion 4). The definitions and
their prose are `contract/file-checks.yaml`; each dataset gets each check
under `<asset>.<agency>.<collection>.<dataset>.<name>_file`, the existing
grammar with a fifth tool suffix. Six checks on thirty datasets is 180
entries nobody should have to keep in step by hand.

ONE STREAMING PASS, BOUNDED MEMORY (NFR 2). The file is read line by line
as bytes; nothing holds more than one row. Standard library only (NFR 5).

WHERE, NEVER WHAT (criterion 14). Every finding is worded by line number,
field count and column name. A column name is the supplier's header, not
a row value; a row value never reaches a finding.

AN EVALUATOR BUG IS NOT A SUPPLIER FAULT (criterion 13): anything raised
while evaluating is re-raised as FileCheckCrashed naming the check, which
the loader deliberately does NOT catch - the run fails, and nothing about
the file is recorded.
"""
from __future__ import annotations

import re

import csv
from dataclasses import dataclass
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent.parent
DEFINITIONS_PATH = ROOT / "contract" / "file-checks.yaml"

#: The fifth tool suffix (check_id.TOOLS) and the value of `qa.check_result.tool`.
TOOL = "file"

#: How much a finding matters (criterion 18): a FAILURE refuses the file, a
#: WARNING is recorded and the file loads.
FAILURE = "failure"
WARNING = "warning"

ENCODING = "encoding"
DELIMITER = "delimiter"
HEADER_ROW = "header_row"
HEADER_NAMES_UNIQUE = "header_names_unique"
FIELDS_PER_ROW = "fields_per_row"
COLUMN_ORDER = "column_order"
#: Evaluation order, which is also reading order on the page.
NAMES = (ENCODING, DELIMITER, HEADER_ROW, HEADER_NAMES_UNIQUE, FIELDS_PER_ROW, COLUMN_ORDER)

#: The existing status vocabulary, nothing new (REQ-DASH-097 criterion 10).
#: `nodata` is a check that could not be asked of this file because an
#: earlier one failed - a header that does not split has no names to
#: compare, and saying "passed" there would be a false green.
PASS, WARN, FAIL, NODATA = "pass", "warn", "fail", "nodata"


class FileCheckCrashed(RuntimeError):
    """Our own evaluator raised (criterion 13). Never a finding about the file."""

    def __init__(self, check: str, exc: BaseException):
        super().__init__(f"the file check {check!r} could not be evaluated: "
                         f"{type(exc).__name__}: {exc}")
        self.check = check


@dataclass(frozen=True)
class Definition:
    check: str
    severity: str
    formats: tuple[str, ...]
    name: str
    retired: bool


def definitions(path: Path | str | None = None) -> list[Definition]:
    """Every file check in the committed configuration, in NAMES order."""
    doc = yaml.safe_load(Path(path or DEFINITIONS_PATH).read_text()) or {}
    out = [Definition(check=str(raw["check"]), severity=str(raw["severity"]),
                      formats=tuple(raw.get("formats") or ("csv",)),
                      name=str(raw.get("name") or raw["check"]).strip(),
                      retired=bool(raw.get("retired_as_of")))
           for raw in doc.get("checks") or []]
    order = {n: i for i, n in enumerate(NAMES)}
    return sorted(out, key=lambda d: order.get(d.check, len(order)))


def active(fmt: str = "csv", path=None) -> list[Definition]:
    return [d for d in definitions(path) if not d.retired and fmt in d.formats]


def check_id_for(dataset, check: str) -> str:
    """Criterion 4: `<asset>.<agency>.<collection>.<dataset>.<check>_file`."""
    return (f"{dataset.data_asset_id}.{dataset.agency_id}.{dataset.collection_id}."
            f"{dataset.dataset_id}.{check}_{TOOL}")


@dataclass(frozen=True)
class Finding:
    check: str
    severity: str
    status: str
    #: Where, never what (criterion 14): line numbers, field counts and
    #: column names only.
    words: str

    @property
    def refuses(self) -> bool:
        """Criterion 11: a FAILURE-level check that failed refuses the file."""
        return self.status == FAIL and self.severity == FAILURE


class _Pass:
    """One pass over the bytes, gathering what every check needs."""

    def __init__(self, path, delimiter: str):
        self.path = Path(path)
        self.delimiter = delimiter
        self.bad_encoding: tuple[int, int] | None = None   # (line, byte offset)
        self.header: list[str] | None = None
        self.uneven = 0
        self.first_uneven: tuple[int, int] | None = None   # (line, fields)
        self.unsplittable: int | None = None              # line csv refused

    def _lines(self):
        offset = 0
        with self.path.open("rb") as f:
            for lineno, raw in enumerate(f, 1):
                if lineno == 1 and raw.startswith(b"\xef\xbb\xbf"):
                    raw, offset = raw[3:], 3
                try:
                    text = raw.decode("utf-8")
                except UnicodeDecodeError as exc:
                    if self.bad_encoding is None:
                        self.bad_encoding = (lineno, offset + exc.start)
                    text = raw.decode("utf-8", errors="replace")
                offset += len(raw)
                yield text

    def run(self) -> "_Pass":
        # NO FIELD-SIZE CEILING OF OUR OWN (#118 D-F): Python's csv default is
        # 128 KiB, and a legitimate longer field - which the loader reads -
        # was refused as unsplittable. Still one row at a time (NFR 2).
        csv.field_size_limit(max(csv.field_size_limit(), 2**31 - 1))
        reader = csv.reader(self._lines(), delimiter=self.delimiter)
        try:
            for row in reader:
                if self.header is None:
                    if row:
                        self.header = row
                    continue
                # A blank line is skipped by the loader too, so it is not a
                # short row.
                if not row:
                    continue
                if len(row) != len(self.header):
                    self.uneven += 1
                    if self.first_uneven is None:
                        self.first_uneven = (reader.line_num, len(row))
        except csv.Error:
            # A line the splitter itself refuses (an unterminated quote at the
            # end of the file, a NUL byte): a row that cannot be counted is a
            # row that does not have the header's fields.
            self.unsplittable = reader.line_num
        return self


def _count(n: int, one: str, many: str) -> str:
    return f"{n} {one if n == 1 else many}"


def _encoding(p: _Pass, expected) -> tuple[str, str]:
    if p.bad_encoding is None:
        return PASS, "every line is readable as UTF-8"
    line, offset = p.bad_encoding
    return FAIL, f"line {line} is not valid UTF-8 (the first unreadable byte is at offset {offset})"


def _delimiter(p: _Pass, expected) -> tuple[str, str]:
    if p.header is None:
        return NODATA, "not evaluated: the file has no lines"
    if len(p.header) == 1 and len(expected) > 1:
        return FAIL, (f"the first line does not split on commas: it is one field "
                      f"where {len(expected)} columns were expected")
    return PASS, f"the first line splits into {_count(len(p.header), 'field', 'fields')}"


def _header_row(p: _Pass, expected) -> tuple[str, str]:
    if p.header is None:
        return FAIL, "the file is empty: it has no header row"
    if _delimiter(p, expected)[0] == FAIL:
        return NODATA, "not evaluated: the first line could not be split"
    # A HEADER NAMES A CONTRACT COLUMN AND HOLDS NO VALUE (Keith, 2026-10-06,
    # post-build-review #118 D-E). Naming one column alone let a headerless
    # file through when its first row happened to hold a value equal to a
    # column name, and its first row was then taken for the names - a false
    # green. A column name is never a date, a number or true/false, so a
    # first line with any such field is data. MISSING columns stay a data
    # check's question (criterion 2) - the "most columns named" rule was
    # tried and reverted for refusing exactly those - and a REPEATED name stays
    # header_names_unique's, which could never fail if this refused it. The
    # value itself is never quoted: it is a row of somebody's data.
    if expected and not set(p.header) & set(expected):
        return FAIL, ("the first line names none of the contract's columns, so it is a "
                      "row of data rather than a header")
    shaped = [i for i, field in enumerate(p.header, start=1) if _value_shaped(field)]
    if shaped:
        return FAIL, (f"the first line holds {_count(len(shaped), 'value', 'values')} - "
                      f"field {shaped[0]} is shaped like a date, a number or true/false, "
                      f"which no column name is - so it is a row of data rather than a "
                      f"header")
    return PASS, "the first line is a header naming the columns"


_VALUE_SHAPES = (
    re.compile(r"[+-]?\d+([.,]\d+)?"),                      # a number
    re.compile(r"\d{4}-\d{2}-\d{2}([ T].*)?"),              # an ISO date or timestamp
    re.compile(r"\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4}"),          # a day-month-year date
    re.compile(r"(?i)true|false"),
)


def _value_shaped(field: str) -> bool:
    text = (field or "").strip()
    return bool(text) and any(shape.fullmatch(text) for shape in _VALUE_SHAPES)


def _header_ready(p: _Pass, expected) -> str | None:
    """Why a check that compares header names cannot be asked, if it cannot."""
    status, _ = _header_row(p, expected)
    return None if status == PASS else "not evaluated: there is no usable header row"


def _header_names_unique(p: _Pass, expected) -> tuple[str, str]:
    if (why := _header_ready(p, expected)):
        return NODATA, why
    seen, repeated = set(), []
    for name in p.header:
        if name in seen and name not in repeated:
            repeated.append(name)
        seen.add(name)
    if repeated:
        # ONLY A NAME THE CONTRACT LISTS IS QUOTED (#118 D-E, criterion 14):
        # anything else on that line may be a row value, so it is counted.
        known = [n for n in repeated if n in expected]
        unknown = len(repeated) - len(known)
        parts = [", ".join(f'"{n}"' for n in known)] if known else []
        if unknown:
            parts.append(_count(unknown, "column name the contract does not list",
                                "column names the contract does not list"))
        return FAIL, "the header names " + " and ".join(parts) + " more than once"
    return PASS, "no column is named twice"


def _fields_per_row(p: _Pass, expected) -> tuple[str, str]:
    if (why := _header_ready(p, expected)):
        return NODATA, why
    if p.unsplittable is not None and p.first_uneven is None:
        return FAIL, f"line {p.unsplittable} could not be split into fields"
    if p.uneven:
        line, fields = p.first_uneven
        more = (f"; line {p.unsplittable} also could not be split"
                if p.unsplittable is not None else "")
        return FAIL, (f"{_count(p.uneven, 'row has', 'rows have')} a different number of "
                      f"fields from the header; the first is line {line}, with {fields} "
                      f"where {len(p.header)} were expected{more}")
    return PASS, f"every row has {len(p.header)} fields, as the header does"


def _column_order(p: _Pass, expected) -> tuple[str, str]:
    if (why := _header_ready(p, expected)):
        return NODATA, why
    shared = set(p.header) & set(expected)
    # First appearance only: a repeated name is header_names_unique's fault.
    arrived = list(dict.fromkeys(c for c in p.header if c in shared))
    agreed = [c for c in expected if c in shared]
    if arrived == agreed:
        return PASS, "the columns are in the contract's order"
    i = next(i for i, (a, b) in enumerate(zip(arrived, agreed)) if a != b)
    return FAIL, (f"the columns are not in the contract's order: \"{arrived[i]}\" arrives "
                  f"where the contract has \"{agreed[i]}\"")


_EVALUATORS = {ENCODING: _encoding, DELIMITER: _delimiter, HEADER_ROW: _header_row,
               HEADER_NAMES_UNIQUE: _header_names_unique, FIELDS_PER_ROW: _fields_per_row,
               COLUMN_ORDER: _column_order}


def evaluate(path, expected_columns, *, definitions_path=None,
             delimiter: str = ",") -> list[Finding]:
    """Every active CSV file check against this file's bytes (criterion 1).

    A WARNING-level check that does not pass reads `warn`, never `fail`, so
    the status a reader sees already says how much it matters."""
    expected = list(expected_columns)
    try:
        gathered = _Pass(path, delimiter).run()
    except OSError:
        # A file that is not there or cannot be opened has no bytes to ask
        # anything of. That is the load failure the loader already records
        # in its own words, not a bug in this evaluator - so it propagates
        # as itself, and screen() steps aside for it.
        raise
    except Exception as exc:  # noqa: BLE001 - criterion 13
        raise FileCheckCrashed("(reading the file)", exc) from exc
    out = []
    for d in active("csv", definitions_path):
        evaluator = _EVALUATORS.get(d.check)
        if evaluator is None:
            raise FileCheckCrashed(d.check, LookupError("no evaluator for this check"))
        try:
            status, words = evaluator(gathered, expected)
        except Exception as exc:  # noqa: BLE001 - criterion 13
            raise FileCheckCrashed(d.check, exc) from exc
        if status == FAIL and d.severity == WARNING:
            status = WARN
        out.append(Finding(d.check, d.severity, status, words))
    return out


def refusal(findings: list[Finding]) -> Finding | None:
    """The first finding that refuses the file, if any (criterion 11)."""
    return next((f for f in findings if f.refuses), None)


def reason_for(finding: Finding, filename: str) -> str:
    """The recorded load-failure reason for a refused file: our own words,
    naming the file and the check (REQ-DASH-097 criterion 6)."""
    # BY ITS NAME, as the section and panel call it (#118 D-G), and a
    # finished sentence, since the outstanding item appends another.
    names = {d.check: d.name for d in definitions()}
    words = finding.words.rstrip()
    return (f"{filename} failed the file check {names.get(finding.check, finding.check)}: "
            f"{words}{'' if words.endswith('.') else '.'}")


def expected_columns(contract_path, table: str) -> list[str]:
    """The contract's columns for one table, in the contract's order - what
    a header is compared with."""
    doc = yaml.safe_load(Path(contract_path).read_text()) or {}
    for entry in doc.get("schema") or []:
        if entry.get("name") == table:
            return [p["name"] for p in entry.get("properties") or []]
    return []


def _as_record(finding: Finding, dataset, definition: Definition | None) -> dict:
    return {
        "dataset_id": dataset.dataset_id,
        "check_id": check_id_for(dataset, finding.check),
        "check_name": definition.name if definition else finding.check,
        "status": finding.status,
        "dimension": None,
        "engine": TOOL,
        "finding": finding.words,
        "severity": finding.severity,
    }


def _dataset(dataset_id: str):
    """The dataset a loader named - by id, or by TABLE where a caller handed
    the loader a table name in its place. build_cp_warehouses falls back to
    the table name when it is given no dataset id (the `mothman cp qa`
    path), and the first full run of the suite with this module in it
    stopped on exactly that: 'cp_clients' is not a dataset."""
    from qa_tools.common import hierarchy

    try:
        return hierarchy.dataset(dataset_id)
    except hierarchy.UnknownDatasetError:
        return hierarchy.dataset_for_table(dataset_id)


def record(findings: list[Finding], *, run_id: str, dataset_id: str, delivery: str,
           filename: str, load_attempt, conn=None) -> int:
    """Record one load attempt's file-check results (criteria 7 and 8).

    `load_attempt` is the load record that attempt wrote - None where the
    load log wrote nothing, because the latest record already said exactly
    this: re-staging an unchanged file is not a new attempt, and recording
    its identical results again would be the unbounded repetition
    load_log.record_load() exists to stop. A reprocessed file whose
    outcome CHANGED writes a new load record, and so new results
    (criterion 16), beside the earlier attempt's rather than over them.

    THE RUN IS REGISTERED IF ABSENT, never updated: staging happens before
    the orchestrator opens the run, and the results need their run to
    exist. Becoming visible waits for the run to complete, exactly as every
    other result does.
    """
    if load_attempt is None or not findings:
        return 0
    from qa_tools.common import asset_time, qa_store, sample_data, supply_db

    dataset = _dataset(dataset_id)
    by_check = {d.check: d for d in definitions()}
    rows = [_as_record(f, dataset, by_check.get(f.check)) for f in findings]

    def write(db):
        qa_store.ensure_schema(db)
        qa_store.register_run_if_absent(
            db, run_key=run_id, agency_id=dataset.agency_id,
            collection_id=dataset.collection_id, run_timestamp=asset_time.now().isoformat())
        return qa_store.record_file_results(
            db, run_id, rows, agency_id=dataset.agency_id,
            collection_id=dataset.collection_id,
            supply_state=sample_data.supply_state(dataset.dataset_id),
            load_attempt=load_attempt.id, delivery=delivery, filename=filename)
    if conn is not None:
        return write(conn)
    with supply_db.connect(label="mothman:file-checks") as opened:
        return write(opened)


@dataclass
class Screening:
    """What one file's checks found, waiting for the load attempt they
    will be recorded against."""

    findings: list[Finding]
    run_id: str
    dataset_id: str
    delivery: str
    filename: str

    @property
    def refused(self) -> Finding | None:
        return refusal(self.findings)

    def record_against(self, attempt, conn=None) -> int:
        return record(self.findings, run_id=self.run_id, dataset_id=self.dataset_id,
                      delivery=self.delivery, filename=self.filename,
                      load_attempt=attempt, conn=conn)


def screen(conn, csv_path, *, contract_path, table: str, run_id: str, dataset_id: str,
           delivery: str, staging: str, physical: str, trial_scope) -> Screening:
    """Both loaders' one call, BEFORE they read a row (criterion 1).

    Where the file is refused (criterion 11) this does everything a refusal
    needs - no table left behind, a FAILED load record through the existing
    mechanism whose reason names the file and the check (REQ-DASH-097
    criterion 6), and the results against that attempt - and the caller
    stops. Otherwise the caller loads as usual and records the results
    against whichever load record its attempt wrote.

    FileCheckCrashed is deliberately NOT caught here or by the callers'
    catch-all around the load, which this runs outside of (criterion 13).
    """
    from qa_tools.common import asset_time, load_log

    filename = Path(csv_path).name
    try:
        findings = evaluate(csv_path, expected_columns(contract_path, table))
    except OSError:
        # Nothing to check; the load that follows fails on the same missing
        # file and records it through the existing mechanism.
        findings = []
    screening = Screening(findings, run_id, dataset_id, delivery, filename)
    refused = screening.refused
    if refused is not None:
        conn.execute(f'DROP TABLE IF EXISTS "{staging}"."{physical}" CASCADE')
        attempt = load_log.record_load(delivery, dataset_id, physical, load_log.FAILED,
                                       asset_time.now().isoformat(),
                                       reason=reason_for(refused, filename), trial=trial_scope)
        screening.record_against(attempt, conn=conn)
        import sys
        print(f"{run_id}: {table} refused by the file check {refused.check} "
              f"({refused.words}) - no table staged, recorded for human action",
              file=sys.stderr)
    return screening
