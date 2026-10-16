"""A generated reports/ file is replaced whole or not at all (CI on d6dce26,
2026-10-11: tests/test_history_rekey.py read the built Child Protection results file while
another xdist worker's dashboard build was rewriting it, and parsed half a
file - "Expecting ',' delimiter: line 63142").

A reader in another process must only ever see the old file or the new one,
which a write that truncates and streams in place cannot promise."""
from __future__ import annotations

import json

import pytest

import rebuild_support


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


@pytest.mark.parametrize("module", rebuild_support.REBUILDS)
def test_an_interrupted_rebuild_leaves_the_previous_results_whole(
        module, clean_qa_history, tmp_path, monkeypatch):
    """Both results writers, driven for real and interrupted part-way
    through writing: the results file a reader would open is still the
    previous one, whole. A writer that truncated and streamed in place
    would leave half a file - the shape CI parsed on d6dce26."""
    previous = {"results": ["the previous build"]}
    (tmp_path / "results.json").write_text(json.dumps(previous))
    real_dump = json.dump

    def interrupted(obj, f, **kwargs):
        f.write('{"results": [')
        raise RuntimeError("interrupted part-way")

    monkeypatch.setattr(json, "dump", interrupted)
    with pytest.raises(RuntimeError, match="interrupted"):
        rebuild_support.rebuild(module, tmp_path, monkeypatch)
    monkeypatch.setattr(json, "dump", real_dump)

    assert json.loads((tmp_path / "results.json").read_text()) == previous
