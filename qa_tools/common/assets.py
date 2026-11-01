"""Which data asset this process acts for, and where everything for it lives
(REQ-PIPE-342 criteria 5 to 7, REQ-PIPE-363 criterion 1).

ONE RESOLVER, CALLED AT CALL TIME. Every reader that wants an asset-wide file
(data-asset.yaml, calendar.yaml, ...), the asset's QA adapters, its generator
providers, its dbt project or one of its state paths under data/ and reports/
asks this module when it needs the answer, never at import. A module-level
path constant is an import-time default, and a module imported before a test
selects its asset would keep the wrong folder (REQ-PIPE-342's decision on call
time; REJECTED keeping the constants and pointing them per asset).

THE ASSET IS NAMED BY MOTHMAN_ASSET, WITH NO DEFAULT (REQ-PIPE-363 criterion
1), beside MOTHMAN_ENVIRONMENT and MOTHMAN_SUPPLY_DSN, on REQ-PIPE-091's
precedent. Unset or naming no asset folder is refused in the form
environments.current() refuses for the environment, listing the folder names
found - the only thing read before an asset is selected. Never the only asset
present, never a last-used value.

TWO LAYOUTS, AND THE SWITCH BETWEEN THEM IS THE MOVE (REQ-TEST-357 criteria 5
and 6). Until the move, `_PreMove` maps today's tree as one asset: contract/
is its folder, qa_tools/collections/ and generator/collections/ hold its
adapters and providers, dbt_project/ is its dbt project, and data/ and
reports/ are its state. Until REQ-QAC-344 renames it, that one asset is named
data-asset-1, as its data-asset.yaml declares (decided 2026-11-01). The move
commit points `_DEFAULT` at `_Assets(ROOT / "assets")`, where each asset
folder is found from assets/ itself (criterion 5) and no code names an asset.

ADAPTERS AND PROVIDERS ARE LOADED BY PATH (REQ-PIPE-369 criterion 2,
REQ-GEN-370 criterion 2), through importlib's file-location loader, under a
module name built from the asset and the module - never a module path taken
from configuration, never an asset folder on sys.path, never an __init__.py
in an asset folder. So a deployment can supply an asset folder from outside
this repository (#55) without renaming an import.

ONE ASSET PER PROCESS (REQ-PIPE-343 criteria 5 and 6): the first connection a
process opens claims its asset, and a connection for another asset is
refused. The test suite is exempt only by releasing the claim between tests,
so each test still opens one asset's database, and a process a test spawns
starts with nothing released.

READS NO DATABASE, and before an asset is selected reads nothing but the
folder names.
"""
from __future__ import annotations

import importlib.util
import os
import re
import sys
import threading
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent

#: Where a process is told which asset it acts for.
ASSET_ENV = "MOTHMAN_ASSET"


class AssetError(RuntimeError):
    """A refusal about which asset this process acts for. Its message says
    what to do next."""


class AssetNotSelected(AssetError):
    """MOTHMAN_ASSET is unset, or names no asset folder (REQ-PIPE-363
    criteria 4 and 6)."""


class NoModule(AssetError):
    """An asset's adapter or provider file does not exist."""


class DbtPackagesMissing(AssetError):
    """The selected asset's dbt packages are not installed (REQ-QAC-368
    criterion 6)."""


class BadAssetName(AssetNotSelected):
    """An asset folder whose name is not lowercase letters, digits and single
    hyphens - which could share a module name with another, or carry a module
    path separator (post-build-review, the groundwork critic)."""


class ModuleNameClash(AssetError):
    """Two different asset modules would register one module name."""


class OneAssetPerProcess(AssetError):
    """A connection for a second asset in a process that already opened one
    for another (REQ-PIPE-343 criterion 5)."""


@dataclass(frozen=True)
class Asset:
    """One asset: its name and where each part of it lives."""

    name: str
    #: Its configuration: data-asset.yaml and the other asset-wide files at
    #: the top, its agencies' folders below.
    folder: Path
    adapters: Path
    providers: Path
    dbt_project: Path
    data: Path
    reports: Path

    def file(self, name: str) -> Path:
        """An asset-wide file, e.g. `file("calendar.yaml")`."""
        return self.folder / name

    @property
    def synthetic(self) -> Path:
        """Its synthetic-only configuration (REQ-GEN-370 criterion 1):
        scripted_decisions.yaml, synthetic_inputs.yaml - read only by the
        generator, the bootstrap and the gates."""
        return self.folder / "synthetic"

    @property
    def data_asset_yaml(self) -> Path:
        return self.file("data-asset.yaml")

    @property
    def dbt_packages(self) -> Path:
        return self.dbt_project / "dbt_packages"

    @property
    def module_tag(self) -> str:
        """The asset's name as part of a module name - hyphens as
        underscores, as a collection id becomes its module's name."""
        return self.name.replace("-", "_")


