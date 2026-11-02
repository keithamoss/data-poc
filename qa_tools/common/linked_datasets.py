"""What an asset-level product links, gated (REQ-QAC-330 criteria 5 and 6;
REQ-QAC-333 criteria 3 and 8).

GENERIC: any dataset may declare `linked_datasets` beside it in
contract/data-asset.yaml - each a dataset id, the supplier's own code and the
ordered source columns id_1 onward hold. Nothing here names Linkage Products.
CONFIGURATION ONLY: the hierarchy, the calendar, the contracts and the Soda
check files, read from `root` so a test can hand it a copy.
"""
from __future__ import annotations

import re
from pathlib import Path

import yaml
from qa_tools.common import assets as _assets

REPO = Path(__file__).resolve().parent.parent.parent


def _asset_folder(root: Path) -> Path:
    """The selected asset's configuration folder in the checkout at `root`,
    asked of the resolver at call time (REQ-PIPE-342 criterion 6)."""
    from qa_tools.common import assets

    return root / assets.folder_on_disk()
_ID = re.compile(r"^id_(\d+)$")


def _load(path: Path):
    return yaml.safe_load(path.read_text()) if path.exists() else None


def _walk(asset: dict):
    """(agency, collection, dataset) for every dataset in the hierarchy."""
    for agency in ((asset.get("hierarchy") or {}).get("agencies") or []):
        for coll in agency.get("collections") or []:
            for ds in coll.get("datasets") or []:
                yield agency, coll, ds


def _calendar_of(cal: dict, coll_id: str, ds_id: str) -> str | None:
    """The calendar a dataset names, its own or its collection's; None where
    it names none (REQ-PIPE-106)."""
    entry = next((d for d in cal.get("datasets") or [] if d.get("id") == ds_id), {}) or {}
    if entry.get("no_calendar"):
        return None
    if entry.get("calendar"):
        return entry["calendar"]
    coll = next((c for c in cal.get("collections") or [] if c.get("id") == coll_id), {}) or {}
    return coll.get("calendar")


def _columns(root: Path, contract: str, table: str) -> list[str]:
    doc = _load(_asset_folder(root) / contract) or {}
    for t in doc.get("schema") or []:
        if t.get("name") == table:
            return [p.get("name") for p in t.get("properties") or []]
    return []


def _soda_checks(path: Path) -> list[tuple[str, dict]]:
    """(check_id, attributes) for every Soda check in a file."""
    return [(cid, attrs) for cid, attrs, _body in _soda_bodies(path)]


def _soda_bodies(path: Path, table: str | None = None) -> list[tuple[str, dict, dict]]:
    """(check_id, attributes, the check's whole body) for every Soda check -
    or, given a table, for the checks of its own 'checks for <table>' block
    only (REQ-QAC-294 criterion 5)."""
    return [(cid, attrs, body) for cid, attrs, body, _key in _soda_items(path, table)]


def _soda_items(path: Path, table: str | None = None) -> list[tuple[str, dict, dict, str]]:
    """(check_id, attributes, body, the check's own key) - the key being what
    names the metric and its column, e.g. 'invalid_count(dataset)'."""
    doc = _load(path) or {}
    out = []
    for key, checks in doc.items():
        if not str(key).startswith("checks for"):
            continue
        if table is not None and str(key)[len("checks for"):].strip() != table:
            continue
        for item in checks or []:
            if isinstance(item, dict):
                for check_key, body in item.items():
                    attrs = (body or {}).get("attributes") or {} if isinstance(body, dict) else {}
                    if attrs.get("check_id"):
                        out.append((attrs["check_id"], attrs, body, str(check_key)))
    return out


#: A Soda check on one column: 'invalid_count(dataset)' -> 'dataset'.
_ON_COLUMN = re.compile(r"^\w+\(\s*([\w]+)\s*\)$")


_CAST = re.compile(r"CAST\(\s*([\w.]+)\s+AS\s+TEXT\s*\)", re.IGNORECASE)
_EQ = re.compile(r"([\w.]+)\s*=\s*([\w.]+)")
_CODE = re.compile(r"\bdataset\s*=\s*'([^']*)'", re.IGNORECASE)


def _queries(body: dict) -> list[str]:
    """The SQL a Soda check runs: its fail query, or its metric's query."""
    return [v for k, v in body.items() if isinstance(v, str) and k.endswith("query")]


