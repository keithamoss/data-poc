"""Tests for qa_tools/common/s3_source.py - see its own docstring for
why this is mocked-boto3-client only (no real AWS access in this
sandbox), same pattern tests/test_results_s3_sink.py already
established."""
from __future__ import annotations
from unittest.mock import MagicMock

from qa_tools.common.s3_source import (
    download_key,
    download_prefix,
    list_delivery_prefixes,
    list_keys,
)


def test_list_keys_returns_sorted_real_keys_under_the_prefix():
    client = MagicMock()
    client.list_objects_v2.return_value = {
        "Contents": [{"Key": "bdm/z.csv"}, {"Key": "bdm/a.csv"}],
    }

    keys = list_keys("my-bucket", "bdm/", s3_client=client)

    assert keys == ["bdm/a.csv", "bdm/z.csv"]
    client.list_objects_v2.assert_called_once_with(Bucket="my-bucket", Prefix="bdm/")


def test_list_keys_handles_an_empty_prefix_with_no_contents_key():
    client = MagicMock()
    client.list_objects_v2.return_value = {}

    assert list_keys("my-bucket", "bdm/nothing-here/", s3_client=client) == []


def test_list_delivery_prefixes_uses_the_delimiter_to_get_real_common_prefixes():
    client = MagicMock()
    client.list_objects_v2.return_value = {
        "CommonPrefixes": [{"Prefix": "cp/delivery_002/"}, {"Prefix": "cp/delivery_001/"}],
    }

    prefixes = list_delivery_prefixes("my-bucket", "cp/", s3_client=client)

    assert prefixes == ["cp/delivery_001/", "cp/delivery_002/"]
    client.list_objects_v2.assert_called_once_with(Bucket="my-bucket", Prefix="cp/", Delimiter="/")


def test_download_key_downloads_to_dest_dir_basename_and_returns_the_local_path(tmp_path):
    client = MagicMock()
    dest_dir = tmp_path / "staging"

    local_path = download_key("my-bucket", "bdm/run_005.csv", str(dest_dir), s3_client=client)

    assert local_path == str(dest_dir / "run_005.csv")
    assert dest_dir.is_dir()
    client.download_file.assert_called_once_with("my-bucket", "bdm/run_005.csv", local_path)


def test_download_key_strips_a_trailing_slash_from_a_prefix_key(tmp_path):
    client = MagicMock()

    local_path = download_key("my-bucket", "cp/delivery_001/", str(tmp_path), s3_client=client)

    assert local_path == str(tmp_path / "delivery_001")


def test_download_prefix_downloads_every_real_key_under_the_prefix_in_sorted_order(tmp_path):
    client = MagicMock()
    client.list_objects_v2.return_value = {
        "Contents": [
            {"Key": "cp/delivery_001/cp_notifications.csv"},
            {"Key": "cp/delivery_001/cp_clients.csv"},
        ],
    }

    local_paths = download_prefix("my-bucket", "cp/delivery_001/", str(tmp_path), s3_client=client)

    assert local_paths == [
        str(tmp_path / "cp_clients.csv"),
        str(tmp_path / "cp_notifications.csv"),
    ]
    assert client.download_file.call_count == 2


def test_functions_build_a_real_boto3_client_when_none_is_passed(tmp_path, monkeypatch):
    fake_client = MagicMock()
    fake_client.list_objects_v2.return_value = {"Contents": []}
    fake_boto3 = MagicMock()
    fake_boto3.client.return_value = fake_client
    monkeypatch.setitem(__import__("sys").modules, "boto3", fake_boto3)

    assert list_keys("my-bucket", "bdm/") == []
    fake_boto3.client.assert_called_once_with("s3")
