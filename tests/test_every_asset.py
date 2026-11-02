"""What every asset's configuration declares, read once for the checks that
must tell another asset's name from a typo (Keith, 2026-11-03, morning report
12 Q6 and Q8): the scenario drop warning, the scenario refusal at generation
(REQ-GEN-246 criterion 8) and the feedback validator's agency check
(REQ-DOCS-219 criterion 10). Configuration only - never a database."""
from __future__ import annotations

from pathlib import Path

import pytest

from qa_tools.common import assets, every_asset

ROOT = Path(__file__).resolve().parent.parent


def _ids(name: str) -> tuple[set, set, set]:
    from qa_tools.common import config_yaml

    doc = config_yaml.parse((ROOT / "assets" / name / "data-asset.yaml").read_text())
    agencies, collections, datasets = set(), set(), set()
    for ag in doc["hierarchy"]["agencies"]:
        agencies.add(ag["id"])
        for col in ag.get("collections") or []:
            collections.add(col["id"])
            datasets |= {d["id"] for d in col.get("datasets") or []}
    return agencies, collections, datasets


class TestBothAssetsHierarchies:

    @pytest.mark.parametrize("selected", ["quarterly", "daily"])
    def test_it_holds_every_assets_ids_whichever_is_selected(self, monkeypatch, selected):
        monkeypatch.setenv(assets.ASSET_ENV, selected)
        names = assets.names()
        assert len(names) >= 2, "precondition: more than one asset"
        got = every_asset.declared()
        for name in names:
            agencies, collections, datasets = _ids(name)
            assert datasets, f"precondition: {name} declares datasets"
            assert agencies <= got.agencies
            assert collections <= got.collections
            assert datasets <= got.datasets
        assert "no-such-dataset" not in got.datasets

    def test_an_injected_root_is_read_rather_than_the_repositorys(self, monkeypatch, tmp_path):
        """REQ-PIPE-342's injection (#55): the assets the resolver finds."""
        root = tmp_path / "assets"
        for name, ag in (("one", "ag-one"), ("two", "ag-two")):
            (root / name).mkdir(parents=True)
            (root / name / "data-asset.yaml").write_text(
                f"data_asset_id: {name}\nhierarchy:\n  agencies:\n    - id: {ag}\n      name: A\n"
                f"      collections:\n        - id: col-{name}\n          name: C\n"
                f"          contract: c.yaml\n          datasets:\n            - id: ds-{name}\n"
                f"              name: D\n              table: t_{name}\n")
        assets.use_root(root)
        monkeypatch.setenv(assets.ASSET_ENV, "one")
        got = every_asset.declared()
        assert got.agencies == {"ag-one", "ag-two"}
        assert got.collections == {"col-one", "col-two"}
        assert got.datasets == {"ds-one", "ds-two"}

    def test_it_reads_no_database(self, monkeypatch):
        from qa_tools.common import supply_db

        def refuse(*a, **k):
            raise AssertionError("every_asset opened a database")
        monkeypatch.setattr(supply_db, "connect", refuse)
        assert every_asset.declared().datasets


#: Reads both assets' configuration; acts for the quarterly one.
pytestmark = pytest.mark.asset("quarterly")
