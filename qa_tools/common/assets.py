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

ONE LAYOUT SINCE THE MOVE (REQ-TEST-357 criteria 5 and 6): `_DEFAULT` is
`_Assets(ROOT / "assets")`, and each asset folder is found from assets/ itself
(criterion 5) - assets/<asset>/ its configuration, its collections/ the QA
adapters, its synthetic/collections/ the generator providers, its dbt/ the dbt
project, and data/<asset>/ and reports/<asset>/ its state. No code names an
asset. The one-asset layout before the move (contract/, qa_tools/collections/,
generator/collections/, dbt_project/) is gone, and with it the class that
mapped it.

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
import stat
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


class OutsideTheRepository(AssetError):
    """A repository path was asked for an asset folder the repository does
    not hold (REQ-PIPE-342 decision 18)."""


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


class _Assets:
    """assets/<asset>/ (REQ-PIPE-342 criterion 1): one folder per asset,
    found from the folder itself. A file at the top - environments.yaml - is
    not an asset; nor is a hidden or underscored folder."""

    def __init__(self, root: Path):
        self.root = root
        # REMEMBERED BY THE FOLDER'S OWN STAT, so still "as it is now": a
        # folder added, removed or renamed under assets/ changes the
        # directory's mtime, and the next call lists it afresh. selected() is
        # asked millions of times in one generation, and listing the folder
        # each time was over half of it (post-build-review #318).
        self._listed: tuple | None = None
        self._assets: dict[str, Asset] = {}

    def names(self) -> list[str]:
        try:
            st = os.stat(self.root)
        except OSError:
            return []
        if not stat.S_ISDIR(st.st_mode):
            return []
        stamp = (st.st_mtime_ns, st.st_ino)
        if self._listed is not None and self._listed[0] == stamp:
            return list(self._listed[1])
        found = sorted(p.name for p in self.root.iterdir()
                       if p.is_dir() and not p.name.startswith((".", "_")))
        bad = [n for n in found if not NAME_PATTERN.fullmatch(n)]
        if bad:
            raise BadAssetName(
                f"asset folder name(s) {', '.join(map(repr, bad))} in {self.root} are not "
                f"lowercase letters, digits and single hyphens - rename them. An asset's "
                f"name becomes part of its modules' names, so 'a-b' and 'a_b' would be "
                f"one module and a dot would be a module path.")
        self._listed = (stamp, tuple(found))
        return found

    def asset(self, name: str) -> Asset:
        """Its paths - which depend on nothing but the root and the name, so
        built once per name (an Asset is frozen)."""
        found = self._assets.get(name)
        if found is None:
            folder = self.root / name
            found = self._assets[name] = Asset(
                name=name, folder=folder, adapters=folder / "collections",
                providers=folder / "synthetic" / "collections",
                dbt_project=folder / "dbt",
                data=ROOT / "data" / name, reports=ROOT / "reports" / name)
        return found


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


def root_injected() -> bool:
    """Whether a deployment has DELIBERATELY injected its assets/ root
    elsewhere (use_root; REQ-PIPE-342's injection, #55) - as opposed to one
    asset's folder pointed elsewhere (use_folder), which is what the suite's
    fixture does. Keith, 2026-11-03 (morning report 12 Q13): the schedule
    gate's git-ref guards refuse an outside folder only in the first case."""
    layout = _layout
    while isinstance(layout, _Folder):
        layout = layout.base
    return isinstance(layout, _Assets) and Path(layout.root) != Path(_DEFAULT.root)


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


def every() -> list[Asset]:
    """Every asset folder found, as the resolver lays it out now - for the
    configuration-only reads that must tell another asset's name from a typo
    (qa_tools/common/every_asset.py; Keith, 2026-11-03, morning report 12 Q6
    and Q8). Selects nothing, and opens no database."""
    return [_layout.asset(n) for n in names()]


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


