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

REPO = Path(__file__).resolve().parent.parent.parent
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
    doc = _load(root / "contract" / contract) or {}
    for t in doc.get("schema") or []:
        if t.get("name") == table:
            return [p.get("name") for p in t.get("properties") or []]
    return []


def _soda_checks(path: Path) -> list[tuple[str, dict]]:
    """(check_id, attributes) for every Soda check in a file."""
    return [(cid, attrs) for cid, attrs, _body in _soda_bodies(path)]


def _soda_bodies(path: Path) -> list[tuple[str, dict, dict]]:
    """(check_id, attributes, the check's whole body) for every Soda check."""
    doc = _load(path) or {}
    out = []
    for key, checks in doc.items():
        if not str(key).startswith("checks for"):
            continue
        for item in checks or []:
            if isinstance(item, dict):
                for body in item.values():
                    attrs = (body or {}).get("attributes") or {} if isinstance(body, dict) else {}
                    if attrs.get("check_id"):
                        out.append((attrs["check_id"], attrs, body))
    return out


_CAST = re.compile(r"CAST\(\s*([\w.]+)\s+AS\s+TEXT\s*\)", re.IGNORECASE)
_EQ = re.compile(r"([\w.]+)\s*=\s*([\w.]+)")
_CODE = re.compile(r"\bdataset\s*=\s*'([^']*)'", re.IGNORECASE)


def _queries(body: dict) -> list[str]:
    """The SQL a Soda check runs: its fail query, or its metric's query."""
    return [v for k, v in body.items() if isinstance(v, str) and k.endswith("query")]


def _query_problems(check_id: str, body: dict, mapping: dict, did: str | None) -> list[str]:
    """REQ-QAC-333 criterion 3 against WHAT RUNS: every dataset code a query
    or a valid-values list states is one the mapping declares (the linked
    dataset's own, for a referential or coverage check); and every identifier
    a referential or coverage query compares is the mapping's column for that
    id, cast to text."""
    codes = {c for c, _cols in mapping.values()}
    out = []
    values = body.get("valid values")
    if isinstance(values, list) and sorted(values) != sorted(codes):
        out.append(f"check {check_id} states the valid values {sorted(values)}; the mapping "
                   f"declares {sorted(codes)}.")
    for sql in _queries(body):
        for stated in _CODE.findall(sql):
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


def problems(root: Path = REPO) -> list[str]:
    asset = _load(root / "contract" / "data-asset.yaml") or {}
    cal = _load(root / "contract" / "calendar.yaml") or {}
    where = {ds.get("id"): (agency, coll, ds) for agency, coll, ds in _walk(asset)}
    out: list[str] = []
    for agency, coll, product in _walk(asset):
        linked = product.get("linked_datasets") or []
        if not linked:
            continue
        pid = product.get("id")
        product_cal = _calendar_of(cal, coll.get("id"), pid)
        own = _columns(root, coll.get("contract", ""), product.get("table"))
        n = max((int(m.group(1)) for c in own if (m := _ID.match(c or ""))), default=0)
        by_code: dict[str, str] = {}
        mapping: dict[str, tuple[str, list[str]]] = {}
        for entry in linked:
            did, code, cols = entry.get("dataset"), entry.get("code"), list(entry.get("id_columns") or [])
            head = f"{pid} links {did!r}"
            if code in by_code:
                out.append(f"{head}: two linked datasets declare the code {code!r} "
                           f"({by_code[code]!r} and {did!r}) - every row's dataset would be ambiguous.")
            by_code.setdefault(code, did)
            if did not in where:
                out.append(f"{head}, which is not in the hierarchy (contract/data-asset.yaml).")
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
        out += _check_problems(root, coll, pid, mapping)
    return out


def _check_problems(root: Path, coll: dict, pid: str, mapping: dict) -> list[str]:
    """REQ-QAC-333 criteria 3 and 8: each hand-written check agrees with the
    mapping, and each linked dataset has both its checks."""
    stem = str(coll.get("contract", "")).rsplit("/", 1)[-1].removesuffix("-contract.yaml")
    folder = str(coll.get("contract", "")).rsplit("/", 1)[0]
    path = root / "contract" / folder / f"{stem}-soda-checks.yml"
    out: list[str] = []
    have: dict[str, set] = {did: set() for did in mapping}
    for check_id, attrs, body in _soda_bodies(path):
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
            did = next((d for d, (c, _cols) in mapping.items() if c == code), None)
            want = len(mapping[did][1]) if did else None
            if want is None:
                out.append(f"check {check_id} states an identifier count for the code {code!r}, "
                           f"which no linked dataset declares.")
            elif int(k) != want:
                out.append(f"check {check_id} states {k} identifier(s) for {code} ({did}); "
                           f"the mapping declares {want}.")
        out += _query_problems(check_id, body, mapping, attrs.get("linked_dataset"))
        codes = attrs.get("linkage_codes")
        if codes is not None and sorted(codes) != sorted(c for c, _cols in mapping.values()):
            out.append(f"check {check_id} states the codes {sorted(codes)}; the mapping declares "
                       f"{sorted(c for c, _cols in mapping.values())}.")
    for did, kinds in have.items():
        for kind in ("referential", "coverage"):
            if kind not in kinds:
                out.append(f"{pid} links {did!r} without its {kind} check (REQ-QAC-333 criterion 8).")
    return out