class _PreMove:
    """Today's tree as one asset (REQ-TEST-357 criterion 6)."""

    #: The one asset's name until REQ-QAC-344, as its data-asset.yaml says.
    NAME = "data-asset-1"

    folder = ROOT / "contract"

    def names(self) -> list[str]:
        return [self.NAME]

    def asset(self, name: str) -> Asset:
        return Asset(name=name, folder=self.folder,
                     adapters=ROOT / "qa_tools" / "collections",
                     providers=ROOT / "generator" / "collections",
                     dbt_project=ROOT / "dbt_project",
                     data=ROOT / "data", reports=ROOT / "reports")


class _Assets:
    """assets/<asset>/ (REQ-PIPE-342 criterion 1): one folder per asset,
    found from the folder itself. A file at the top - environments.yaml - is
    not an asset; nor is a hidden or underscored folder."""

    def __init__(self, root: Path):
        self.root = root

    def names(self) -> list[str]:
        if not self.root.is_dir():
            return []
        found = sorted(p.name for p in self.root.iterdir()
                       if p.is_dir() and not p.name.startswith((".", "_")))
        bad = [n for n in found if not NAME_PATTERN.fullmatch(n)]
        if bad:
            raise BadAssetName(
                f"asset folder name(s) {', '.join(map(repr, bad))} in {self.root} are not "
                f"lowercase letters, digits and single hyphens - rename them. An asset's "
                f"name becomes part of its modules' names, so 'a-b' and 'a_b' would be "
                f"one module and a dot would be a module path.")
        return found

    def asset(self, name: str) -> Asset:
        folder = self.root / name
        return Asset(name=name, folder=folder, adapters=folder / "collections",
                     providers=folder / "synthetic" / "collections",
                     dbt_project=folder / "dbt",
                     data=ROOT / "data" / name, reports=ROOT / "reports" / name)


#: AN ASSET'S NAME: lowercase letters and digits, words joined by single
#: hyphens - so its module tag (hyphens as underscores) is unique and has no
#: dot in it (post-build-review, the groundwork critic).
NAME_PATTERN = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")


#: THE SWITCH, made by the move commit: one folder per asset under assets/.
_DEFAULT = _Assets(ROOT / "assets")
_layout = _DEFAULT


def use_root(root: Path | None):
    """Point the resolver at an assets/ folder, or back at the default with
    None; returns what it pointed at before. For a deployment whose asset
    folders are not this repository's (#55) and for the suite's fixture."""
    global _layout
    before = _layout
    _layout = _DEFAULT if root is None else _Assets(Path(root))
    return before


class _Folder:
    """Another layout with one asset's configuration folder pointed
    elsewhere - every other path of it, and every other asset, unchanged."""

    def __init__(self, base, name: str, folder: Path, adapters: Path | None = None):
        self.base, self.name, self.folder, self.adapters = base, name, folder, adapters

    def names(self) -> list[str]:
        return self.base.names()

    def asset(self, name: str) -> Asset:
        found = self.base.asset(name)
        if name != self.name:
            return found
        return Asset(name=name, folder=self.folder, adapters=self.adapters or found.adapters,
                     providers=found.providers, dbt_project=found.dbt_project,
                     data=found.data, reports=found.reports)


def use_folder(folder: Path, name: str | None = None, *, adapters: Path | None = None):
    """Point one asset's configuration at another folder - by default the
    selected asset's - and, with `adapters`, its adapter folder too; return
    what the resolver pointed at before. The suite's one fixture
    (REQ-PIPE-342 criterion 7) is built on this."""
    global _layout
    before = _layout
    _layout = _Folder(before, name or selected().name, Path(folder),
                      Path(adapters) if adapters is not None else None)
    return before


def restore(layout) -> None:
    """Put back what use_root or use_folder returned."""
    global _layout
    _layout = layout


def _describe(layout):
    """A picklable description of a layout, for a process this one starts."""
    if isinstance(layout, _Assets):
        return ("root", str(layout.root))
    if isinstance(layout, _Folder):
        return ("folder", _describe(layout.base), layout.name, str(layout.folder),
                str(layout.adapters) if layout.adapters is not None else None)
    return ("default",)


def _rebuild(described):
    kind = described[0]
    if kind == "root":
        return _Assets(Path(described[1]))
    if kind == "folder":
        _, base, name, folder, adapters = described
        return _Folder(_rebuild(base), name, Path(folder),
                       Path(adapters) if adapters is not None else None)
    return _DEFAULT


