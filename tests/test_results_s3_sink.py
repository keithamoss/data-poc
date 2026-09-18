"""Tests for qa_tools/common/results_s3_sink.py - see its own docstring
for why qa_results_writer.py itself stays S3-unaware. Mocked boto3
client, no real AWS."""
from __future__ import annotations
from unittest.mock import MagicMock

from qa_tools.common.results_s3_sink import upload_qa_result


def test_upload_qa_result_uses_the_path_relative_to_qa_results_root_as_the_key(tmp_path):
    root = tmp_path / "qa_results"
    local_path = root / "registry-services" / "birth-registrations" / "run_042" / "dbt.json"
    local_path.parent.mkdir(parents=True)
    local_path.write_text("{}")

    client = MagicMock()
    key = upload_qa_result(str(local_path), str(root), "my-results-bucket", s3_client=client)

    assert key == "registry-services/birth-registrations/run_042/dbt.json"
    client.upload_file.assert_called_once_with(str(local_path), "my-results-bucket", key)


def test_upload_qa_result_builds_a_real_boto3_client_when_none_is_passed(tmp_path, monkeypatch):
    root = tmp_path / "qa_results"
    local_path = root / "a" / "b" / "run_01" / "soda.json"
    local_path.parent.mkdir(parents=True)
    local_path.write_text("{}")

    fake_client = MagicMock()
    fake_boto3 = MagicMock()
    fake_boto3.client.return_value = fake_client
    monkeypatch.setitem(__import__("sys").modules, "boto3", fake_boto3)

    key = upload_qa_result(str(local_path), str(root), "bucket")

    fake_boto3.client.assert_called_once_with("s3")
    fake_client.upload_file.assert_called_once_with(str(local_path), "bucket", key)
