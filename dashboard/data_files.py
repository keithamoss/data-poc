"""The dashboard's data files (REQ-DASH-291, REQ-DASH-292, REQ-DASH-293).

WHY THE PAGE IS SPLIT. Cloudflare Pages serves no file over 25 MiB, and the
built page reached 20.62 MiB with three collections (2026-10-24) - roughly
thirty are coming. So each collection's COLLECTION_DATA entry, and the
Requirements and Plans data together, are written as sibling files under
dashboard/data/ that the page loads with a plain classic <script src>. Not
fetch() or XMLHttpRequest: both are refused under file://, which is the
supported way to open the page locally (the template's DEMO_CAST comment
records the same reason). Every other const stays inline - about 1 MiB in
all, and moving it would add files without solving anything.

WHAT A FILE IS. One line of JavaScript that registers ONE STRING - the
payload's JSON text, or one part of it - and the build id it was written
for, under its own key:

    (window.MOTHMAN_DATA=window.MOTHMAN_DATA||{})["collection-x#1"]={build:"...",text:'...'};

The page joins a key's parts in order and JSON.parses the joined text once,
which browsers do markedly faster than parsing the same data as an object
literal. The string is single-quoted with `\\`, `'` and `<` escaped, so a
file holds no `<` at all and a snapshot can inline it inside a <script>
element byte for byte (REQ-DASH-292) - the split back is then exact by
construction rather than by care.

NAMED FROM ITS CONTENT: `<key>.<12 hex of its SHA-256>.js`, or
`<key>.part<n>.<hash>.js` for a payload past the budget (REQ-DASH-293), so
two builds of the same content write the same names and any change makes a
new one. A stale cached file can never stand in for a new one, and wrangler
re-sends only what changed.

THE BUILD ID IS THE PAYLOAD'S, NOT THE PAGE'S (PROVISIONAL, not put to
Keith). Each file carries the id of the payload it was written for - the
first 12 hex digits of the SHA-256 of that payload's whole text, shared by
its parts - and the page's list names the id it expects for each file. An
id taken from the whole build would change every file whenever any one
collection changed, so a publish would re-send every collection; a random
or time-based id would make two identical builds write different bytes,
which REQ-DASH-291 criterion 16 forbids. The list's own `build` is the
page's id, derived from every file it lists.

ONE READER. read_page() returns a built page's data whether it sits in
sibling files or inlined in a snapshot, so the render gate, the snapshot
step and the tests cannot drift on what "the page's data" is (criterion
13).
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

MIB = 1024 * 1024
#: REQ-DASH-293: no data file the dashboard writes exceeds this. 40% of
#: Cloudflare Pages' per-file limit, so REQ-PIPE-255's 20 MiB warning and
#: 25 MiB refusal stay backstops a data file never reaches. A constant here
#: rather than a setting in contract/: it follows the hosting provider, not a
#: data asset's configuration.
BUDGET_BYTES = 10 * MIB
#: REQ-PIPE-255 criteria 13, 14 and 26: Cloudflare Pages' per-file ceiling,
#: and the size at which a build warns about it.
LIMIT_BYTES = 25 * MIB
WARN_BYTES = 20 * MIB

DATA_DIR = "data"
REGISTRY = "MOTHMAN_DATA"
COLLECTION_KIND = "collection"
REQUIREMENTS_PLANS_KEY = "requirements-plans"
#: Where the build writes the static <script src> elements, in the template
#: immediately before the main inline script. The raw template carries the
#: marker and no data script tags (REQ-DASH-291 decision).
MARKER = "<!-- mothman:data-files -->\n"

_TAG_RE = re.compile(r'<script src="([^"]*)" data-mothman-key="([^"]+)" '
                     r'data-mothman-file="([^"]+)"></script>\n')
_BLOCK_RE = re.compile(r'<script( type="text/plain")? data-mothman-key="([^"]+)" '
                       r'data-mothman-file="([^"]+)">(.*?)</script>\n', re.DOTALL)
_FILE_RE = re.compile(r'\(window\.MOTHMAN_DATA=window\.MOTHMAN_DATA\|\|\{\}\)\["(.+)#(\d+)"\]='
                      r'\{build:"([0-9a-f]+)",text:\'(.*)\'\};\n', re.DOTALL)
_MANIFEST_RE = re.compile(r"const DATA_FILES = (.*?);\n")


class DataFileError(RuntimeError):
    """A built page's data files are missing or not the ones it lists."""

    def __init__(self, problems: list[str]):
        self.problems = problems
        super().__init__("; ".join(problems))


