"""An asset's configuration held still for one synthetic run (REQ-PIPE-397,
signed by Keith 2026-11-14 as speed-anchor v2).

WHY. A generation and a bootstrap's replay read the same configuration
millions of times - post-build-review #318 counted 2.7 million hierarchy loads
and 1.5 million agreement look-ups in one generation - and every one of them
read its file again, because REQ-PIPE-254 criterion 15 says a configuration
file is read whole on every call. Keith's S1 (2026-11-14): a generation and a
bootstrap read the configuration ONCE, at the start, and use it throughout; an
edit made mid-run is seen by the next run. Criterion 15 still holds outside a
pinned run - the pipeline, the CLI and the dashboard build read as before.

EAGER, NOT LAZY (the architect's B1). The snapshot reads its whole declared set
when it is taken: every *.yaml and *.yml file of the selected asset's folder
(dbt/dbt_packages/ left out - an installed package is not the asset's
configuration) and assets/environments.yaml. So its digest is one value, and
every process a pinned run starts is handed exactly those contents
(assets.handoff) rather than reading afresh whatever the parent had not yet
read - plus the shared file-checks default at the repository root
(REQ-QAC-387), which every asset's file checks merge with.

THROUGH THE SEAM, NOT A FLAG (the architect, separation v5 reviews): the pin
acts inside config_yaml.read() - and so inside load() and every Built store -
as an installed clock acts inside asset_time.now(). No real pipeline module
asks whether a pin is installed (criterion 4); only the synthetic side installs
one (the generator's driver, the bootstrap), and it is REFUSED on an asset that
does not declare `synthetic: true`, here in asset_model/ so the refusal holds
where the bootstrap package is absent (criterion 3) - a real deployment's
long-running pass never answers from a stale configuration.

MOTHMAN'S OWN READS ONLY (SA Q4, SETTLED by Keith 2026-11-14): dbt and Soda read
their own project and check files themselves, unpinned, so a mid-run edit of a
dbt model reaches dbt as it does today; the replay cache key (REQ-TEST-117) and
the resume digest (REQ-TEST-160) catch it after the run.

STAGED CORRECTIONS SIT ON TOP (criterion 5): correction_trial.configured swaps
agreement.current and asset_time.timezone_versions in memory for an arrival's
span, so for that span the staged agreement and zones answer, and the pin
answers everything else.
"""
from __future__ import annotations

import hashlib
import os
from contextlib import contextmanager
from pathlib import Path

from asset_model import assets, config_yaml

#: What a configuration file is called (criterion 1).
SUFFIXES = (".yaml", ".yml")

#: Directories never read into the snapshot: an installed dbt package is
#: somebody else's project, and a hidden folder or a byte-code cache is not
#: configuration.
PRUNED = frozenset({"dbt_packages", "__pycache__", "node_modules"})


class PinRefused(RuntimeError):
    """A pin asked of an asset that does not declare itself synthetic."""


class PinMismatch(RuntimeError):
    """A process was handed a snapshot whose contents do not match the
    digest it was handed with - a fault in mothman's hand-off."""


def declared_files() -> list[Path]:
    """The snapshot set of the selected asset, as found now: every *.yaml and
    *.yml under its configuration folder - following the links the suite's
    asset folders are made of - outside dbt_packages/, plus
    assets/environments.yaml and the shared file-checks default."""
    folder = assets.selected().folder
    found = []
    for root, dirs, files in os.walk(folder, followlinks=True):
        dirs[:] = sorted(d for d in dirs if d not in PRUNED and not d.startswith("."))
        found += [Path(root) / f for f in sorted(files) if f.endswith(SUFFIXES)]
    for shared in (assets.ROOT / "assets" / "environments.yaml", assets.ROOT / "file-checks.yaml"):
        if shared.is_file():
            found.append(shared)
    return found


def _digest(texts) -> str:
    h = hashlib.sha256()
    for key in sorted(texts):
        h.update(key.encode("utf-8"))
        h.update(b"\0")
        h.update(texts[key].encode("utf-8"))
        h.update(b"\0")
    return h.hexdigest()


