"""A generated reports/ file is replaced whole or not at all (CI on d6dce26,
2026-10-11: tests/test_history_rekey.py read the built Child Protection results file while
another xdist worker's dashboard build was rewriting it, and parsed half a
file - "Expecting ',' delimiter: line 63142").

A reader in another process must only ever see the old file or the new one,
which a write that truncates and streams in place cannot promise."""
from __future__ import annotations

import json

import pytest


def test_an_interrupted_write_leaves_the_previous_file_whole(tmp_path):
    from qa_tools.common import atomic_file

    path = tmp_path / "results.json"
    atomic_file.write_json(path, {"results": [1, 2, 3]})

    class Boom:
        def __repr__(self):
            raise RuntimeError("interrupted part-way")

    with pytest.raises(Exception):
        atomic_file.write_json(path, {"results": [Boom()]})
    assert json.loads(path.read_text()) == {"results": [1, 2, 3]}
    assert [p.name for p in tmp_path.iterdir()] == ["results.json"], "no temp file left"


@pytest.mark.parametrize("module", ["qa_tools.bdm.build_results_from_history",
                                    "qa_tools.cp.build_results_from_history"])
def test_both_results_writers_write_atomically(module):
    import importlib
    import inspect

    source = inspect.getsource(importlib.import_module(module))
    assert "atomic_file.write_json(RESULTS_PATH" in source
    assert 'open(RESULTS_PATH, "w")' not in source
