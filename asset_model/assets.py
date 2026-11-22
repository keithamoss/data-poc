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
this repository (REQ-PIPE-342) without renaming an import.

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

ROOT = Path(__file__).resolve().parent.parent

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


class BadAssetName(AssetNotSelected):
    """An asset folder whose name is not lowercase letters, digits and single
    hyphens - which could share a module name with another, or carry a module
    path separator (post-build-review, the groundwork critic)."""


class OutsideTheRepository(AssetError):
    """A repository path was asked for an asset folder the repository does
    not hold (REQ-PIPE-342 decision 18)."""


class ModuleNameClash(AssetError):
    """Two different asset modules would register one module name."""


class OneOffRefused(AssetNotSelected):
    """A one-off named in a way that cannot select it (REQ-PIPE-446 criteria 3,
    4 and 9, REQ-PIPE-363 criterion 12): MOTHMAN_ASSET set beside `--id`, an id
    that is not one, or one id under two roots, or MOTHMAN_ASSET naming one."""


class NeverGitHub(AssetError):
    """A GitHub API call while a one-off is selected (REQ-PIPE-446 criterion
    14, Keith 2026-11-21: 'One offs should never use GitHub.')."""


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
    #: THE KIND FOLDER IT WAS FOUND UNDER (REQ-PIPE-446 criterion 12) - None
    #: for an enduring asset under assets/. Read from where the folder is,
    #: never from a declaration inside it.
    kind: str | None = None

    @property
    def is_one_off(self) -> bool:
        return self.kind is not None

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


#: Where one-offs live, beside assets/ (REQ-PIPE-446 criterion 1):
#: one-offs/<kind>/<id>/, each kind's template at one-offs/<kind>/_template/.
ONE_OFFS = "one-offs"


def _listable(path: Path) -> tuple | None:
    """(mtime_ns, inode) of a directory, or None where it is not one."""
    try:
        st = os.stat(path)
    except OSError:
        return None
    return (st.st_mtime_ns, st.st_ino) if stat.S_ISDIR(st.st_mode) else None


def _subfolders(path: Path) -> list[str]:
    return sorted(p.name for p in path.iterdir()
                  if p.is_dir() and not p.name.startswith((".", "_")))


class _OneOffs:
    """one-offs/<kind>/<id>/ (REQ-PIPE-446 criterion 1): every kind folder,
    and every folder in it - directories only, '_' and '.' names skipped. No
    list of kinds or one-offs is held anywhere in code.

    A STAT STAMP PER FOLDER (the SCALABILITY NFR): the root's for which kinds
    exist, and each kind folder's for which one-offs it holds - so the
    two-level listing is re-read only where an entry changed."""

    def __init__(self, root: Path):
        self.root = Path(root)
        self._kinds: tuple | None = None
        self._ids: dict[str, tuple] = {}

    def kinds(self) -> list[str]:
        stamp = _listable(self.root)
        if stamp is None:
            return []
        if self._kinds is None or self._kinds[0] != stamp:
            self._kinds = (stamp, tuple(_subfolders(self.root)))
        return list(self._kinds[1])

    def names_in(self, kind: str) -> list[str]:
        """Every one-off folder of a kind, its name good or bad."""
        folder = self.root / kind
        stamp = _listable(folder)
        if stamp is None:
            return []
        held = self._ids.get(kind)
        if held is None or held[0] != stamp:
            held = self._ids[kind] = (stamp, tuple(_subfolders(folder)))
        return list(held[1])

    def listing(self) -> list[tuple[str, str]]:
        """(kind, id) for every one-off whose name meets NAME_PATTERN. A bad
        name is left out, so it can never be selected - `mothman check` names
        it (bad_names)."""
        return [(k, n) for k in self.kinds() for n in self.names_in(k)
                if NAME_PATTERN.fullmatch(n)]

    def bad_names(self) -> list[Path]:
        return [self.root / k / n for k in self.kinds() for n in self.names_in(k)
                if not NAME_PATTERN.fullmatch(n)]

    def asset(self, kind: str, name: str) -> "Asset":
        folder = self.root / kind / name
        return Asset(name=name, folder=folder, adapters=folder / "collections",
                     providers=folder / "synthetic" / "collections",
                     dbt_project=folder / "dbt",
                     data=ROOT / "data" / name, reports=ROOT / "reports" / name, kind=kind)