@dataclass
class DataFile:
    entry: dict
    content: bytes


@dataclass
class Decoded:
    key: str
    part: int
    build: str
    text: str


@dataclass
class PageData:
    manifest: dict | None
    contents: dict = field(default_factory=dict)
    problems: list = field(default_factory=list)
    collections: dict | None = None
    requirements: list | None = None
    plans: dict | None = None


def collection_key(collection_id: str) -> str:
    return f"collection-{collection_id}"


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("'", "\\'").replace("<", "\\x3c")


def _escaped_len(text: str, start: int, end: int) -> int:
    return ((end - start) + text.count("\\", start, end) + text.count("'", start, end)
            + 3 * text.count("<", start, end))


def _file_bytes(key: str, part: int, build: str, chunk: str) -> bytes:
    return (f'(window.{REGISTRY}=window.{REGISTRY}||{{}})["{key}#{part}"]='
            f"{{build:\"{build}\",text:'{_escape(chunk)}'}};\n").encode("ascii")


def payload_text(payload) -> str:
    # ensure_ascii (the default) on purpose: an ASCII file has one byte per
    # character, so the budget is a character count and nothing about the
    # bytes depends on an encoding.
    return json.dumps(payload, separators=(",", ":"))


def encode(key: str, payload, *, kind: str, collection: str | None = None,
           budget: int | None = None) -> list[DataFile]:
    """The file or files that carry one payload."""
    return encode_text(key, payload_text(payload), kind=kind, collection=collection,
                       budget=budget)


def encode_text(key: str, text: str, *, kind: str, collection: str | None = None,
                budget: int | None = None) -> list[DataFile]:
    budget = BUDGET_BYTES if budget is None else budget
    if not text.isascii() or "\n" in text or "\r" in text:
        raise ValueError(f"{key}: a payload's text must be single-line ASCII JSON")
    build = _sha(text.encode("ascii"))[:12]

    def fits(part: int, start: int, end: int) -> bool:
        return len(_file_bytes(key, part, build, "")) + _escaped_len(text, start, end) <= budget

    chunks: list[str] = []
    start = 0
    while start < len(text) or not chunks:
        part = len(chunks) + 1
        if fits(part, start, len(text)):
            end = len(text)
        else:
            lo, hi = start, len(text)
            while lo < hi:
                mid = (lo + hi + 1) // 2
                if fits(part, start, mid):
                    lo = mid
                else:
                    hi = mid - 1
            end = lo
            if end == start:
                raise ValueError(f"{key}: a budget of {budget} bytes cannot hold any of its payload")
        chunks.append(text[start:end])
        start = end

    out = []
    for i, chunk in enumerate(chunks, start=1):
        content = _file_bytes(key, i, build, chunk)
        digest = _sha(content)
        name = (f"{key}.{digest[:12]}.js" if len(chunks) == 1
                else f"{key}.part{i}.{digest[:12]}.js")
        entry = {"key": key, "kind": kind, "part": i, "parts": len(chunks), "name": name,
                 "bytes": len(content), "sha256": digest, "build": build}
        if collection is not None:
            entry["collection"] = collection
        out.append(DataFile(entry, content))
    return out


def decode(content: bytes) -> Decoded:
    m = _FILE_RE.fullmatch(content.decode("ascii"))
    if not m:
        raise ValueError("not a dashboard data file")
    text = re.sub(r"\\(x3c|.)", lambda e: "<" if e.group(1) == "x3c" else e.group(1), m.group(4))
    return Decoded(m.group(1), int(m.group(2)), m.group(3), text)


