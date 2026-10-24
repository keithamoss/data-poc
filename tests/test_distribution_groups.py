"""REQ-TEST-281 criteria 1 and 2: how pytest-xdist hands tests to workers.

`--dist loadgroup` schedules by xdist_group, and tests/conftest.py gives
every test one: its file, except tests/test_dashboard_e2e.py, whose tests are
grouped by file and class. These assert on the real items of the running
session - the hook's own output - rather than on the hook's source.
"""
from __future__ import annotations

import conftest


def _groups(item) -> list[str]:
    return [m.args[0] if m.args else m.kwargs.get("name") for m in item.iter_markers("xdist_group")]


def _file(item) -> str:
    return item.nodeid.split("::", 1)[0]


def test_every_collected_test_has_exactly_one_group(request):
    items = request.session.items
    assert items, "no collected items - this test proves nothing"
    without = [i.nodeid for i in items if len(_groups(i)) != 1]
    assert without == [], without


def test_a_module_outside_the_browser_tests_is_one_group(request):
    """So it runs whole on one worker, exactly as --dist loadfile kept it."""
    others = [i for i in request.session.items if i.path.name not in conftest.SPREAD_BY_CLASS]
    assert others, "no items outside the browser tests - this test proves nothing"
    wrong = [(i.nodeid, _groups(i)) for i in others if _groups(i) != [_file(i)]]
    assert wrong == [], wrong[:5]
    mine = [i for i in others if i.path.name == "test_distribution_groups.py"]
    assert len({g for i in mine for g in _groups(i)}) == 1


def test_under_loadgroup_the_scheduler_sees_the_group(request):
    """The mark has to be on the item before pytest-xdist's own hook turns it
    into the `@group` suffix its scheduler reads - which is why conftest's hook
    is tryfirst. Without the suffix every test would be its own unit."""
    suffixed = request.node.nodeid.endswith("@" + _file(request.node))
    # Serial (-n0) there is no worker, no scheduler and no suffix; it is
    # asserted either way.
    scheduled = hasattr(request.config, "workerinput") and request.config.getvalue("loadgroup")
    assert suffixed == bool(scheduled), request.node.nodeid
