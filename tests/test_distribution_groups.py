"""REQ-TEST-281 criteria 1 and 2: how pytest-xdist hands tests to workers.

`--dist loadgroup` schedules by xdist_group, and tests/conftest.py gives
every test one: its file, except tests/test_dashboard_e2e.py, whose tests are
grouped by file and class. These assert on the real items of the running
session - the hook's own output - rather than on the hook's source.
"""
from __future__ import annotations

import pytest

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
    others = [i for i in request.session.items
              if i.path.name not in conftest.SPREAD_BY_CLASS
              and i.path.name not in conftest.SHARE_THE_DEPLOYMENT]
    assert others, "no items outside the browser tests - this test proves nothing"
    wrong = [(i.nodeid, _groups(i)) for i in others if _groups(i) != [_file(i)]]
    assert wrong == [], wrong[:5]
    mine = [i for i in others if i.path.name == "test_distribution_groups.py"]
    assert len({g for i in mine for g in _groups(i)}) == 1


def test_the_deployment_writers_and_counters_share_one_group(request):
    """Post-build-review #323: the deployment-half modules that write and the
    ones that count run on one worker, so one cannot count rows the other is
    writing. They are the one exception to a group per file."""
    shared = [i for i in request.session.items if i.path.name in conftest.SHARE_THE_DEPLOYMENT]
    groups = {g for i in shared for g in _groups(i)}
    assert groups <= {"deployment-writers-and-counters"}, groups


def test_under_loadgroup_the_scheduler_sees_the_group(request):
    """The mark has to be on the item before pytest-xdist's own hook turns it
    into the `@group` suffix its scheduler reads - which is why conftest's hook
    is tryfirst. Without the suffix every test would be its own unit."""
    suffixed = request.node.nodeid.endswith("@" + _file(request.node))
    # Serial (-n0) there is no worker, no scheduler and no suffix; it is
    # asserted either way.
    scheduled = hasattr(request.config, "workerinput") and request.config.getvalue("loadgroup")
    assert suffixed == bool(scheduled), request.node.nodeid


#: The data asset this module's tests act for, unless a test says otherwise
#: (C11, Keith 2026-11-02: every test module names its asset).
pytestmark = pytest.mark.asset("quarterly")
