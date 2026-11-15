"""A provider imports shared code and the standard library only (REQ-GEN-370
criterion 5): one that imports another provider, an adapter or anything under
assets/ fails the providers gate, naming it.

WHY THE IMPORTS GATE DOES NOT ALREADY CATCH IT: REQ-TEST-384's gate sides
every provider with the generator, so one provider importing another is an
import inside one side and allowed there. This is the providers gate's own
rule, as the collections gate has one for adapters (REQ-PIPE-369 criterion 3,
tests/test_adapter_imports.py).

WHAT IT REFUSES: an import statement - at module or function level, under
`if TYPE_CHECKING:` too - naming another provider, an adapter or anything
under assets/, a relative import, and a load by path (the resolver's load,
importlib, __import__). WHAT IT DOES NOT: a lookup through the shared
provider registry, which is how Linkage Products reads the collections it
declares in `depends_on` (REQ-GEN-334 criterion 6) - PROVISIONAL, see
REQ-GEN-370's decisions."""
from __future__ import annotations

from pathlib import Path

import pytest

from qa_tools.common import assets

ROOT = Path(__file__).resolve().parent.parent

#: The provider a test edits - a quarterly one with no declared dependency.
EDITED = "emergency_department.py"


@pytest.fixture
def providers_root(tmp_path) -> Path:
    """An assets/ root whose quarterly providers folder is a folder of its
    own - every real provider linked in, EDITED copied so a test can add a
    line to it - and every other entry linked to the real one. The resolver
    points at it for the test (the autouse fixture puts it back)."""
    root = tmp_path / "assets"
    root.mkdir()
    real_root = ROOT / "assets"
    for entry in real_root.iterdir():
        if entry.name != "quarterly":
            (root / entry.name).symlink_to(entry)
    quarterly = root / "quarterly"
    quarterly.mkdir()
    for entry in (real_root / "quarterly").iterdir():
        if entry.name != "synthetic":
            (quarterly / entry.name).symlink_to(entry)
    synthetic = quarterly / "synthetic"
    synthetic.mkdir()
    for entry in (real_root / "quarterly" / "synthetic").iterdir():
        if entry.name != "collections":
            (synthetic / entry.name).symlink_to(entry)
    folder = synthetic / "collections"
    folder.mkdir()
    for real in (real_root / "quarterly" / "synthetic" / "collections").glob("*.py"):
        if real.name == EDITED:
            (folder / real.name).write_text(real.read_text())
        else:
            (folder / real.name).symlink_to(real)
    assets.use_root(root)
    return folder


def _add(folder: Path, text: str) -> None:
    """`text` at the top of the edited provider, after its future import."""
    target = folder / EDITED
    head, sep, rest = target.read_text().partition("from __future__ import annotations\n")
    assert sep, "precondition: the provider has a future import to add after"
    target.write_text(head + sep + text + "\n" + rest)


def _gate():
    from generator import validate_providers
    return validate_providers


class TestTheRule:

    def test_todays_providers_pass_on_each_asset(self, monkeypatch):
        for name in ("quarterly", "daily"):
            monkeypatch.setenv(assets.ASSET_ENV, name)
            found = list(assets.selected().providers.glob("*.py"))
            assert found, f"precondition: asset {name} has providers"
            assert _gate().provider_import_problems() == [], name

    @pytest.mark.parametrize("line", [
        # Another provider, every way it can be named.
        "import mothman_provider_quarterly_child_protection",
        "from mothman_provider_quarterly_child_protection import PROVIDER as _other",
        "from assets.quarterly.synthetic.collections import child_protection",
        "import assets.daily.synthetic.collections.civil_registration",
        "from generator.collections import linkage_products",
        "from . import child_protection",
        # An adapter, its own collection's included.
        "from qa_tools.collections import emergency_department as _adapter",
        "import qa_tools.collections.child_protection",
        "import mothman_adapter_quarterly_emergency_department",
        # Anything under assets/.
        "from assets.quarterly import whatever",
    ])
    def test_a_provider_importing_another_provider_an_adapter_or_assets_fails(
            self, providers_root, line):
        _add(providers_root, line)
        problems = _gate().provider_import_problems()
        assert len(problems) == 1, problems
        assert EDITED in problems[0]
        assert line in problems[0]
        assert "REQ-GEN-370 criterion 5" in problems[0]

    @pytest.mark.parametrize("line", [
        "def _late():\n    from mothman_provider_quarterly_child_protection import PROVIDER\n"
        "    return PROVIDER",
        "from typing import TYPE_CHECKING\nif TYPE_CHECKING:\n"
        "    from qa_tools.collections import child_protection",
    ])
    def test_a_function_level_or_type_checking_import_fails_too(self, providers_root, line):
        _add(providers_root, line)
        problems = _gate().provider_import_problems()
        assert len(problems) == 1, problems
        assert EDITED in problems[0]

    @pytest.mark.parametrize("line, needle", [
        ("from qa_tools.common import assets as _a\n"
         "def _p():\n    return _a.load('provider', 'child_protection')",
         "_a.load('provider', 'child_protection')"),
        ("from qa_tools.common import assets\n"
         "def _p():\n    return assets.module_file('adapter', 'x')",
         "assets.module_file('adapter', 'x')"),
        ("import importlib", "import importlib"),
        ("from importlib import util as _u", "from importlib import util as _u"),
        ("def _p():\n    return __import__('mothman_provider_quarterly_child_protection')",
         "__import__("),
    ])
    def test_a_load_by_path_or_by_name_fails(self, providers_root, line, needle):
        _add(providers_root, line)
        problems = _gate().provider_import_problems()
        assert len(problems) == 1, problems
        assert EDITED in problems[0] and needle in problems[0]

    def test_shared_code_and_the_standard_library_pass(self, providers_root):
        _add(providers_root,
             "import json\nimport re\nfrom generator.collections.base import Job\n"
             "from generator import targeting as _t\nfrom qa_tools.common import hierarchy\n"
             "from qa_tools.collections.base import CollectionAdapter\n"
             "def _read(f):\n    return json.load(f)")
        assert _gate().provider_import_problems() == []

    def test_a_lookup_through_the_shared_registry_passes(self, providers_root):
        """PROVISIONAL (REQ-GEN-370's decisions): Linkage Products reads the
        collections it declares in depends_on through the registry."""
        _add(providers_root, "def _dep():\n    from generator import collections\n"
                             "    return collections.for_dataset('cp-clients')")
        assert _gate().provider_import_problems() == []


class TestTheGateReportsIt:

    def test_the_providers_gate_fails_naming_the_file_and_the_import(self, providers_root,
                                                                       capsys):
        line = "from qa_tools.collections import child_protection as _adapter"
        _add(providers_root, line)
        gate = _gate()
        problems = gate.problems()
        assert any(EDITED in p and line in p for p in problems), problems
        assert gate.main() == 1
        assert line in capsys.readouterr().err

    def test_a_provider_that_cannot_be_imported_is_a_finding_not_a_traceback(
            self, providers_root):
        """post-build-review #336: a provider whose own import fails raised
        out of the gate, so `mothman check` showed a ModuleNotFoundError
        traceback where the collections gate names an adapter that cannot be
        imported. It is named, with the error."""
        _add(providers_root, "import no_such_module_anywhere_st4")
        problems = _gate().problems()
        assert any(EDITED in p and "no_such_module_anywhere_st4" in p for p in problems), problems


#: The data asset this module's tests act for, unless a test says otherwise
#: (C11, Keith 2026-11-02: every test module names its asset).
pytestmark = pytest.mark.asset("quarterly")
