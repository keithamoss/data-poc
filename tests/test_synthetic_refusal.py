"""The sentence a synthetic command or flag is refused with where synthetic
data cannot be made here (REQ-PIPE-385 criteria 6 and 7, the wording amended
by Keith 2026-11-18 after the CLI post-build critic): what the command is for,
what is missing, and what to do instead.

`cli/synthetic.py`'s refusal is the one sentence every refused path prints -
a hidden stand-in, `refuse()` and `refuse_flags()` - so it is driven here
directly, with the missing side faked; tests/test_real_deployment.py drives the
same refusals through `mothman` in a copy with the components blocked."""
from __future__ import annotations

import click
import pytest

from cli import synthetic


@pytest.fixture
def blocked(monkeypatch):
    monkeypatch.setattr(synthetic, "missing_components",
                        lambda: ["generator", "synthetic_data_generator", "scenarios", "bootstrap"])


def _said(call) -> str:
    with pytest.raises(click.ClickException) as raised:
        call()
    return raised.value.message


def test_a_command_is_for_synthetic_data_and_says_what_to_run_instead(blocked):
    said = _said(lambda: synthetic.refuse("mothman pipeline cache-key"))
    assert said.startswith("`mothman pipeline cache-key` is for synthetic data, and this "
                           "deployment does not have generator/, synthetic_data_generator/, "
                           "scenarios/ or bootstrap/ - it processes real supplies only."), said
    assert "generates synthetic data" not in said
    assert "To process what has arrived, run `mothman pipeline run` (first time) or " \
           "`mothman pipeline process`." in said


def test_a_flag_names_the_flags_that_check_a_file_instead(blocked):
    said = _said(lambda: synthetic.refuse_flags("mothman bdm qa", run_id="bdm_run_001",
                                                reference_run_id=None))
    assert said.startswith("`mothman bdm qa --run-id` is for synthetic data"), said
    assert "To check a file of your own, give --file or --s3-key instead." in said
    assert "pipeline run" not in said


def test_an_asset_without_a_synthetic_folder_is_named(monkeypatch):
    class _Asset:
        name = "registry"

    monkeypatch.setattr(synthetic, "missing_components", lambda: [])
    monkeypatch.setattr(synthetic, "asset_has_synthetic", lambda: False)
    monkeypatch.setattr(synthetic, "_asset", lambda: _Asset())
    said = _said(lambda: synthetic.refuse("mothman env reset-synthetic"))
    assert said.startswith("`mothman env reset-synthetic` is for synthetic data, and asset "
                           "registry has no synthetic/ folder (assets/registry/synthetic/) - "
                           "this deployment processes real supplies only."), said
    assert "`mothman pipeline process`" in said


def test_nothing_is_refused_where_synthetic_data_can_be_made(monkeypatch):
    monkeypatch.setattr(synthetic, "missing_components", lambda: [])
    monkeypatch.setattr(synthetic, "asset_has_synthetic", lambda: True)
    assert synthetic.refuse("mothman pipeline bootstrap") is None
    assert synthetic.refuse_flags("mothman bdm qa", run_id="bdm_run_001") is None


pytestmark = pytest.mark.asset("daily")
