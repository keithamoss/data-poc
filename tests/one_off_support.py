"""A one-offs root in a temporary folder, with a TEST KIND registered for it.

THE TEST KIND IS NOT THE EXTRACTION. The extraction's recipe reader and its
generated folder are REQ-PIPE-439's and REQ-PIPE-440's; REQ-PIPE-446 is the
kind-neutral layer, so it is driven through a minimal kind - 'audit' /
'audits' - whose folders carry only a data-asset.yaml.
"""
from __future__ import annotations

from pathlib import Path

import yaml

from asset_model import assets, one_off_kinds

KIND = "audit"
AUDIT = one_off_kinds.Kind(name=KIND, singular="audit", plural="audits", layer="Audit check")


def make(root: Path, kind: str, name: str, *, project: str | None = "A test project",
         data_asset_id: str | None = None) -> Path:
    folder = root / kind / name
    folder.mkdir(parents=True)
    doc = {"data_asset_id": data_asset_id or name}
    if project is not None:
        doc["project"] = project
    (folder / "data-asset.yaml").write_text(yaml.safe_dump(doc))
    return folder


class OneOffs:
    """The temporary root, pointed at by the resolver, with the test kind
    registered; undone by close()."""

    def __init__(self, tmp_path: Path, monkeypatch):
        self.root = tmp_path / "one-offs"
        self.root.mkdir()
        (self.root / KIND).mkdir()
        (self.root / KIND / "_template").mkdir()
        self._before = assets.use_one_offs_root(self.root)
        one_off_kinds.register(AUDIT)
        monkeypatch.delenv(assets.ASSET_ENV, raising=False)

    def add(self, name: str, kind: str = KIND, **kw) -> Path:
        return make(self.root, kind, name, **kw)

    def close(self) -> None:
        assets.deselect_one_off()
        assets.restore(self._before)
        one_off_kinds.unregister(KIND)