def _repo_rel(path: Path, what: str, root: Path | None = None) -> str:
    """`path` relative to the repository root (or the checkout at `root`),
    POSIX-style - REFUSED for a path outside it (Keith, 2026-11-02, C7;
    REQ-PIPE-342 decision 18). A repository path is what a read at a git
    ref, CODEOWNERS and a link into the repository mean, and none of them
    has a meaning for a folder the repository does not hold, so an absolute
    path standing in for one would be mis-read rather than fail."""
    root = Path(root) if root is not None else ROOT
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        raise OutsideTheRepository(
            f"asset {selected().name!r}'s {what} is {path}, outside the repository "
            f"({root}), so it has no repository path - a reader that names its files "
            f"by repository path cannot read it there.") from None


def _on_disk(path: Path) -> str:
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def folder_rel(root: Path | None = None) -> str:
    """The selected asset's configuration folder relative to the repository
    root (or the checkout at `root`), POSIX-style - `assets/<asset>` - for a
    reader that names its files by REPOSITORY PATH: a read at a git ref,
    CODEOWNERS, a link into the repository (REQ-PIPE-342 criterion 6).
    Refused for a folder outside it (a test's copy, #55's injected
    configuration): OutsideTheRepository. A reader that only OPENS the
    asset's files asks folder_on_disk()."""
    return _repo_rel(selected().folder, "configuration folder", root)


def folder_on_disk() -> str:
    """The selected asset's configuration folder AS A PATH TO OPEN in the
    working tree: by repository path where the repository holds it, so what
    a reader records or names reads as before, and as the folder itself
    where it does not (#55's injected configuration, a test's copy) - joined
    to the repository root, either finds it. Never a repository path: a
    git-ref read, CODEOWNERS or a link asks folder_rel(), which refuses
    (C7)."""
    return _on_disk(selected().folder)


def config_dir() -> str:
    """The selected asset's configuration folder for a MESSAGE to name -
    its repository path, or the folder as it is when the repository does not
    hold it (a message names a file for a person, so it is never refused
    mid-sentence); the generic `assets/<asset>` when no asset is selected,
    so a refusal or warning naming a file never itself fails for want of an
    asset (critic finding 7, the asset split)."""
    try:
        folder = selected().folder
    except AssetNotSelected:
        return "assets/<asset>"
    try:
        return folder.relative_to(ROOT).as_posix()
    except ValueError:
        return folder.as_posix()


def dbt_rel(root: Path | None = None) -> str:
    """The selected asset's dbt project relative to the repository root,
    POSIX-style - `assets/<asset>/dbt` - for the readers that name its files
    by repository path, as `folder_rel` does for the configuration folder
    (REQ-QAC-368 criterion 1); refused outside the repository, as there."""
    return _repo_rel(selected().dbt_project, "dbt project", root)


def dbt_on_disk() -> str:
    """The selected asset's dbt project as a path to open, as
    folder_on_disk() is for its configuration folder."""
    return _on_disk(selected().dbt_project)


#: The shared dbt macros and generic tests every asset's project reads through its
#: macro-paths and test-paths (REQ-QAC-368
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
    # ONE MEANING OF "INSTALLED" EVERYWHERE (Keith, 2026-11-03, morning
    # report 12 Q10; criterion 6 as amended): dbt's own package-lock rule, the
    # one `mothman env dbt-deps` decides by, so packages outdated by an edit to
    # packages.yml, or deleted since, are refused as a missing folder is.
    # REJECTED keeping the missing-or-empty folder test as first signed.
    from qa_tools.common import dbt_common

    asset = selected()
    if not dbt_common.packages_installed(asset.dbt_project):
        raise DbtPackagesMissing(
            f"asset {asset.name!r} has no current dbt packages installed - "
            f"{asset.dbt_project / dbt_common.PACKAGE_LOCK} is missing or stale against "
            f"packages.yml, or a package it names is missing from {asset.dbt_packages}, so "
            f"dbt cannot compile its checks. Run `mothman env dbt-deps` (with "
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

