"""REQ-PIPE-122 NFR 1, built 2026-10-05 (Keith): the amber setting in
force, and the level it came from, visible in the terminal."""
from __future__ import annotations

from click.testing import CliRunner

from cli import supply


def test_amber_setting_lists_every_dataset_in_words():
    result = CliRunner().invoke(supply.supply_group, ["amber-setting"])
    assert result.exit_code == 0, result.output
    flat = " ".join(result.output.split())
    assert "birth-registrations" in flat and "cp-clients" in flat
    assert "set for the whole data asset" in flat


def test_amber_setting_narrows_to_a_collection():
    result = CliRunner().invoke(supply.supply_group,
                                ["amber-setting", "--collection", "child-protection"])
    assert result.exit_code == 0, result.output
    assert "cp-clients" in result.output and "birth-registrations" not in result.output
