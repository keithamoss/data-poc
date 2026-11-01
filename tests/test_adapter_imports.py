"""An adapter imports shared code and the standard library only
(REQ-PIPE-369 criterion 3): one that imports another adapter, a generator
provider or anything under assets/ fails the collections gate, naming it."""
from __future__ import annotations

from pathlib import Path

import pytest

from qa_tools.common import assets
from qa_tools.common import validate_collections as gate


@pytest.fixture
def adapters(tmp_path) -> Path:
    """The selected asset's adapter folder, copied, for a test to add to."""
    folder = tmp_path / "adapters"
    folder.mkdir()
    for real in assets.selected().adapters.glob("*.py"):
        (folder / real.name).symlink_to(real)
    assets.use_folder(assets.selected().folder, adapters=folder)
    return folder


def _imports(folder: Path, text: str) -> None:
    target = folder / "emergency_department.py"
    real = target.resolve().read_text()
    target.unlink()
    target.write_text(text + "\n" + real)


class TestTheGate:

    def test_todays_adapters_pass(self, adapters):
        assert gate.adapter_import_problems() == []

    @pytest.mark.parametrize("line", [
        "from qa_tools.collections import child_protection",
        "from qa_tools.collections.child_protection import ADAPTER as _other",
        "import qa_tools.collections.civil_registration",
        "from generator.collections import emergency_department as _p",
        "import generator.collections.linkage_products",
        "import mothman_adapter_data_asset_1_child_protection",
        "from assets.quarterly.collections import x",
    ])
    def test_an_adapter_reaching_another_adapter_a_provider_or_assets_fails(self, adapters, line):
        _imports(adapters, line)
        problems = gate.adapter_import_problems()
        assert len(problems) == 1, problems
        assert "emergency_department.py" in problems[0]
        assert line.split()[1] in problems[0]

    def test_shared_code_and_the_standard_library_pass(self, adapters):
        _imports(adapters, "import re\nfrom qa_tools.collections.base import CollectionAdapter\n"
                           "from qa_tools.common import hierarchy\nfrom generator.collections.base import Plan")
        assert gate.adapter_import_problems() == []

    def test_the_gate_reports_it(self, adapters):
        _imports(adapters, "from qa_tools.collections import child_protection")
        assert any("emergency_department.py" in p and "child_protection" in p
                   for p in gate.config_problems())
