"""An extraction arrives as a PACKAGE - one recipe file and the data files it
names - and the recipe is ours to define (REQ-PIPE-439).

THE RECIPE IS UNTRUSTED INPUT (the SECURITY NFR). It is parsed as data against
the schema committed beside this module (extraction-recipe.schema.json, format
version 1), its filter text is kept as text and never executed, and a file it
names that would escape the package is refused. NOTHING HERE OPENS A DATABASE
(criterion 8): the recipe lives beside the package, and what it declares is
carried into the generated folder (REQ-PIPE-440), which is configuration.

A PACKAGE IS A DIRECTORY ON LOCAL DISK OR AN S3 PREFIX (criterion 1). S3 is
read through a client the caller hands in, with the environment's own
credentials (the PORTABILITY NFR) - this module creates none.

CSV ONLY IN FORMAT VERSION 1 (criterion 5): staging is CSV-only, so another
format would be new work; version 1 says so rather than half-supporting one.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

#: The recipe's file name in a package.
RECIPE_FILE = "recipe.json"
#: The recipe format versions this checkout reads.
FORMAT_VERSIONS = (1,)
#: The file formats format version 1 accepts.
FORMATS_V1 = ("csv",)
SCHEMA_PATH = Path(__file__).with_name("extraction-recipe.schema.json")


class RecipeRefused(ValueError):
    """The package cannot be opened. Its message names every problem found."""

    def __init__(self, problems: list[str]):
        self.problems = list(problems)
        super().__init__("the package was refused, and nothing was generated or loaded:\n"
                         + "\n".join(f"  - {p}" for p in self.problems))


@dataclass(frozen=True)
class Column:
    name: str
    type: str
    primary_identifier: bool


@dataclass(frozen=True)
class Bound:
    column: str
    lower: object
    upper: object


@dataclass(frozen=True)
class Table:
    file: str
    format: str
    agency_id: str
    agency_name: str
    collection_id: str
    collection_name: str
    dataset_id: str
    dataset_name: str
    table: str
    derived: bool
    columns: tuple[Column, ...]
    cohort: tuple[Bound, ...]
    expected_rows: int | None = None


@dataclass(frozen=True)
class Recipe:
    format_version: int
    extraction_id: str
    project: str
    filter: str
    tables: tuple[Table, ...]
    #: sha256 of the recipe file's bytes - what the generated folder records
    #: (REQ-PIPE-440 criteria 2 and 8).
    digest: str


@dataclass(frozen=True)
class Package:
    """Where the package is, its recipe, and every file it holds."""

    location: str
    recipe: Recipe
    files: tuple[str, ...]


# ---- where a package's files come from --------------------------------------

class _Local:
    def __init__(self, root: Path):
        self.root = Path(root)

    def exists(self) -> bool:
        return self.root.is_dir()

    def names(self) -> list[str]:
        return sorted(p.relative_to(self.root).as_posix()
                      for p in self.root.rglob("*") if p.is_file())

    def read(self, name: str) -> bytes:
        return (self.root / name).read_bytes()


class _S3:
    """An S3 prefix, through a client the caller hands in."""

    def __init__(self, uri: str, client):
        rest = uri[len("s3://"):]
        self.bucket, _, prefix = rest.partition("/")
        self.prefix = prefix.rstrip("/") + "/" if prefix else ""
        self.client = client

    def exists(self) -> bool:
        return bool(self.names())

    def names(self) -> list[str]:
        out, token = [], None
        while True:
            kw = {"Bucket": self.bucket, "Prefix": self.prefix}
            if token:
                kw["ContinuationToken"] = token
            page = self.client.list_objects_v2(**kw)
            out += [o["Key"][len(self.prefix):] for o in page.get("Contents") or []
                    if not o["Key"].endswith("/")]
            token = page.get("NextContinuationToken")
            if not page.get("IsTruncated"):
                return sorted(out)

    def read(self, name: str) -> bytes:
        return self.client.get_object(Bucket=self.bucket, Key=self.prefix + name)["Body"].read()


def _source(location: str, s3_client=None):
    if str(location).startswith("s3://"):
        if s3_client is None:
            raise RecipeRefused([f"{location} is an S3 prefix, and no S3 client was given to "
                                 f"read it with the environment's credentials."])
        return _S3(str(location), s3_client)
    return _Local(Path(location))


def source(location: str, s3_client=None):
    """Where a package's files are read from - `.names()` and `.read(name)`
    over a local directory or an S3 prefix - for the load (REQ-PIPE-442)."""
    return _source(location, s3_client)


# ---- reading ----------------------------------------------------------------

def _schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text())


def _escapes(name: str) -> bool:
    """Whether a file name a recipe gives would leave the package directory -
    absolute, a backslash, or any '..' part."""
    if not name or "\\" in name or PurePosixPath(name).is_absolute():
        return True
    return ".." in PurePosixPath(name).parts


def _id_problems(extraction_id: str) -> list[str]:
    """Criterion 7: the id's shape, and a folder it would clash with."""
    from asset_model import assets

    if not assets.NAME_PATTERN.fullmatch(extraction_id or ""):
        return [f"extraction_id {extraction_id!r} is not lowercase letters, digits and single "
                f"hyphens."]
    clash = []
    if extraction_id in assets.names():
        clash.append(str(assets.ROOT / "assets" / extraction_id))
    clash += [str(assets.one_offs_root() / k / n) for k, n in assets.one_offs()
              if n == extraction_id]
    return ([f"extraction_id {extraction_id!r} is already a folder: {', '.join(clash)}. A "
             f"re-send is a new extraction, with an id of its own."] if clash else [])