def manifest(files: list[DataFile]) -> dict:
    """The page's one list of the files it expects (criterion 4)."""
    entries = [f.entry for f in files]
    page_build = _sha(json.dumps([[e["key"], e["part"], e["sha256"]] for e in entries])
                      .encode())[:12]
    return {"build": page_build, "files": entries}


def _tags(entries: list[dict], prefix: str) -> str:
    return "".join(f'<script src="{prefix}/{e["name"]}" data-mothman-key="{e["key"]}" '
                   f'data-mothman-file="{e["name"]}"></script>\n'
                   for e in entries if e["kind"] == COLLECTION_KIND)


def _replace_once(html: str, old: str, new: str, what: str) -> str:
    if html.count(old) != 1:
        raise RuntimeError(f"expected exactly one {what} in the page, found {html.count(old)} - "
                           "has the dashboard's structure changed?")
    return html.replace(old, new)


def _set_manifest(html: str, value: dict) -> str:
    found = _MANIFEST_RE.findall(html)
    if len(found) != 1:
        raise RuntimeError(f"expected exactly one 'const DATA_FILES = ...;' line, found {len(found)}")
    line = f"const DATA_FILES = {json.dumps(value, separators=(',', ':'))};\n"
    return _MANIFEST_RE.sub(lambda _m: line, html, count=1)


def embed_into_page(html: str, value: dict, prefix: str = DATA_DIR) -> str:
    """The template with its list of expected files, the expression that
    assembles COLLECTION_DATA from them, and one classic <script src> per
    collection file before the main inline script."""
    html = _set_manifest(html, value)
    html = _replace_once(html, "const COLLECTION_DATA = null;\n",
                         "const COLLECTION_DATA = assembleCollectionData();\n",
                         "'const COLLECTION_DATA = null;' line")
    return _replace_once(html, MARKER, MARKER + _tags(value["files"], prefix),
                         "data-file marker")


def page_manifest(html: str) -> dict | None:
    # Searched with the inline blocks taken out: a block is data, and the
    # Requirements block quotes this very line (found 2026-10-24, when the
    # register gained a decision naming it and the snapshot read the quote).
    m = _MANIFEST_RE.search(_BLOCK_RE.sub("", html))
    return json.loads(m.group(1)) if m else None


def _assemble(entries: list[dict], decoded: dict) -> dict:
    """{key: parsed payload}, each key's parts joined in order."""
    texts: dict[str, list] = {}
    for e in entries:
        texts.setdefault(e["key"], []).append((e["part"], decoded[e["name"]].text))
    return {k: json.loads("".join(t for _, t in sorted(v))) for k, v in texts.items()}


def _legacy(html: str) -> PageData:
    """A page with its data in consts - the raw template's shape, a page
    built before REQ-DASH-291, or an archived snapshot from before it."""
    out = PageData(manifest=None)
    m = re.search(r"const COLLECTION_DATA = (.*?);\n", html)
    if not m:
        out.problems.append("COLLECTION_DATA: no embedded const found in the built HTML")
    else:
        try:
            out.collections = json.loads(m.group(1))
        except json.JSONDecodeError as e:
            out.problems.append(f"COLLECTION_DATA: embedded data isn't valid JSON - {e}")
    for name, attr in (("REQUIREMENTS", "requirements"), ("PLANS", "plans")):
        m = re.search(rf"(?:const|let) {name} = (.*?);\n", html)
        if m:
            try:
                setattr(out, attr, json.loads(m.group(1)))
            except json.JSONDecodeError:
                pass
    return out


