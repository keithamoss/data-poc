"""A partial bootstrap replays every collection its checks read
(REQ-PIPE-336 criterion 7; Keith, 2026-10-30: added automatically, and said)."""
from __future__ import annotations

from qa_tools.common import bootstrap


def test_linkage_alone_brings_the_collections_it_links():
    said = []
    got = bootstrap.with_what_it_reads(["lp"], said.append)
    assert set(got) == {"cp", "ed", "lp"}
    assert len(said) == 2 and all("Linkage" in s and "checks read its tables" in s
                                  for s in said)


def test_a_collection_reading_only_itself_is_unchanged():
    said = []
    assert bootstrap.with_what_it_reads(["cp"], said.append) == ["cp"]
    assert said == []


class TestACheckpointOfACollectionReadingOthersIsRefused:
    """Criterion 7's checkpoint half (Keith, 2026-10-30: refuse by name for
    now): a checkpoint counts one collection's own arrivals, so one of a
    collection whose checks read others would replay without them."""

    def test_taking_one_is_refused_naming_what_it_reads(self, monkeypatch):
        from qa_tools.common import checkpoints

        called = []
        monkeypatch.setattr(checkpoints, "require_synthetic", lambda: called.append(1))
        got = bootstrap.bootstrap(collection="lp", checkpoint_before=5)
        assert got.refused and not called, "refused before anything is touched"
        assert "Child Protection" in got.reason and "Emergency Department" in got.reason
        assert "Bootstrap from empty" in got.reason

    def test_resuming_one_is_refused(self, monkeypatch):
        from types import SimpleNamespace

        from qa_tools.common import checkpoints

        monkeypatch.setattr(checkpoints, "require_synthetic", lambda: None)
        monkeypatch.setattr(checkpoints, "find", lambda name: SimpleNamespace(
            name=name, collection_id="linkage-products", before=5,
            recorded=SimpleNamespace(readable=True)))
        copied = []
        monkeypatch.setattr(checkpoints, "copy_for_resume", lambda cp: copied.append(cp))
        got = bootstrap.resume("lp-5")
        assert got.refused and not got.replayed and copied == []
        assert "Child Protection" in got.reason

    def test_a_collection_reading_only_itself_is_not(self):
        assert bootstrap.reads_others("cp") is None
        assert bootstrap.reads_others("ed") is None
