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

    def test_the_run_path_never_calls_safe_load(self, monkeypatch, tmp_path):
        import shutil
        from datetime import date

        from qa_tools.common import (agreement, asset_time, environments, hierarchy,
                                     postgres_version, slots)

        # FRESH COPIES, so nothing built earlier in this process can answer
        # (REQ-PIPE-254 keys every built value on its file's path and text).
        for name, module, attr in (("data-asset.yaml", hierarchy, "DATA_ASSET_YAML"),
                                   ("data-asset.yaml", asset_time, "DATA_ASSET_YAML"),
                                   ("calendar.yaml", agreement, "CALENDAR_YAML")):
            copy = tmp_path / name
            shutil.copyfile(getattr(module, attr), copy)
            monkeypatch.setattr(module, attr, copy)

        def refuse(*a, **k):
            raise AssertionError("yaml.safe_load was called on the run path")
        monkeypatch.setattr(yaml, "safe_load", refuse)
        assert slots.slots_for_dataset("cp-clients", until=date(2024, 1, 1))
        assert slots.claimable_until("cp-clients", date(2024, 1, 1))
        assert environments.for_connection()
        postgres_version.declared_major()
        assert asset_time.timezone_versions()
        assert agreement.current().datasets and hierarchy.all_datasets()

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


class TestReadIsReadText:
    """config_yaml.read answers as Path.read_text(encoding='utf-8') would -
    the same text and the same errors - by the operating system's own read
    (REQ-PIPE-254 criterion 19). post-build-review #282 (L5 critic, 4): it
    lost the path from a directory's error and kept a file's CRLFs, which
    read_text translates."""

    @pytest.mark.parametrize("raw", [b"a: 1\r\nb: 2\r\n", b"a: 1\rb: 2\r", b"a: 1\r\nb: 2\nc: 3\r",
                                     b"plain: text\n", b""],
                             ids=["crlf", "lone-cr", "mixed", "lf", "empty"])
    def test_the_same_text(self, tmp_path, raw):
        f = tmp_path / "c.yaml"
        f.write_bytes(raw)
        assert config_yaml.read(f) == f.read_text(encoding="utf-8")

    @pytest.mark.parametrize("make", ["directory", "missing", "undecodable"])
    def test_the_same_error(self, tmp_path, make):
        f = tmp_path / "c.yaml"
        if make == "directory":
            f.mkdir()
        elif make == "undecodable":
            f.write_bytes(b"a: \xff\n")
        with pytest.raises(Exception) as theirs:
            f.read_text(encoding="utf-8")
        with pytest.raises(Exception) as ours:
            config_yaml.read(f)
        assert type(ours.value) is type(theirs.value)
        assert str(ours.value) == str(theirs.value)
