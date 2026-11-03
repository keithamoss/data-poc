"""
REQ-GHUB-027 - the plain-English "what is actually failing" section that
goes into every QA ticket's opening body and every subsequent run
comment.

Until this, a ticket said only that a dataset was reading red or amber
and pointed at the dashboard for the detail. That was a deliberate
stance and this reverses it (Keith, 2026-09-20): whoever picks the
ticket up should be able to act on it without going somewhere else
first. The sentences are the ones REQ-QAC-024 authored onto every check,
so nothing new is written here - this only decides what to show and how
to group it.

Three real decisions are baked into the shape below, all Keith's:

  - EVERY check that is not green is listed, not only the ones matching
    the ticket's own status. An amber check under a red ticket is worth
    seeing while somebody is already looking. They are split under two
    headings all the same, because "why is this red" and "also worth
    knowing" are different questions and a flat list answers neither.
  - No cap. A genuinely broken dataset produces a long ticket, and that
    is the honest outcome; hiding the tail behind "and 14 more" hides it
    from the one person who has opened the ticket to fix it.
  - The list is rebuilt for every run comment and posted even when it is
    identical to the last one. The thread is then a real record of the
    failure set shrinking run by run, at the cost of repetition.

Grouping is by (name, description), which is what makes this readable at
all: cp-placements' 17 failing checks are 5 distinct questions asked by
different tools, and listing them raw would say "Null rate" six times.
Each group keeps every one of its checks as a real deep link, so the
grouping never loses a check - it only stops repeating its sentence.

Reads the already-built dashboard JSON and nothing else, same hard rule
as the rest of ticket_sync.py: no data/, no warehouse connection.
"""
from __future__ import annotations

from collections import OrderedDict
from urllib.parse import quote

from qa_tools.common.dataset_status import dashboard_status_of

# The real published dashboard. A ticket is read on github.com, so a
# relative link is no use and this has to be absolute.
DASHBOARD_BASE_URL = "https://keithamoss.github.io/data-poc/"

# Ordered worst-first, which is also the order the sections print in.
_NOT_GREEN = ("red", "amber")

_HEADING = {
    "red": "Failing checks",
    "amber": "Checks in warning",
}


def check_status(check: dict) -> str:
    """One check's current status, by the same rule the dashboard and the
    ticketing layer already share (qa_tools/common/dataset_status.py) -
    the tool's own verdict where it gave one, threshold math otherwise."""
    return dashboard_status_of(
        check, "current", "current_status", check.get("warn"), check.get("fail"))


def check_url(agency_id: str, collection_id: str, dataset_id: str,
              column_name: str, check_key: str) -> str:
    """A real deep link to one check on the live dashboard.

    Mirrors the template's own `stateToPath()` exactly, including that
    each segment is encoded separately - a column name really can contain
    a space or a bracket, since the table-level pseudo-columns are named
    "(table-level checks)" and "(supply-level checks)".

    `quote(safe="")` escapes a little more than JavaScript's own
    encodeURIComponent does - brackets, for one - which is harmless:
    decodeURIComponent turns %28 back into "(" just the same. Erring
    towards more escaping is the right direction for a string being
    pasted into Markdown."""
    seg = [
        "agency", agency_id, "collection", collection_id,
        "dataset", dataset_id, "column", column_name, "check", check_key,
    ]
    return DASHBOARD_BASE_URL + "#/" + "/".join(quote(s, safe="") for s in seg)


def _not_green_checks(dataset: dict) -> list[tuple[str, dict, str]]:
    """(column name, check, status) for every non-green, non-retired
    check on this dataset, in the dataset's own column and check order -
    never re-sorted, so a ticket reads in the same order as the page."""
    out = []
    for column in dataset.get("columns", []):
        for check in column.get("checks", []):
            if check.get("retired"):
                continue
            # The CP builder emits a placeholder row for a column that no
            # tool defines a rule for ("Neither the ODCS contract nor the
            # Soda/dbt check files define a rule for this column today").
            # There are 11 of them, they carry no check_id, key, name or
            # description, and they are all green - so filtering on
            # status alone happens to exclude them today. Excluded
            # explicitly all the same: "no check exists here" is not a
            # passing check, and a ticket must never list one as
            # failing. Without this, a future change that gave them a
            # real status would raise a KeyError inside a GitHub Actions
            # job rather than print something odd.
            if not check.get("key"):
                continue
            status = check_status(check)
            if status in _NOT_GREEN:
                out.append((column["name"], check, status))
    return out


def _group(rows: list[tuple[str, dict, str]]) -> "OrderedDict[tuple, list]":
    """Collapses checks asking the same question into one entry, keyed on
    the two authored fields a reader actually sees. Insertion-ordered, so
    grouping cannot reorder a dataset's own checks."""
    groups: OrderedDict[tuple, list] = OrderedDict()
    for column_name, check, _status in rows:
        key = (check.get("name") or "", check.get("description") or "")
        groups.setdefault(key, []).append((column_name, check))
    return groups


def _render_group(key: tuple, members: list, agency_id: str,
                  collection_id: str, dataset_id: str) -> list[str]:
    name, description = key
    columns = list(OrderedDict.fromkeys(c for c, _ in members))
    lines = [
        f"**{name}** — {len(members)} {'check' if len(members) == 1 else 'checks'}, "
        f"{len(columns)} {'column' if len(columns) == 1 else 'columns'}",
        "",
        description,
        "",
    ]
    for column_name in columns:
        links = " · ".join(
            f"[{check.get('tool_ref') or check.get('key')}]"
            f"({check_url(agency_id, collection_id, dataset_id, column_name, check['key'])})"
            for c, check in members if c == column_name
        )
        lines.append(f"- `{column_name}` — {links}")
    lines.append("")
    return lines


def build_check_summary(dataset: dict, status: str, agency_id: str,
                        collection_id: str, dataset_id: str) -> str:
    """The Markdown section naming what is not green on this dataset.

    `status` is the ticket's own status, and decides only which heading
    comes first - both sections are rendered whatever it is. Returns ""
    when nothing is failing, which is the green case: the resolved
    comment says so in a sentence and has no list to carry.
    """
    rows = _not_green_checks(dataset)
    if not rows:
        return ""

    order = [status] + [s for s in _NOT_GREEN if s != status]
    out: list[str] = []
    for section_status in order:
        section = [r for r in rows if r[2] == section_status]
        if not section:
            continue
        out.append(f"## {_HEADING[section_status]}")
        out.append("")
        for key, members in _group(section).items():
            out.extend(_render_group(key, members, agency_id, collection_id, dataset_id))
    return "\n".join(out).rstrip() + "\n"