def handoff() -> tuple:
    """What a process this one starts needs to act for the same asset: the
    selected asset's NAME and the LAYOUT it was found in - an assets/ root
    from use_root (#55), a folder from use_folder - since a spawned
    interpreter sees neither this one's selection nor its layout
    (post-build-review, the groundwork critic). Passed to `adopt` as a pool's
    initializer arguments; picklable."""
    return (selected().name, _describe(_layout))


def adopt(name: str, layout: tuple = ("default",)) -> Asset:
    """A started process's first act: take the layout and the asset it was
    handed (`handoff()`), then select the asset - refused as `select`
    refuses."""
    global _layout
    _layout = _rebuild(layout)
    return select(name)


def names() -> list[str]:
    """The asset folder names found - the one thing read with no asset
    selected (REQ-PIPE-363 NFR: reading the names is not reading an asset)."""
    return _layout.names()


def _refusal(stated: str | None, found: list[str]) -> str:
    listed = ", ".join(found) if found else "(no asset folders found)"
    if not stated:
        head = (f"{ASSET_ENV} is not set, so this command cannot say which data asset it "
                f"acts for.")
    else:
        head = f"{ASSET_ENV} is {stated!r}, which names no asset folder."
    return (f"{head} Set it to one of: {listed}. There is deliberately no default - a "
            f"command that guesses is a command that can act for an asset it was not "
            f"meant to.")


def selected() -> Asset:
    """The asset MOTHMAN_ASSET names, resolved now. Refused, naming the
    variable and every asset folder found, when it is unset or names none."""
    stated = os.environ.get(ASSET_ENV) or None
    found = names()
    if stated is None or stated not in found:
        raise AssetNotSelected(_refusal(stated, found))
    return _layout.asset(stated)


def why_not_selected() -> str | None:
    """The refusal `selected()` would raise, or None when an asset is
    selected - for a caller that says it rather than raising it, such as the
    CLI meeting a command it cannot place (REQ-PIPE-363 criterion 4)."""
    stated = os.environ.get(ASSET_ENV) or None
    found = names()
    return None if stated in found else _refusal(stated, found)


def selected_or_none() -> Asset | None:
    """For a caller that can say something useful without one - a statement
    of where the terminal is acting, `--help`. Never for a reader."""
    try:
        return selected()
    except AssetNotSelected:
        return None


def select(name: str) -> Asset:
    """Select `name` for this process and any it starts - what a spawned
    process runs first with the asset it was handed (REQ-PIPE-369
    criterion 4). Refused as `selected()` refuses."""
    if name not in names():
        raise AssetNotSelected(_refusal(name, names()))
    os.environ[ASSET_ENV] = name
    return selected()


def folder_rel() -> str:
    """The selected asset's configuration folder relative to the repository
    root, POSIX-style - `contract` today - for a reader that names its files
    by repository path, as the lifecycle gate and a read at a git ref do
    (REQ-PIPE-342 criterion 6). A folder outside the repository (a test's
    copy, #55's injected configuration) is given ABSOLUTE, so joining it to
    the repository root still names it; only a git-ref read has no meaning
    there."""
    folder = selected().folder
    try:
        return folder.relative_to(ROOT).as_posix()
    except ValueError:
        return folder.as_posix()


def dbt_rel() -> str:
    """The selected asset's dbt project relative to the repository root,
    POSIX-style - `dbt_project` today - for the readers that name its files
    by repository path, as `folder_rel` does for the configuration folder
    (REQ-QAC-368 criterion 1); absolute outside the repository."""
    project = selected().dbt_project
    try:
        return project.relative_to(ROOT).as_posix()
    except ValueError:
        return project.as_posix()


#: The shared local dbt package every asset's project pulls in (REQ-QAC-368
#: criterion 2): the shared macros and generic tests, and nothing a
#: collection owns. Repository-wide, so a constant.
DBT_SHARED = "dbt_shared"


# ---- state paths, per asset, at call time (REQ-PIPE-342 criterion 6) ----

def data_dir() -> Path:
    return selected().data


def reports_dir() -> Path:
    return selected().reports


def data_path(*parts: str) -> Path:
    return data_dir().joinpath(*parts)


def reports_path(*parts: str) -> Path:
    return reports_dir().joinpath(*parts)


def deliveries_dir() -> Path:
    return data_path("deliveries")


def receipts_dir() -> Path:
    return data_path("receipts")


# ---- the asset's dbt project (REQ-QAC-368) ----