def _query_problems(check_id: str, body: dict, mapping: dict, did: str | None,
                    check_key: str = "") -> list[str]:
    """REQ-QAC-333 criterion 3 against WHAT RUNS: every dataset code a query
    or a valid-values list states is one the mapping declares (the linked
    dataset's own, for a referential or coverage check); and every identifier
    a referential or coverage query compares is the mapping's column for that
    id, cast to text.

    THE VALID-VALUES RULE IS THE CODE COLUMN'S (REQ-QAC-294 criterion 14): it
    exists so the dataset column holds only declared codes, so it reads only a
    check on that column, and none at all for a dataset whose entry has no
    code - another column's allowed values are not codes."""
    codes = {c for c, _cols in mapping.values() if c is not None}
    out = []
    values = body.get("valid values")
    on = _ON_COLUMN.match(check_key.strip())
    if (codes and on and on.group(1) == CODE_COLUMN and isinstance(values, list)
            and sorted(values) != sorted(codes)):
        out.append(f"check {check_id} states the valid values {sorted(values)}; the mapping "
                   f"declares {sorted(codes)}.")
    for sql in _queries(body):
        for stated in (_CODE.findall(sql) if codes else ()):
            if did is not None and stated != mapping[did][0]:
                out.append(f"check {check_id} queries the code {stated!r} for {did}; the "
                           f"mapping declares {mapping[did][0]!r}.")
            elif did is None and stated not in codes:
                owner = ", ".join(sorted(codes))
                out.append(f"check {check_id} queries the code {stated!r}, which no linked "
                           f"dataset declares; the mapping declares {owner}.")
        if did is None:
            continue
        cols = mapping[did][1]
        cast = {m.split(".")[-1] for m in _CAST.findall(sql)}
        plain = _CAST.sub(lambda m: m.group(1), sql)
        for left, right in _EQ.findall(plain):
            a, b = left.split(".")[-1], right.split(".")[-1]
            ida, idb = _ID.match(a), _ID.match(b)
            if bool(ida) == bool(idb):
                continue
            j, col = (int((ida or idb).group(1)), b if ida else a)
            want = cols[j - 1] if j <= len(cols) else None
            if col != want:
                out.append(f"check {check_id} compares id_{j} with the column {col!r} of "
                           f"{did}; the mapping declares {want!r}.")
            elif col not in cast or f"id_{j}" not in cast:
                out.append(f"check {check_id} compares id_{j} with {did}'s {col!r} without "
                           f"casting both to text (REQ-QAC-333 criterion 3).")
    return out


#: The declaring table's code column - the one REQ-QAC-330 declares, whose
#: values are the linked datasets' codes. A table without it links one source,
#: by a single entry with no code (REQ-QAC-294 criteria 2 and 4).
CODE_COLUMN = "dataset"


def problems(root: Path = REPO) -> list[str]:
    asset = _load(_asset_folder(root) / "data-asset.yaml") or {}
    cal = _load(_asset_folder(root) / "calendar.yaml") or {}
    where = {ds.get("id"): (agency, coll, ds) for agency, coll, ds in _walk(asset)}
    out: list[str] = []
    #: (collection id, source dataset) -> the dataset declaring it alone, with no code
    sole: dict[tuple[str, str], str] = {}
    for agency, coll, product in _walk(asset):
        linked = product.get("linked_datasets") or []
        if not linked:
            continue
        pid = product.get("id")
        product_cal = _calendar_of(cal, coll.get("id"), pid)
        own = _columns(root, coll.get("contract", ""), product.get("table"))
        n = max((int(m.group(1)) for c in own if (m := _ID.match(c or ""))), default=0)
        has_code_column = CODE_COLUMN in own
        codeless = [e for e in linked if e.get("code") is None]
        if len(codeless) > 1:
            out.append(f"{pid} declares {len(codeless)} linked datasets without a code "
                       f"({', '.join(repr(e.get('dataset')) for e in codeless)}) - with no "
                       f"{CODE_COLUMN} column a row cannot say which it is about, so a "
                       f"dataset declares at most one.")
        if len(linked) == 1 and len(codeless) == 1:
            key = (coll.get("id"), codeless[0].get("dataset"))
            if key in sole:
                out.append(f"{pid} and {sole[key]} each declare {key[1]!r} as their one "
                           f"linked dataset without a code - one source, geocoded twice in "
                           f"one collection.")
            sole.setdefault(key, pid)
        by_code: dict[str, str] = {}
        mapping: dict[str, tuple[str | None, list[str]]] = {}
        for entry in linked:
            did, code, cols = entry.get("dataset"), entry.get("code"), list(entry.get("id_columns") or [])
            head = f"{pid} links {did!r}"
            if code is None and has_code_column:
                out.append(f"{head} with no code, but its table {product.get('table')!r} has a "
                           f"{CODE_COLUMN} column, whose values are its linked datasets' codes.")
            elif code is not None and not has_code_column:
                out.append(f"{head} with the code {code!r}, but its table "
                           f"{product.get('table')!r} has no {CODE_COLUMN} column to carry it.")
            if code is not None and code in by_code:
                out.append(f"{head}: two linked datasets declare the code {code!r} "
                           f"({by_code[code]!r} and {did!r}) - every row's dataset would be ambiguous.")
            if code is not None:
                by_code.setdefault(code, did)
            if did not in where:
                out.append(f"{head}, which is not in the hierarchy ({_assets.config_dir()}/data-asset.yaml).")
                continue
            mapping[did] = (code, cols)
            _a, l_coll, l_ds = where[did]
            l_cal = _calendar_of(cal, l_coll.get("id"), did)
            if l_cal is None:
                out.append(f"{head}, which names no calendar, so it has no period to be read for.")
            elif l_cal != product_cal:
                out.append(f"{head}, which is never on {pid}'s calendar {product_cal!r} "
                           f"(it is on {l_cal!r}) - a check reads only its own period.")
            source = _columns(root, l_coll.get("contract", ""), l_ds.get("table"))
            for col in cols:
                if col not in source:
                    out.append(f"{head} by the column {col!r}, which its contract does not declare.")
            if len(cols) > n:
                out.append(f"{head} by {len(cols)} identifier columns, more than the contract's "
                           f"id_1 to id_{n}.")
        out += _check_problems(root, coll, pid, mapping, product.get("table"))
    return out + participation_problems(root)