def read(location: str, *, s3_client=None, opening: bool = True) -> Package:
    """The package at `location` - a local directory or an s3:// prefix -
    with its recipe read and validated, or RecipeRefused naming every problem
    (criteria 1 to 7). Reads files only; never opens a database.

    `opening` False is the LOAD's read (REQ-PIPE-442), of a package whose
    folder is already generated: criterion 7's clash with an existing folder is
    the open's refusal, and the load's own folder is that folder."""
    from jsonschema import Draft202012Validator

    source = _source(location, s3_client)
    if not source.exists():
        raise RecipeRefused([f"{location}: no package there."])
    files = source.names()
    if RECIPE_FILE not in files:
        raise RecipeRefused([f"{location}: no {RECIPE_FILE} - a package is one recipe and the "
                             f"data files it names."])
    raw = source.read(RECIPE_FILE)
    try:
        doc = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RecipeRefused([f"{RECIPE_FILE} does not parse as JSON: {exc}"]) from None
    version = doc.get("recipe_format_version") if isinstance(doc, dict) else None
    if isinstance(doc, dict) and version is not None and version not in FORMAT_VERSIONS:
        raise RecipeRefused([f"recipe_format_version {version!r} is not one this checkout "
                             f"reads ({', '.join(map(str, FORMAT_VERSIONS))})."])
    problems = [f"{RECIPE_FILE}: {'/'.join(map(str, e.absolute_path)) or '(top)'}: {e.message}"
                for e in sorted(Draft202012Validator(_schema()).iter_errors(doc),
                                key=lambda e: list(map(str, e.absolute_path)))]
    if problems:
        raise RecipeRefused(problems)
    tables = []
    for t in doc["tables"]:
        where = f"table {t['dataset']['table']!r}"
        if t["format"] not in FORMATS_V1:
            problems.append(f"{where}: format {t['format']!r} - recipe format version 1 "
                            f"reads {', '.join(FORMATS_V1)} only.")
        if _escapes(t["file"]):
            problems.append(f"{where}: file {t['file']!r} would leave the package directory.")
        tables.append(Table(
            file=t["file"], format=t["format"],
            agency_id=t["agency"]["id"], agency_name=t["agency"]["name"],
            collection_id=t["collection"]["id"], collection_name=t["collection"]["name"],
            dataset_id=t["dataset"]["id"], dataset_name=t["dataset"]["name"],
            table=t["dataset"]["table"], derived=t["derived"],
            columns=tuple(Column(c["name"], c["type"], c["primary_identifier"])
                          for c in t["columns"]),
            cohort=tuple(Bound(b["column"], b["lower"], b["upper"]) for b in t["cohort"]),
            expected_rows=t.get("expected_rows")))
    problems += (_id_problems(doc["extraction_id"]) if opening else
                 [p for p in _id_problems(doc["extraction_id"]) if "already a folder" not in p])
    if problems:
        raise RecipeRefused(problems)
    recipe = Recipe(format_version=doc["recipe_format_version"],
                    extraction_id=doc["extraction_id"], project=doc["project"],
                    filter=doc["filter"], tables=tuple(tables),
                    digest=hashlib.sha256(raw).hexdigest())
    return Package(location=str(location), recipe=recipe, files=tuple(files))


def recipe_digest(location: str, *, s3_client=None) -> str:
    """sha256 of the recipe file beside a package, as it reads now
    (REQ-PIPE-440 criterion 8)."""
    return hashlib.sha256(_source(location, s3_client).read(RECIPE_FILE)).hexdigest()