class ConfigSnapshot:
    """One asset's configuration as read at one moment: {resolved path: text},
    and a digest naming exactly those contents (criterion 13).

    `install()` and `release()` pin it for a span, or use it as a with-block.
    Picklable, so a pinned run hands it to every process it starts
    (assets.handoff, criterion 12); two snapshots are equal when their asset
    and digest are."""

    def __init__(self, asset: str, texts: dict[str, str], digest: str | None = None):
        self.asset = asset
        self.texts = dict(texts)
        self.digest = digest if digest is not None else _digest(self.texts)

    @classmethod
    def take(cls) -> "ConfigSnapshot":
        """Read the selected asset's whole snapshot set now, once, from disk.

        A FILE THAT CANNOT BE READ IS LEFT OUT (criterion 9): every read of it
        then goes to disk and raises as an unpinned read would, on every call,
        and nothing remembers the failure."""
        texts = {}
        for path in declared_files():
            try:
                texts[os.path.realpath(path)] = config_yaml.read_from_disk(path)
            except (OSError, UnicodeDecodeError):
                continue
        return cls(assets.selected().name, texts)

    def __eq__(self, other) -> bool:
        return (isinstance(other, ConfigSnapshot) and self.asset == other.asset
                and self.digest == other.digest)

    def __hash__(self) -> int:
        return hash((self.asset, self.digest))

    def __repr__(self) -> str:
        return f"ConfigSnapshot({self.asset!r}, {len(self.texts)} files, {self.digest[:12]})"

    @property
    def short(self) -> str:
        """The digest's first 12 characters, as the bootstrap prints it."""
        return self.digest[:12]

    def verify(self) -> None:
        """Raise PinMismatch unless the contents hash to the digest this
        snapshot was handed with."""
        found = _digest(self.texts)
        if found != self.digest:
            raise PinMismatch(
                f"this process was handed a configuration snapshot of asset {self.asset!r} "
                f"stated as {self.digest[:12]} whose contents hash to {found[:12]} - a fault "
                f"in mothman's hand-off, not anything you did")

    def install(self) -> "ConfigSnapshot":
        """Pin it: every config_yaml read of a file in it is answered from it
        until release(). REFUSED on an asset that does not declare `synthetic:
        true` (criterion 3) - read through asset_time's one reader, from the
        snapshot's own text - naming the asset and its data-asset.yaml."""
        global _installed
        from asset_model import asset_time

        if _installed is not None and _installed is not self:
            raise RuntimeError(f"a configuration pin is already installed ({_installed!r}) - "
                               f"release it first, or use config_pin.pinned()")
        config_yaml.pin(self.texts)
        try:
            synthetic = asset_time.declared_synthetic()
        except BaseException:
            config_yaml.unpin()
            raise
        if not synthetic:
            config_yaml.unpin()
            raise PinRefused(
                f"asset {self.asset!r} does not declare `synthetic: true` in "
                f"{asset_time.data_asset_yaml()}, so its configuration cannot be pinned - a "
                f"real asset's configuration is read whole on every call (REQ-PIPE-254 "
                f"criterion 15), so a long-running real process never answers from a "
                f"stale copy")
        _installed = self
        return self

    def release(self) -> None:
        """Unpin it, if it is the one installed: the next read sees the files
        as they are (criterion 6)."""
        global _installed
        if _installed is self:
            _installed = None
            config_yaml.unpin()

    def __enter__(self) -> "ConfigSnapshot":
        return self.install()

    def __exit__(self, *_exc) -> None:
        self.release()


#: The snapshot pinned in this process, or None.
_installed: ConfigSnapshot | None = None


def installed() -> ConfigSnapshot | None:
    """The snapshot pinned in this process, or None - for the synthetic side
    that hands it on and reports its digest, never for a pipeline module to
    branch on (criterion 4)."""
    return _installed


@contextmanager
def pinned():
    """The selected asset's configuration pinned for the span of the
    with-block: the snapshot already installed if there is one (a generation
    inside a bootstrap is one pin), else one taken now, installed, and
    released however the block ends."""
    held = _installed
    if held is not None:
        yield held
        return
    with ConfigSnapshot.take() as snapshot:
        yield snapshot


def adopt(snapshot: ConfigSnapshot | None) -> None:
    """A started process's half of the hand-off (assets.adopt): install the
    snapshot it was handed - verified against its digest first - or, handed
    none, hold none. A no-op when it already holds that snapshot."""
    global _installed
    if snapshot == _installed:
        return
    if _installed is not None:
        _installed.release()
    if snapshot is not None:
        snapshot.verify()
        snapshot.install()
