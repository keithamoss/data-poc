"""Pointing the resolver at an asset folder a test made (REQ-PIPE-342
criterion 7) - what the `asset_folder` fixture does, for the shared helpers
that are handed only monkeypatch.

A FOLDER IS COMPLETED FROM THE REAL ONE: every entry of the selected asset's
real configuration folder the test did not write is linked in, so a test that
writes only data-asset.yaml still has the real calendar, presentation and
agency folders beside it - as it did when only one path constant was moved.
"""
from __future__ import annotations

from pathlib import Path

from qa_tools.common import assets


def complete(folder: Path) -> Path:
    """Link into `folder` every entry of the real asset folder it lacks."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    real = assets.selected().folder
    if real.resolve() == folder.resolve():
        return folder
    for entry in real.iterdir():
        target = folder / entry.name
        if not target.exists() and not target.is_symlink():
            target.symlink_to(entry)
    return folder


def point(folder: Path, *, link: tuple[str, ...] | None = None) -> Path:
    """Point the selected asset's configuration at `folder` for the rest of
    the test (the suite's autouse `selected_asset` fixture puts it back),
    completed from the real folder - or, with `link`, given only those real
    entries it lacks, for a test whose gate scans the folder itself."""
    if link is None:
        complete(folder)
    else:
        real = assets.selected().folder
        for name in link:
            target = Path(folder) / name
            if not target.exists() and not target.is_symlink():
                target.symlink_to(real / name)
    assets.use_root(None)
    assets.use_folder(Path(folder))
    return Path(folder)


def with_file(tmp: Path, name: str, source: Path) -> Path:
    """A completed folder under `tmp` whose `name` is a link to `source` - for
    a test that wrote a file somewhere of its own and pointed one constant at
    it. A `source` that does not exist (yet) stays missing until it does.
    Returns the folder."""
    folder = Path(tmp) / f"asset-with-{name.replace('/', '-')}"
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / name
    if target.is_symlink() or target.exists():
        target.unlink()
    target.symlink_to(Path(source).absolute())
    return point(folder)


def replace(name: str, text: str) -> Path:
    """Write `name` into the folder the resolver points at now, as a file of
    its own - never through a link into the real asset folder, and never into
    the real folder itself."""
    from qa_tools.common import assets as _assets

    folder = _assets.selected().folder
    real = _assets._DEFAULT.asset(_assets.selected().name).folder
    if folder.resolve() == real.resolve():
        raise AssertionError("refusing to write into the real asset folder - point at a copy first")
    path = folder / name
    if path.is_symlink():
        path.unlink()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


class pointed:
    """`with pointed(folder):` - the resolver pointed at a completed `folder`
    inside the block, and back at what it pointed at before after it."""

    def __init__(self, folder: Path):
        self.folder = Path(folder)

    def __enter__(self) -> Path:
        complete(self.folder)
        self.before = assets.use_folder(self.folder)
        return self.folder

    def __exit__(self, *exc) -> None:
        assets.restore(self.before)


def real_folder() -> Path:
    """The selected asset's committed configuration folder,
    assets/<asset>/ - what a test reading "the real one" reads since the
    split (it was contract/). Asked when called, so a module evaluating it at
    import gets the asset it is imported under (tests/conftest.py)."""
    return Path(__file__).resolve().parent.parent / "assets" / assets.selected().name
