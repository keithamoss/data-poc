"""Tests for qa_tools/common/datacontract_common.py's
fail_threshold_from_quality_definition() - item 74's Bug B fix
(plans/qa-pipeline.md). Before this fix, every severity:error rule got a
blanket fail_threshold of 0, discarding any real non-zero ODCS threshold
(mustBeLessThan/mustBeLessOrEqualTo) a rule actually configured - a real
bug found via place_of_birth_facility's own mustBeLessThan: 35 rule
reading red on almost every run despite genuinely passing."""
from __future__ import annotations

import yaml

from qa_tools.common.datacontract_common import fail_threshold_from_quality_definition


def _quality_definition(**fields) -> str:
    return yaml.dump(fields)


def test_severity_warning_is_always_none_regardless_of_threshold():
    qd = _quality_definition(mustBeLessThan=35)
    assert fail_threshold_from_quality_definition(qd, "warning") is None


def test_severity_info_is_always_none():
    qd = _quality_definition(mustBe=0)
    assert fail_threshold_from_quality_definition(qd, "info") is None


def test_must_be_zero_preserves_zero_tolerance():
    qd = _quality_definition(mustBe=0)
    assert fail_threshold_from_quality_definition(qd, "error") == 0


def test_must_be_less_than_preserves_the_real_configured_value():
    """The real bug: place_of_birth_facility's real rule (mustBeLessThan:
    35, severity: error) used to collapse to fail_threshold=0 - throwing
    away the real 35% tolerance and making a genuinely passing ~2% null
    rate read as failing on almost every run."""
    qd = _quality_definition(mustBeLessThan=35)
    assert fail_threshold_from_quality_definition(qd, "error") == 35


def test_must_be_less_or_equal_to_preserves_the_real_configured_value():
    qd = _quality_definition(mustBeLessOrEqualTo=10)
    assert fail_threshold_from_quality_definition(qd, "error") == 10


def test_missing_quality_definition_falls_back_to_the_old_zero_default():
    assert fail_threshold_from_quality_definition(None, "error") == 0


def test_unrecognised_threshold_shape_falls_back_to_the_old_zero_default():
    """mustBeGreaterThan/mustBeGreaterOrEqualTo/mustBeBetween are real
    ODCS shapes but never actually used with severity: error in either
    real contract today (verified 2026-09-18) - this project's own
    convention is to always flip the query to a "0/low = healthy"
    mustBe: 0 shape instead (see bdm-birth-registrations-contract.yaml's
    freshness-check comment). Falls back rather than raising, so an
    unexpected future shape doesn't crash a real pipeline run."""
    qd = _quality_definition(mustBeGreaterThan=5)
    assert fail_threshold_from_quality_definition(qd, "error") == 0