def participation_problems(root: Path = REPO) -> list[str]:
    """REQ-QAC-294 criterion 11, generic: a dataset linking ONE source with no
    code is a product built from that source's supply for the period, so it
    owes exactly the periods its source owes - each side read after its own
    collection's files_go_to_period (REQ-PIPE-321), through the one schedule.
    Names the dataset and the first period they disagree."""
    from qa_tools.common import agreement, schedule

    asset = _load(_asset_folder(root) / "data-asset.yaml") or {}
    path = _asset_folder(root) / "calendar.yaml"
    if not path.exists():
        return []
    try:
        agr = agreement.load(path)
    except schedule.ScheduleConfigError:
        return []  # the schedule gate reports a calendar that cannot be read
    out = []
    for _agency, _coll, product in _walk(asset):
        linked = product.get("linked_datasets") or []
        if len(linked) != 1 or linked[0].get("code") is not None:
            continue
        pid, src = product.get("id"), linked[0].get("dataset")
        try:
            mine = {p.name: p.date for p in schedule.periods_for_dataset(pid, agreement=agr)
                    if p.expected}
            theirs = {p.name: p.date for p in schedule.periods_for_dataset(src, agreement=agr)
                      if p.expected}
        except (schedule.ScheduleConfigError, LookupError, ValueError):
            continue  # problems() and the schedule gate say why it cannot be read
        differ = set(mine) ^ set(theirs)
        if not differ:
            continue
        first = min(differ, key=lambda n: ((mine | theirs)[n], n))
        owes = "owes" if first in mine else "does not owe"
        out.append(f"{pid} {owes} {first}, which its source {src} "
                   f"{'does not' if first in mine else 'does'} - a product built from one "
                   f"source owes exactly the periods the source owes (REQ-QAC-294 criterion 11).")
    return out


def _check_problems(root: Path, coll: dict, pid: str, mapping: dict, table: str) -> list[str]:
    """REQ-QAC-333 criteria 3 and 8: each hand-written check agrees with the
    mapping, and each linked dataset has both its checks.

    SCOPED TO THE DECLARING DATASET'S OWN BLOCK (REQ-QAC-294 criterion 5):
    only 'checks for <table>' is read, so one dataset's checks can neither
    satisfy nor break another's - a geocoding check naming cp-clients never
    counts toward the linkage product's pair. An id_counts key is a code, or
    the source dataset's id where the entry has none."""
    stem = str(coll.get("contract", "")).rsplit("/", 1)[-1].removesuffix("-contract.yaml")
    folder = str(coll.get("contract", "")).rsplit("/", 1)[0]
    path = _asset_folder(root) / folder / f"{stem}-soda-checks.yml"
    out: list[str] = []
    have: dict[str, set] = {did: set() for did in mapping}
    for check_id, attrs, body, check_key in _soda_items(path, table):
        did = attrs.get("linked_dataset")
        if did is not None:
            if did not in mapping:
                out.append(f"check {check_id} names {did!r}, which is not declared as linked by {pid}.")
                continue
            code, cols = mapping[did]
            if "linkage_code" in attrs and attrs["linkage_code"] != code:
                out.append(f"check {check_id} states the code {attrs['linkage_code']!r} for {did}; "
                           f"the mapping declares {code!r}.")
            if "id_columns" in attrs and list(attrs["id_columns"]) != cols:
                out.append(f"check {check_id} states the identifier columns {list(attrs['id_columns'])} "
                           f"for {did}; the mapping declares {cols}.")
            if attrs.get("linked_check"):
                have[did].add(attrs["linked_check"])
        for code, k in (attrs.get("id_counts") or {}).items():
            did = next((d for d, (c, _cols) in mapping.items()
                        if (c if c is not None else d) == code), None)
            want = len(mapping[did][1]) if did else None
            if want is None:
                out.append(f"check {check_id} states an identifier count for the code {code!r}, "
                           f"which no linked dataset declares.")
            elif int(k) != want:
                out.append(f"check {check_id} states {k} identifier(s) for {code} ({did}); "
                           f"the mapping declares {want}.")
        out += _query_problems(check_id, body, mapping, attrs.get("linked_dataset"), check_key)
        codes = attrs.get("linkage_codes")
        if codes is not None and sorted(codes) != sorted(c for c, _cols in mapping.values() if c):
            out.append(f"check {check_id} states the codes {sorted(codes)}; the mapping declares "
                       f"{sorted(c for c, _cols in mapping.values() if c)}.")
    for did, kinds in have.items():
        for kind in ("referential", "coverage"):
            if kind not in kinds:
                out.append(f"{pid} links {did!r} without its {kind} check (REQ-QAC-333 criterion 8).")
    return out
