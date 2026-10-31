"""The processing pass builds every arrival from the delivery records
(REQ-PIPE-152 criterion 6; Keith, 2026-10-06) - the same arrivals disk
recognition gives, plus an object a handler recorded straight from S3."""
from __future__ import annotations

import dataclasses
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from qa_tools.common import arrivals, s3_arrival

LANDED = datetime(2031, 6, 7, 1, 2, 3, tzinfo=timezone.utc)


def _comparable(found):
    return [dataclasses.replace(a, sources=()) for a in found]


@pytest.mark.needs_deployment
class TestTheSameArrivalsAsTheTree:
    """Pinned over the whole deployment: every field disk recognition
    gives, in the same order, for both collections."""

    @pytest.mark.parametrize("collection_id,prefix", [("civil-registration", "run_"),
                                                      ("child-protection", "cp_run_")])
    def test_identical(self, deployment_history, collection_id, prefix):
        from_tree = arrivals.arrivals_for(collection_id, prefix)
        from_rows = arrivals.arrivals_from_records(collection_id)
        assert from_tree, "the deployment holds no arrivals - bootstrap first"
        assert _comparable(from_rows) == from_tree


def _client():
    client = MagicMock()
    client.head_object.return_value = {"LastModified": LANDED}
    client.download_file.side_effect = lambda b, k, p: Path(p).write_text("id\n1\n")
    return client


class TestAnObjectRecordedFromS3IsAnArrival:

    def test_it_is_offered_with_its_storage_uri_and_fetched_to_stage(self, supply_dsn,
                                                                      tmp_path):
        import uuid

        bucket = f"raw-{uuid.uuid4().hex[:8]}"
        got = s3_arrival.record_object(_client(), bucket, "cp/cp_carers.csv")
        [found] = [a for a in arrivals.arrivals_from_records("child-protection",
                                                             tmp_path / "deliveries")
                   if a.delivery_name == got.delivery_name]
        assert found.files_by_dataset == {"cp-carers": ("cp_carers.csv",)}
        assert found.received_at == LANDED
        assert found.sources == (("cp_carers.csv", f"s3://{bucket}/cp/cp_carers.csv"),)
        assert not found.path.exists(), "nothing was copied when it was recorded"

        client = _client()
        local = s3_arrival.materialise(found, s3_client=client, root=tmp_path)
        assert (local.path / "cp_carers.csv").read_text() == "id\n1\n"
        client.download_file.assert_called_once()
        assert local.run_id == found.run_id

    def test_a_local_arrival_is_left_where_it_is(self, tmp_path):
        local = arrivals.Arrival(run_id="r", run_index=1, collection_id="c", delivery_name="d",
                                 path=tmp_path, received_at=LANDED, sequence=1,
                                 files_by_dataset={}, unmatched=(), anomalies=())
        assert s3_arrival.materialise(local) is local


class TestALocalRecordWhoseDirectoryIsGoneIsNotAnArrival:
    """The orphan CLAUDE.md records from 2026-09-28: a record the tree no
    longer holds would be an arrival nobody can read."""

    def test_it_is_not_offered(self, supply_dsn, tmp_path):
        import uuid

        from qa_tools.common import delivery, delivery_log

        name = f"gone-{uuid.uuid4().hex[:8]}"
        d = delivery.Delivery(name=name, path=tmp_path / name, received_at=LANDED,
                              files=("cp_clients.csv",), anomalies=(), sequence=1)
        delivery_log.record(d, arrivals.recognise(d))
        offered = {a.delivery_name for a in arrivals.arrivals_from_records(
            "child-protection", tmp_path)}
        assert name not in offered
        (tmp_path / name).mkdir()
        offered = {a.delivery_name for a in arrivals.arrivals_from_records(
            "child-protection", tmp_path)}
        assert name in offered