def dbt_project_ready() -> Path:
    """The selected asset's dbt project, once its packages are installed -
    refused before dbt is invoked when they are not (REQ-QAC-368 criterion
    6), naming the asset and the one command that fixes it, rather than
    failing later with a FileNotFoundError on manifest.json."""
    asset = selected()
    packages = asset.dbt_packages
    if not packages.is_dir() or not any(packages.iterdir()):
        raise DbtPackagesMissing(
            f"asset {asset.name!r} has no dbt packages installed - {packages} is missing or "
            f"empty, so dbt cannot compile its checks. Run `mothman env dbt-deps` (with "
            f"{ASSET_ENV}={asset.name}), then run this again.")
    return asset.dbt_project


# ---- adapters and providers, by path (REQ-PIPE-369, REQ-GEN-370) ----

_KINDS = {"adapter": "adapters", "provider": "providers"}


def module_file(kind: str, module: str) -> Path:
    """Where the selected asset's `kind` module would be. `module` must
    already have passed the hierarchy's id pattern - the callers validate the
    collection id before it reaches here."""
    return getattr(selected(), _KINDS[kind]) / f"{module}.py"


def module_name(kind: str, module: str) -> str:
    """The name the selected asset's `kind` module is registered under -
    mothman_<kind>_<asset>_<module> (REQ-PIPE-369 criterion 2, REQ-GEN-370
    criterion 2, both SETTLED by Keith 2026-11-01)."""
    return f"mothman_{kind}_{selected().module_tag}_{module}"


def load(kind: str, module: str):
    """The selected asset's adapter or provider module, loaded from its file
    and registered as mothman_<kind>_<asset>_<module> - a name no package on
    sys.path provides, so two assets' same-named modules are two modules.
    Loaded once per file; asked again, the same module."""
    with _loading:
        return _load(kind, module)


#: ONE LOAD AT A TIME (a run's dbt thread and its foreground load the same
#: adapter at once): a module is registered before its body runs, so a second
#: thread must wait for the first rather than be handed it half built.
_loading = threading.RLock()


def _load(kind: str, module: str):
    asset = selected()
    path = module_file(kind, module)
    name = module_name(kind, module)
    loaded = sys.modules.get(name)
    if loaded is not None and getattr(loaded, "__file__", None) == str(path):
        return loaded
    # A CLASH IS REFUSED, NEVER REPLACED: another asset's module that maps to
    # this name (asset 'x' module 'y_z' and asset 'x-y' module 'z') keeps its
    # registration. The SAME asset, kind and module re-pointed at a new file
    # (a test's adapter folder) is a reload, not a clash.
    identity = (asset.name, kind, module)
    owner = _owners.get(name)
    if loaded is not None and owner is not None and owner != identity:
        raise ModuleNameClash(
            f"asset {asset.name!r}'s {kind} {module!r} ({path}) would be registered as "
            f"{name}, which already holds asset {owner[0]!r}'s {owner[1]} {owner[2]!r} "
            f"({getattr(loaded, '__file__', '?')}) - rename one of them")
    if not path.is_file():
        raise NoModule(f"asset {asset.name!r} has no {kind} {module!r} - {path} does not "
                       f"exist")
    spec = importlib.util.spec_from_file_location(name, path)
    loaded = importlib.util.module_from_spec(spec)
    # REGISTERED BEFORE IT RUNS: a dataclass in it looks its own module up.
    sys.modules[name] = loaded
    try:
        spec.loader.exec_module(loaded)
    except BaseException:
        sys.modules.pop(name, None)
        raise
    _owners[name] = identity
    return loaded


#: Which (asset, kind, module) each registered module name was loaded for.
_owners: dict[str, tuple[str, str, str]] = {}


def adapter_file(collection_id: str) -> str:
    """The file a collection's adapter loads from - what a spawned process
    reports back, and what a gate names."""
    from qa_tools import collections

    return collections.adapter_module(collection_id).__file__


# ---- one asset per process (REQ-PIPE-343 criteria 5 and 6) ----

_claimed: str | None = None


def claimed() -> str | None:
    """The asset this process has opened a connection for, if any."""
    return _claimed


def claim_for_connection(name: str) -> None:
    """Called as each connection opens: the first claims the process for
    `name`, a later one for another asset is refused - so nothing that ships
    holds two assets' databases (or their credentials) in one process."""
    global _claimed
    if _claimed is None:
        _claimed = name
    elif _claimed != name:
        raise OneAssetPerProcess(
            f"this process already opened a connection for asset {_claimed!r}, so it "
            f"cannot open one for asset {name!r} - run one process per asset, each with "
            f"its own {ASSET_ENV} and MOTHMAN_SUPPLY_DSN")


def release_claim() -> None:
    """The test suite's exemption (REQ-PIPE-343 criterion 6), called between
    tests and only there: each test starts unclaimed, and still opens only
    one asset's database. Nothing that ships calls it."""
    global _claimed
    _claimed = None