def read_page(html: str, page_dir: Path) -> PageData:
    """A built page's data, from its sibling files or its inline blocks."""
    value = page_manifest(html)
    if not value:
        return _legacy(html)
    page_dir = Path(page_dir)
    blocks = {m.group(3): m.group(4).encode("ascii") for m in _BLOCK_RE.finditer(html)}
    srcs = {m.group(3): m.group(1) for m in _TAG_RE.finditer(html)}
    default_dir = next((s[: -len(n)] for n, s in srcs.items()), DATA_DIR + "/")
    out = PageData(manifest=value)
    decoded = {}
    for e in value["files"]:
        name = e["name"]
        if name in blocks:
            content = blocks[name]
        else:
            path = page_dir / (srcs.get(name) or (default_dir + name))
            if not path.is_file():
                out.problems.append(f"{name}: missing - the page lists it and there is no {path}")
                continue
            content = path.read_bytes()
        if _sha(content) != e["sha256"]:
            out.problems.append(f"{name}: its SHA-256 differs from the page's list")
            continue
        try:
            d = decode(content)
        except ValueError:
            out.problems.append(f"{name}: not a dashboard data file")
            continue
        if (d.key, d.part, d.build) != (e["key"], e["part"], e["build"]):
            out.problems.append(f"{name}: registers as {d.key}#{d.part} from build {d.build}, "
                                f"not {e['key']}#{e['part']} from build {e['build']}")
            continue
        out.contents[name] = content
        decoded[name] = d
    if out.problems:
        return out
    assembled = _assemble(value["files"], decoded)
    out.collections = {}
    for e in value["files"]:
        if e["kind"] == COLLECTION_KIND:
            out.collections.setdefault(e["collection"], assembled[e["key"]])
    rp = assembled.get(REQUIREMENTS_PLANS_KEY)
    if rp is not None:
        out.requirements, out.plans = rp.get("requirements"), rp.get("plans")
    return out


def _strip_data_elements(html: str) -> str:
    return _BLOCK_RE.sub("", _TAG_RE.sub("", html))


def inline(html: str, page_dir: Path) -> str:
    """The page with every data file it lists inlined in place of its
    script element, each block marked with the file's key and name
    (REQ-DASH-292 criterion 1). A collection file becomes an executing
    block; the Requirements and Plans file an inert `text/plain` one that
    the page runs on demand, exactly as it would load the file. Refuses,
    naming each file, when any is missing or differs from the list
    (criterion 3). A page with no list is returned unchanged."""
    data = read_page(html, page_dir)
    if data.manifest is None:
        return html
    if data.problems:
        raise DataFileError(data.problems)
    blocks = []
    for e in data.manifest["files"]:
        inert = "" if e["kind"] == COLLECTION_KIND else ' type="text/plain"'
        blocks.append(f'<script{inert} data-mothman-key="{e["key"]}" data-mothman-file="{e["name"]}">'
                      f'{data.contents[e["name"]].decode("ascii")}</script>\n')
    return _replace_once(_strip_data_elements(html), MARKER, MARKER + "".join(blocks),
                         "data-file marker")


def split(html: str, files_dir: str, budget: int | None = None) -> tuple[str, dict]:
    """An inlined page split back into a page and its files (REQ-DASH-292
    criteria 4 to 6): each block written back out byte for byte, the page's
    script elements pointing at `files_dir`. A block over the budget - only
    possible if the budget was lowered after the snapshot was taken - is
    re-written as parts within it, and the page's list updated to match. A
    page with no blocks is returned unchanged."""
    budget = BUDGET_BYTES if budget is None else budget
    blocks = {m.group(3): m.group(4).encode("ascii") for m in _BLOCK_RE.finditer(html)}
    value = page_manifest(html)
    if not blocks or not value:
        return html, {}
    entries, files = [], {}
    by_key: dict[str, list] = {}
    for e in value["files"]:
        by_key.setdefault(e["key"], []).append(e)
    for key, group in by_key.items():
        contents = [blocks[e["name"]] for e in group]
        if all(len(c) <= budget for c in contents):
            entries += group
            files.update({e["name"]: c for e, c in zip(group, contents)})
            continue
        text = "".join(decode(c).text for c in contents)
        first = group[0]
        for f in encode_text(key, text, kind=first["kind"], collection=first.get("collection"),
                             budget=budget):
            entries.append(f.entry)
            files[f.entry["name"]] = f.content
    out = _strip_data_elements(html)
    if entries != value["files"]:
        out = _set_manifest(out, {**value, "files": entries})
    out = _replace_once(out, MARKER, MARKER + _tags(entries, files_dir), "data-file marker")
    return out, files


