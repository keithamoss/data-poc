"""post-build-review #485 (Keith, 2026-11-21): under pytest the bootstrap runs
its collection streams one after another in the test's own process, so a stub
a test installs by monkeypatch always applies. A spawned stream process has
none of the test's patches: twice a "stubbed" bootstrap of a two-collection
asset really staged and checked the checkout's deliveries, for over two hours.
A test that needs the real process pool asks for it with `real_stream_pool`."""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.asset("daily")


def test_a_stubbed_stream_runs_in_the_tests_own_process(monkeypatch):
    from bootstrap import bootstrap as boot

    assert boot._run_concurrently.__qualname__ != "_run_concurrently", "the real pool"
    ran = []
    monkeypatch.setattr(boot, "_run_stream", lambda key, sequential: ran.append(key) or 1.5)
    timings, reports = boot._run_concurrently(["no-such-stream-a", "no-such-stream-b"], False)
    assert ran == ["no-such-stream-a", "no-such-stream-b"]
    assert timings == {"no-such-stream-a": 1.5, "no-such-stream-b": 1.5}
    assert set(reports) == {"no-such-stream-a", "no-such-stream-b"}


@pytest.mark.real_stream_pool
def test_a_test_that_asks_for_the_pool_gets_it():
    from concurrent.futures import ProcessPoolExecutor

    from bootstrap import bootstrap as boot

    assert boot._run_concurrently.__qualname__ == "_run_concurrently"
    with boot.stream_pool(1) as pool:
        assert isinstance(pool, ProcessPoolExecutor)
