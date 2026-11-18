"""Whether this deployment can make synthetic data, and the commands that need
it (REQ-PIPE-385 criteria 2, 3 and 6).

ONE `mothman`, ITS SYNTHETIC COMMANDS PRESENT ONLY WHERE THEY CAN RUN (Q3,
SETTLED by Keith 2026-11-02): a synthetic command is listed in `--help`, its
group's help and the terminal's menus only where every component it needs is
present AND the selected asset has a synthetic/ folder. Invoked by name where
it is not, it is refused in one sentence with exit 1 - never an ImportError or
'No such command' (REQ-GEN-370 criterion 8's refusal by name, kept).

FIND_SPEC, NEVER AN IMPORT (B5): a real import at start-up would cost every
`--help`, and a check that imported would disagree with a test blocking the
import at find_spec. importlib.util.find_spec answers None for a package a
real deployment leaves out and for one a test blocks (sys.modules[name] =
None), so what the CLI detects and what the test blocks agree.
"""
from __future__ import annotations

import importlib
import importlib.util

import rich_click as click

#: What making synthetic data needs: the generator, the population-scale
#: generator, the scenario design and the bootstrap - what a real deployment
#: leaves out (SPLIT D1).
COMPONENTS = ("generator", "synthetic_data_generator", "scenarios", "bootstrap")


def missing_components() -> list[str]:
    """The components find_spec cannot find, in COMPONENTS' order."""
    out = []
    for name in COMPONENTS:
        try:
            found = importlib.util.find_spec(name) is not None
        except (ImportError, ValueError):
            found = False
        if not found:
            out.append(name)
    return out


def _asset():
    from asset_model import assets

    return assets.selected_or_none()


def asset_has_synthetic() -> bool:
    """Whether the selected asset has a synthetic/ folder. With no asset
    selected nothing is known to be missing, so nothing is hidden; a command
    that needs the asset refuses for want of one."""
    asset = _asset()
    return asset is None or asset.synthetic.is_dir()


def available() -> bool:
    return not missing_components() and asset_has_synthetic()


def refusal(command: str) -> str:
    """The one sentence a synthetic command is refused with, naming what is
    missing (criterion 6)."""
    gone = missing_components()
    if gone:
        return (f"`{command}` generates synthetic data, and this deployment does not have "
                f"{_listed(gone)} - it processes real supplies only.")
    asset = _asset()
    return (f"`{command}` generates synthetic data, and asset {asset.name} has no synthetic/ "
            f"folder (assets/{asset.name}/synthetic/) - this deployment processes real "
            f"supplies only.")


def _listed(names: list[str]) -> str:
    shown = [f"{n}/" for n in names]
    return shown[0] if len(shown) == 1 else ", ".join(shown[:-1]) + " or " + shown[-1]


def refuse(command: str) -> None:
    """Refuse `command` by name where synthetic data cannot be made here."""
    if not available():
        raise click.ClickException(refusal(command))


def refuse_flags(command: str, **given) -> None:
    """Refuse a synthetic-mode flag by name where synthetic data cannot be
    made here (criterion 7) - `run_id=...` is `--run-id`."""
    if available():
        return
    for name, value in given.items():
        if value is not None:
            raise click.ClickException(refusal(f"{command} --{name.replace('_', '-')}"))


def _refusing(name: str, path: str) -> click.Command:
    """A hidden stand-in that refuses by name - whatever it is given, flags
    included, so the refusal is the answer and not a usage error."""
    @click.command(name, hidden=True, add_help_option=False,
                   context_settings={"ignore_unknown_options": True,
                                     "allow_extra_args": True})
    def stand_in() -> None:
        raise click.ClickException(refusal(path))
    return stand_in


class Group(click.RichGroup):
    """A group some of whose commands make synthetic data. `synthetic` names
    them; `lazy` maps a name to (module, attribute) for a command whose module
    imports a synthetic component, loaded only where it can run."""

    def __init__(self, *args, synthetic=(), lazy=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.synthetic = set(synthetic) | set(lazy or {})
        self.lazy = dict(lazy or {})

    def _path(self, ctx, name: str) -> str:
        """`mothman <group>... <name>`, however the root was invoked."""
        names = []
        while ctx is not None and ctx.parent is not None:
            names.append(ctx.info_name)
            ctx = ctx.parent
        return " ".join(["mothman", *reversed(names), name])

    def list_commands(self, ctx):
        names = set(super().list_commands(ctx)) | set(self.lazy)
        if not available():
            names -= self.synthetic
        return sorted(names)

    def get_command(self, ctx, name):
        if name in self.synthetic and not available():
            return _refusing(name, self._path(ctx, name))
        if name in self.lazy and name not in self.commands:
            module, attribute = self.lazy[name]
            self.add_command(getattr(importlib.import_module(module), attribute), name)
        return super().get_command(ctx, name)
