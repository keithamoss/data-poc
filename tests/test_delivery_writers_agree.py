"""REQ-GEN-386 criterion 8: the delivery format has two writers - the real
pipeline's (qa_tools/common/delivery.py, which hand filing calls) and the
generator's own (generator/delivery_writer.py) - and one reader
(asset_model/delivery.py). The same deliveries written through each into two
empty trees must agree byte for byte, and read back the same, so the two
copies of the format cannot drift apart unnoticed.

Critical (REQ-TEST-375): a drift would break every bootstrap and every hand
filing at once, and this needs no database.
"""
from __future__ import annotations

import io
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from asset_model import delivery as tree
from generator import delivery_writer
from qa_tools.common import delivery as pipeline_writer

T0 = datetime(2026, 3, 2, 1, 15, tzinfo=timezone.utc)


def _zip_bytes() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("cp_clients.csv", "cp_client_id,postcode\nC1,6000\n")
        z.writestr("cp_carers.csv", "carer_id\nK1\n")
    return buf.getvalue()


#: (name, files, receipt instant(s)) - a plain folder of several files each
#: received at its own instant, and a zip-shaped one received at once.
DELIVERIES = (
    ("2026-03-plain", {"birth_registrations_2026-03-01.csv": "registration_number\nBR1\n",
                       "birth_registrations_2026-03-02.csv": "registration_number\nBR2\n",
                       "readme.txt": b"\x00\x01binary"},
     {"birth_registrations_2026-03-01.csv": T0,
      "birth_registrations_2026-03-02.csv": T0 + timedelta(minutes=7),
      "readme.txt": T0 + timedelta(minutes=3)}),
    ("2026-Q1-zip", {"cp_2026_Q1.zip": _zip_bytes()}, T0 + timedelta(days=1)),
)


def _write(writer, root: Path) -> None:
    for name, files, received in DELIVERIES:
        writer.write_delivery(name, files, received_at=received,
                              deliveries_dir=root / "deliveries", receipts_dir=root / "receipts",
                              received_from=tree.RECEIVED_FROM_STORAGE)


def _bytes(root: Path) -> dict[str, bytes]:
    files = {str(p.relative_to(root)): p.read_bytes() for p in sorted(root.rglob("*"))
             if p.is_file()}
    assert files, "test precondition - the writer wrote something"
    return files


def test_both_writers_write_the_same_bytes(tmp_path):
    _write(pipeline_writer, tmp_path / "pipeline")
    _write(delivery_writer, tmp_path / "generator")
    ours, theirs = _bytes(tmp_path / "pipeline"), _bytes(tmp_path / "generator")
    assert sorted(ours) == sorted(theirs)
    differing = [path for path in ours if ours[path] != theirs[path]]
    assert differing == [], differing


def test_the_one_reader_reads_both_back_the_same(tmp_path):
    read = {}
    for side, writer in (("pipeline", pipeline_writer), ("generator", delivery_writer)):
        root = tmp_path / side
        _write(writer, root)
        read[side] = [tree.read_delivery(name, root / "deliveries", root / "receipts")
                      for name, _files, _received in DELIVERIES]
    for ours, theirs in zip(read["pipeline"], read["generator"]):
        assert (ours.files, ours.received_at, ours.sequence, ours.received_from,
                dict(ours.file_receipts), dict(ours.filed_by), ours.anomalies) == \
            (theirs.files, theirs.received_at, theirs.sequence, theirs.received_from,
             dict(theirs.file_receipts), dict(theirs.filed_by), theirs.anomalies)
    assert len(read["generator"][0].file_receipts) == 3


def test_a_drifted_writer_is_caught(tmp_path, monkeypatch):
    """The comparison can fail: a generator writer numbering its receipts one
    on is a differing byte."""
    real = delivery_writer.next_sequence
    monkeypatch.setattr(delivery_writer, "next_sequence", lambda *a, **k: real(*a, **k) + 1)
    _write(pipeline_writer, tmp_path / "pipeline")
    _write(delivery_writer, tmp_path / "generator")
    ours, theirs = _bytes(tmp_path / "pipeline"), _bytes(tmp_path / "generator")
    assert any(ours[p] != theirs[p] for p in ours)


pytestmark = [pytest.mark.critical, pytest.mark.asset("daily")]
