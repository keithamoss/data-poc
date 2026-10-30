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
