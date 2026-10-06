"""Configuration is parsed once per process while its content is unchanged
(REQ-PIPE-156, signed by Keith 2026-10-06)."""
from __future__ import annotations

import os
import threading

import pytest
import yaml

from qa_tools.common import config_yaml


@pytest.fixture(autouse=True)
def _fresh_cache():
    config_yaml.clear()
    yield
    config_yaml.clear()


def _counting(monkeypatch):
    calls = []
    real = config_yaml._parse_raw

    def counted(text):
        calls.append(text)
        return real(text)
    monkeypatch.setattr(config_yaml, "_parse_raw", counted)
    return calls


class TestParsedOnce:

    def test_the_same_bytes_are_parsed_once(self, tmp_path, monkeypatch):
        calls = _counting(monkeypatch)
        f = tmp_path / "a.yaml"
        f.write_text("a: 1\nb: [1, 2]\n")
        assert config_yaml.load(f) == config_yaml.load(f) == {"a": 1, "b": [1, 2]}
        assert len(calls) == 1

    def test_changed_bytes_are_parsed_again_even_with_the_same_size_and_time(self, tmp_path,
                                                                              monkeypatch):
        """Criterion 3: keyed on content, not modification time and size - a
        test changing '14d' to '21d' inside one clock tick keeps both."""
        calls = _counting(monkeypatch)
        f = tmp_path / "a.yaml"
        f.write_text("window: 14d\n")
        stat = f.stat()
        assert config_yaml.load(f) == {"window": "14d"}
        f.write_text("window: 21d\n")
        os.utime(f, ns=(stat.st_atime_ns, stat.st_mtime_ns))
        assert f.stat().st_size == stat.st_size
        assert config_yaml.load(f) == {"window": "21d"}
        assert len(calls) == 2

    def test_a_stream_and_text_go_through_the_same_cache(self, tmp_path, monkeypatch):
        calls = _counting(monkeypatch)
        f = tmp_path / "a.yaml"
        f.write_text("x: 1\n")
        with open(f) as stream:
            assert config_yaml.parse(stream) == {"x": 1}
        assert config_yaml.parse("x: 1\n") == {"x": 1}
        assert len(calls) == 1

    def test_empty_and_absent_content_parse_as_yaml_does(self):
        assert config_yaml.parse("") is None
        assert config_yaml.parse(None) is None


class TestEachCallerGetsItsOwnCopy:

    def test_mutating_one_result_does_not_change_the_next(self, tmp_path):
        f = tmp_path / "a.yaml"
        f.write_text("items: [1, 2]\nnested: {k: v}\n")
        first = config_yaml.load(f)
        first["items"].append(3)
        first["nested"]["k"] = "changed"
        assert config_yaml.load(f) == {"items": [1, 2], "nested": {"k": "v"}}


class TestThreads:

    def test_many_threads_asking_at_once_each_get_a_correct_document(self, tmp_path):
        f = tmp_path / "a.yaml"
        f.write_text("\n".join(f"k{i}: {i}" for i in range(500)) + "\n")
        want = {f"k{i}": i for i in range(500)}
        got, errors = [], []

        def read():
            try:
                got.append(config_yaml.load(f))
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)
        threads = [threading.Thread(target=read) for _ in range(16)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert not errors and len(got) == 16 and all(g == want for g in got)


class TestItIsWhatTheRunPathReads:
    """Criterion 1, asserted by behaviour rather than by reading the source:
    with PyYAML's own safe_load made to fail, everything on the run path that
    reads configuration still works, because none of it calls safe_load."""

    def test_the_run_path_never_calls_safe_load(self, monkeypatch):
        from datetime import date

        from qa_tools.common import (asset_time, environments, hierarchy, postgres_version,
                                     schedule, slots)

        def refuse(*a, **k):
            raise AssertionError("yaml.safe_load was called on the run path")
        monkeypatch.setattr(yaml, "safe_load", refuse)
        for cached in (hierarchy._load, schedule._load, schedule._dataset_schedules,
                       asset_time.asset_timezone):
            cached.cache_clear()
        try:
            assert slots.slots_for_dataset("cp-clients", until=date(2024, 1, 1))
            assert slots.claimable_until("cp-clients", date(2024, 1, 1))
            assert environments.for_connection()
            postgres_version.declared_major()
            assert asset_time.asset_timezone()
        finally:
            for cached in (hierarchy._load, schedule._load, schedule._dataset_schedules,
                           asset_time.asset_timezone):
                cached.cache_clear()

    def test_it_uses_the_c_loader_where_it_exists(self):
        assert config_yaml.LOADER is getattr(yaml, "CSafeLoader", yaml.SafeLoader)


class TestASlipNamesItsFile:

    def test_the_error_names_the_file_it_came_from(self, tmp_path):
        f = tmp_path / "data-asset.yaml"
        f.write_text("a: 1\nb: [unclosed\n")
        with pytest.raises(yaml.MarkedYAMLError) as by_path:
            config_yaml.load(f)
        assert str(f) in str(by_path.value)
        with open(f) as stream, pytest.raises(yaml.MarkedYAMLError) as by_stream:
            config_yaml.parse(stream)
        assert str(f) in str(by_stream.value)