def write(files: list[DataFile], data_dir: Path) -> list[Path]:
    data_dir = Path(data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    out = []
    for f in files:
        path = data_dir / f.entry["name"]
        if not (path.is_file() and path.read_bytes() == f.content):
            path.write_bytes(f.content)
        out.append(path)
    return out


def prune(data_dir: Path, keep: list[str]) -> list[Path]:
    """Remove every file directly in `data_dir` the new page does not
    reference (REQ-DASH-291 criterion 11) - nothing outside it."""
    data_dir = Path(data_dir)
    if not data_dir.is_dir():
        return []
    removed = []
    for path in sorted(data_dir.iterdir()):
        if path.is_file() and path.name not in keep:
            path.unlink()
            removed.append(path)
    return removed


def _mib(n: int) -> str:
    return f"{n / MIB:.2f} MiB"


def size_report(page: Path, files: list[Path]) -> list[tuple[str, str]]:
    """Every file a build wrote, with its size (REQ-DASH-293 criterion 4,
    REQ-PIPE-255 criterion 26): a warning at or above the 10 MiB budget, and
    one naming the 25 MiB limit at or above 20 MiB. Lines, not prints, so
    the caller chooses how to show them; nothing here stops a build."""
    out = []
    for path in [Path(page), *map(Path, files)]:
        size = path.stat().st_size
        out.append(("info", f"{path.name}: {_mib(size)}"))
        if size >= WARN_BYTES:
            out.append(("warn", f"WARNING: {path.name} is {_mib(size)}, close to Cloudflare Pages' "
                                f"{LIMIT_BYTES // MIB} MiB per-file limit"))
        elif size >= BUDGET_BYTES:
            out.append(("warn", f"WARNING: {path.name} is {_mib(size)}, at or over the "
                                f"{BUDGET_BYTES // MIB} MiB budget"))
    return out


#: REQ-PIPE-255 criterion 22: values that change on every build without
#: changing what a reader sees. A newly found volatile field is added here.
VOLATILE_CONSTS = ("BUILT_AT", "BUILD_PROVENANCE", "SNAPSHOT_MANIFEST")


def _normalised(html: str) -> str:
    html = _strip_data_elements(html)
    for name in VOLATILE_CONSTS:
        html = re.sub(rf"const {name} = .*?;\n", f'const {name} = "<volatile>";\n', html, count=1)
    return re.sub(r'"generated_at":"[^"]*"', '"generated_at":"<volatile>"', html)


def fingerprint(html: str, page_dir: Path, static_dirs: list[Path] = ()) -> str:
    """REQ-PIPE-255 criterion 22: one SHA-256 over the page with its
    volatile values blanked, every data file it lists - from disk or from
    its inline blocks, through read_page(), so a built page and its archived
    snapshot fingerprint the same way - and every file under `static_dirs`
    (fonts/ and vendor/)."""
    data = read_page(html, page_dir)
    if data.problems and data.manifest is not None:
        raise DataFileError(data.problems)
    h = hashlib.sha256(_normalised(html).encode("utf-8"))
    for e in (data.manifest or {}).get("files", []):
        h.update(e["name"].encode() + b"\0" + data.contents[e["name"]])
    for d in static_dirs:
        d = Path(d)
        if not d.is_dir():
            continue
        for path in sorted(p for p in d.rglob("*") if p.is_file()):
            h.update(f"{d.name}/{path.relative_to(d).as_posix()}".encode() + b"\0" + path.read_bytes())
    return h.hexdigest()