class _Assets:
    """assets/<asset>/ (REQ-PIPE-342 criterion 1): one folder per asset,
    found from the folder itself. A file at the top - environments.yaml - is
    not an asset; nor is a hidden or underscored folder. The one-offs root is
    held beside it (REQ-PIPE-446 criterion 11)."""

    def __init__(self, root: Path, one_offs: Path | None = None):
        self.root = root
        self.one_offs = _OneOffs(Path(one_offs) if one_offs is not None
                                 else ROOT / ONE_OFFS)
        # REMEMBERED BY THE FOLDER'S OWN STAT, so still "as it is now": a
        # folder added, removed or renamed under assets/ changes the
        # directory's mtime, and the next call lists it afresh. selected() is
        # asked millions of times in one generation, and listing the folder
        # each time was over half of it (post-build-review #318).
        self._listed: tuple | None = None
        self._assets: dict[str, Asset] = {}

    def names(self) -> list[str]:
        """The asset folders under assets/, as they are now.

        REMEMBERED BY THE assets/ DIRECTORY'S OWN STAT (mtime and inode), and
        deliberately so: REQ-PIPE-254 criterion 15's rule - a configuration
        file is read on every call and never skipped on its modification time,
        size or inode - is about a file's CONTENT, and this reads no
        configuration file. It lists which folders exist, and a directory's
        mtime moves whenever an entry is added, removed or renamed, which is
        all it needs to see (REQ-PIPE-401 criterion 4). Listing the folder
        on every call was over half of a generation (post-build-review #318).
        """
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
    folders are not this repository's (REQ-PIPE-342) and for the suite's fixture."""
    global _layout
    before = _layout
    _layout = _DEFAULT if root is None else _Assets(Path(root), _innermost(before).one_offs.root)
    return before


def _innermost(layout) -> "_Assets":
    while isinstance(layout, _Folder):
        layout = layout.base
    return layout


def use_one_offs_root(root: Path | None):
    """Point the resolver's one-offs root elsewhere - a deployment's, a test's
    temporary folder - or back at one-offs/ with None, as use_root does for
    assets/ (REQ-PIPE-446 criterion 7); returns what it pointed at before."""
    global _layout
    before = _layout
    inner = _innermost(before)
    replaced = _Assets(Path(inner.root), Path(root) if root is not None else ROOT / ONE_OFFS)
    _layout = _with_base(before, replaced)
    return before


def _with_base(layout, base):
    if isinstance(layout, _Folder):
        return _Folder(_with_base(layout.base, base), layout.name, layout.folder,
                       layout.adapters)
    return base


def root_injected() -> bool:
    """Whether a deployment has DELIBERATELY injected its assets/ root
    elsewhere (use_root; REQ-PIPE-342's injection) - as opposed to one
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

    @property
    def one_offs(self) -> "_OneOffs":
        return self.base.one_offs

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
        return ("root", str(layout.root), str(layout.one_offs.root))
    if isinstance(layout, _Folder):
        return ("folder", _describe(layout.base), layout.name, str(layout.folder),
                str(layout.adapters) if layout.adapters is not None else None)
    return ("default",)


def _rebuild(described):
    kind = described[0]
    if kind == "root":
        return _Assets(Path(described[1]),
                       Path(described[2]) if len(described) > 2 else None)
    if kind == "folder":
        _, base, name, folder, adapters = described
        return _Folder(_rebuild(base), name, Path(folder),
                       Path(adapters) if adapters is not None else None)
    return _DEFAULT


def handoff() -> tuple:
    """What a process this one starts needs to act for the same asset: the
    selected asset's NAME, the LAYOUT it was found in - an assets/ root from
    use_root (REQ-PIPE-342), a folder from use_folder - and the CONFIGURATION
    PINNED for this run, if one is (REQ-PIPE-397 criterion 12), since a spawned
    interpreter sees neither this one's selection, its layout nor its pin
    (post-build-review, the groundwork critic). Passed to `adopt` as a pool's
    initializer arguments; picklable. THE ONE HAND-OFF (REQ-PIPE-369 criterion
    4): no pool carries an initializer of its own.

    THE CLOCK TRAVELS BESIDE IT, not in it (PROVISIONAL (2026-11-16)): a
    pinned instant is MOTHMAN_PINNED_NOW, which a spawned process inherits with
    the environment, and a replay clock is installed by each stream process
    around its own replay, since a clock anchored on this process's monotonic
    time means nothing in another. THE INSTALLED ANCHOR IS HANDED TOO
    (REQ-GEN-404 criterion 10, REQ-PIPE-397 criterion 12), so a provider
    called in a started process generates for the run's anchor."""
    from asset_model import arrivals, config_pin, history_anchor

    # A ONE-OFF TRAVELS AS ITSELF (REQ-PIPE-446 criterion 7): its id and that it
    # is one, never written into MOTHMAN_ASSET, which criterion 9 refuses.
    # ITS CHECK WORKSPACE TRAVELS WITH IT (REQ-QAC-441): a tool's worker reads
    # the same merged layers as the run - the path in place of True.
    chosen = selected()
    one_off = (str(_workspace) if chosen.is_one_off and _workspace is not None
               else chosen.is_one_off)
    return (chosen.name, _describe(_layout), config_pin.installed(),
            arrivals.installed_tree(), history_anchor.installed(), one_off)


def adopt(name: str, layout: tuple = ("default",), snapshot=None, tree=None,
          anchor=None, one_off: "bool | str" = False) -> Asset:
    """A started process's first act: take the layout and the asset it was
    handed (`handoff()`), select the asset - refused as `select` refuses - pin
    the configuration snapshot it was handed, verified against its digest
    (REQ-PIPE-397 criterion 12), and hold the delivery-tree snapshot it was
    handed (REQ-PIPE-430) - or neither, if it was handed neither - and install
    the history's anchor it was handed (REQ-GEN-404 criterion 10)."""
    global _layout
    _layout = _rebuild(layout)
    asset = select_one_off(name) if one_off else select(name)
    if isinstance(one_off, str):
        use_workspace(Path(one_off))
        asset = selected()
    from asset_model import arrivals, config_pin, history_anchor

    config_pin.adopt(snapshot)
    arrivals.adopt_tree(tree)
    history_anchor.adopt(anchor)
    return asset


def names() -> list[str]:
    """The asset folder names found - the one thing read with no asset
    selected (REQ-PIPE-363 NFR: reading the names is not reading an asset)."""
    return _layout.names()


def every() -> list[Asset]:
    """Every asset folder found, as the resolver lays it out now - for the
    configuration-only reads that must tell another asset's name from a typo
    (asset_model/every_asset.py; Keith, 2026-11-03, morning report 12 Q6
    and Q8). Selects nothing, and opens no database."""
    return [_layout.asset(n) for n in names()]


def one_offs() -> list[tuple[str, str]]:
    """(kind, id) for every one-off found (REQ-PIPE-446 criterion 1) - its
    own reader, never through names() (criterion 6)."""
    return _layout.one_offs.listing()


def one_off_kinds() -> list[str]:
    """Every kind folder under one-offs/."""
    return _layout.one_offs.kinds()


def one_offs_root() -> Path:
    return _layout.one_offs.root


def kind_template(kind: str) -> Path:
    """one-offs/<kind>/_template/ - what every one-off of the kind reads live
    (REQ-PIPE-440 criterion 13): its default check layer, people.yaml and
    publishing destination. Never copied into a one-off's folder."""
    return _layout.one_offs.root / kind / "_template"


def bad_one_off_names() -> list[Path]:
    """One-off folders whose names do not meet NAME_PATTERN - never selectable;
    `mothman check` names each (criterion 1)."""
    return _layout.one_offs.bad_names()


def id_clashes() -> dict[str, list[Path]]:
    """{id: every folder holding it} for an id under assets/ and a kind, or
    under two kinds (criterion 4) - they would share data/, reports/, a
    database and a module tag."""
    held: dict[str, list[Path]] = {n: [_layout.asset(n).folder] for n in names()}
    for kind, name in one_offs():
        held.setdefault(name, []).append(_layout.one_offs.root / kind / name)
    return {n: f for n, f in held.items() if len(f) > 1}


def kinds_sentence() -> str:
    """'For one of <n> <kinds>, use mothman one-off.' - each kind that has
    folders, counted in its plural display word (its singular for exactly one
    folder, Keith 2026-11-22), joined with 'or'; empty where
    there are none (REQ-PIPE-363 criteria 4 to 6, wording SETTLED by Keith
    2026-11-21). A kind with no plug-in has no display word, so it is left out
    of the sentence - `mothman check` fails its folder (REQ-PIPE-446 c2)."""
    from asset_model import one_off_kinds

    counts: dict[str, int] = {}
    for kind, _name in one_offs():
        counts[kind] = counts.get(kind, 0) + 1
    parts = []
    for kind in sorted(counts):
        plug = one_off_kinds.get(kind)
        if plug is not None:
            # THE SINGULAR FOR EXACTLY ONE FOLDER (Keith 2026-11-22): 'For one
            # of 1 extraction'; the plural otherwise, as approved.
            parts.append(f"{counts[kind]} {plug.singular if counts[kind] == 1 else plug.plural}")
    return f" For one of {' or '.join(parts)}, use mothman one-off." if parts else ""


def _refusal(stated: str | None, found: list[str]) -> str:
    listed = ", ".join(found) if found else "(no asset folders found)"
    kind = _kind_of_one_off(stated) if stated else None
    if kind is not None:
        return _names_a_one_off(stated, kind, listed)
    if not stated:
        head = (f"{ASSET_ENV} is not set, so this command cannot say which data asset it "
                f"acts for.")
    else:
        head = f"{ASSET_ENV} is {stated!r}, which names no asset folder."
    return (f"{head} Set it to one of: {listed}.{kinds_sentence()} There is deliberately "
            f"no default - a command that guesses is a command that can act for an asset "
            f"it was not meant to.")


def _kind_of_one_off(name: str) -> str | None:
    found = [k for k, n in one_offs() if n == name]
    return found[0] if found else None


def _names_a_one_off(stated: str, kind: str, listed: str) -> str:
    """REQ-PIPE-363 criterion 12, in the words Keith approved (v7 review)."""
    from asset_model import one_off_kinds

    plug = one_off_kinds.get(kind)
    word = plug.singular if plug is not None else kind
    return (f"{ASSET_ENV} is {stated!r}, which is an {word}, not an asset. A one-off is "
            f"chosen by --id, with {ASSET_ENV} unset: mothman one-off <step> --id {stated}. "
            f"To run this command for an asset instead, set it to one of: {listed}.")


#: The one-off this process acts for, chosen by `--id` or in the TUI - never
#: from MOTHMAN_ASSET (REQ-PIPE-446 criteria 3 and 9).
_one_off: str | None = None
#: THE CHECK WORKSPACE A ONE-OFF'S LOAD MATERIALISED (REQ-QAC-441 criterion 1,
#: REQ-PIPE-440 criterion 13): its committed configuration with the kind's
#: default check layer, read live from the template, merged in - under its own
#: data/<id>/, never its folder. While set, the selected one-off's
#: configuration folder and dbt project are read from there.
_workspace: Path | None = None


def _stated_beside(what: str) -> None:
    stated = os.environ.get(ASSET_ENV)
    if stated:
        raise OneOffRefused(
            f"{ASSET_ENV} is {stated!r}, and a one-off is being named ({what}). "
            f"{ASSET_ENV} is for the enduring assets only - unset it, and name the "
            f"one-off by --id alone.")


def select_one_off(name: str) -> Asset:
    """Select one-off `name` for this process (REQ-PIPE-446 criterion 3) -
    refused, before any configuration is read, with MOTHMAN_ASSET set at all,
    and refused for an id that is not a one-off or that clashes (criterion 4).
    Never writes MOTHMAN_ASSET (criterion 7)."""
    global _one_off, _workspace
    _stated_beside(f"--id {name}")
    found = [(k, n) for k, n in one_offs() if n == name]
    if not found:
        listed = ", ".join(sorted(n for _k, n in one_offs())) or "(no one-off folders found)"
        raise OneOffRefused(f"{name!r} is not a one-off - none of {one_offs_root()}/<kind>/ "
                            f"holds a folder of that name. One-offs found: {listed}.")
    clash = id_clashes().get(name)
    if clash:
        raise OneOffRefused(_clash_words(name, clash))
    _one_off = name
    _workspace = None
    return selected()


def use_workspace(folder: Path | None) -> None:
    """Read the selected one-off's configuration from its check workspace
    (qa_tools/common/one_off_checks.materialise), or, with None, from its
    folder again. Only for a one-off already selected."""
    global _workspace
    if folder is not None and _one_off is None:
        raise OneOffRefused("a check workspace is for a selected one-off only")
    _workspace = Path(folder) if folder is not None else None


def committed_folder() -> Path:
    """The selected one-off's own folder under one-offs/<kind>/, whether or
    not a check workspace is in use - what git and the digest are asked of."""
    found = [(k, n) for k, n in one_offs() if n == _one_off]
    if _one_off is None or not found:
        raise OneOffRefused("no one-off is selected")
    return _layout.one_offs.root / found[0][0] / found[0][1]


def deselect_one_off() -> None:
    """Back to no one-off - the TUI choosing another, and the suite between
    tests."""
    global _one_off, _workspace
    _one_off = None
    _workspace = None


def _clash_words(name: str, folders: list[Path]) -> str:
    return (f"{name!r} is the name of more than one folder - "
            f"{', '.join(str(f) for f in folders)} - so it is selected as neither: they "
            f"would share data/{name}, reports/{name}, the database supply_{name} and a "
            f"module tag. Rename all but one.")


def selected() -> Asset:
    """The asset MOTHMAN_ASSET names, or the one-off chosen by `--id`, resolved
    now. Refused, naming the variable and every asset folder found, when
    neither is there."""
    if _one_off is not None:
        _stated_beside(f"--id {_one_off}")
        found = [(k, n) for k, n in one_offs() if n == _one_off]
        if not found:
            raise OneOffRefused(f"the one-off {_one_off!r} chosen for this process is no "
                                f"longer under {one_offs_root()}.")
        found_asset = _layout.one_offs.asset(*found[0])
        if _workspace is not None:
            from dataclasses import replace

            return replace(found_asset, folder=_workspace, adapters=_workspace / "collections",
                           providers=_workspace / "synthetic" / "collections",
                           dbt_project=_workspace / "dbt")
        return found_asset
    stated = os.environ.get(ASSET_ENV) or None
    found = names()
    if stated is None or stated not in found:
        refusal = _refusal(stated, found)
        raise (OneOffRefused if stated and _kind_of_one_off(stated) else
               AssetNotSelected)(refusal)
    # AN ID UNDER assets/ AND A KIND IS SELECTED AS NEITHER (REQ-PIPE-446 c4);
    # asked only where one-offs exist, since selected() is asked millions of
    # times in one generation.
    if one_offs():
        clash = id_clashes().get(stated)
        if clash:
            raise OneOffRefused(_clash_words(stated, clash))
    return _layout.asset(stated)


def why_not_selected() -> str | None:
    """The refusal `selected()` would raise, or None when an asset or a
    one-off is selected - for a caller that says it rather than raising it,
    such as the CLI meeting a command it cannot place (REQ-PIPE-363
    criterion 4)."""
    try:
        selected()
    except AssetNotSelected as exc:
        return str(exc)
    return None


def selected_or_none() -> Asset | None:
    """For a caller that can say something useful without one - a statement
    of where the terminal is acting, `--help`. Never for a reader."""
    try:
        return selected()
    except AssetNotSelected:
        return None


def select(name: str) -> Asset:
    """Select asset `name` for this process and any it starts - what a spawned
    process runs first with the asset it was handed (REQ-PIPE-369
    criterion 4). Refused as `selected()` refuses - a one-off's id included
    (REQ-PIPE-446 criterion 9)."""
    if name not in names():
        raise (OneOffRefused if _kind_of_one_off(name) else AssetNotSelected)(
            _refusal(name, names()))
    os.environ[ASSET_ENV] = name
    return selected()


def refuse_github(what: str) -> None:
    """Refused for a one-off (REQ-PIPE-446 criterion 14): no ticket, no
    comment, no GitHub API call of any kind. Every `gh` boundary asks."""
    chosen = selected_or_none()
    if chosen is not None and chosen.is_one_off:
        raise NeverGitHub(f"{what} is a GitHub API call, and {chosen.name!r} is a one-off: "
                          f"one-offs never use GitHub (tickets, comments or the API). "
                          f"Pushing its configuration with git is not an API call.")


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
    Refused for a folder outside it (a test's copy, REQ-PIPE-342's injected
    configuration): OutsideTheRepository. A reader that only OPENS the
    asset's files asks folder_on_disk()."""
    return _repo_rel(selected().folder, "configuration folder", root)


def folder_on_disk() -> str:
    """The selected asset's configuration folder AS A PATH TO OPEN in the
    working tree: by repository path where the repository holds it, so what
    a reader records or names reads as before, and as the folder itself
    where it does not (REQ-PIPE-342's injected configuration, a test's copy) - joined
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

