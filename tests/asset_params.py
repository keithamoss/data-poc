"""Parametrising a test over values of both assets (the asset split, C11).

A parametrised test whose values belong to different assets - one collection
id per asset, one contract path per asset - runs each value under its own
asset. `per_asset(values)` marks each value with the asset its own ids name,
read from each asset's data-asset.yaml (tests/asset_inference.py), so a value
is never hand-assigned to an asset; a value naming neither asset, or both,
runs under the test's own mark.
"""
from __future__ import annotations

import pytest

import asset_inference


def per_asset(values, ids=None):
    """`values` as pytest params, each carrying the asset its ids name."""
    out = []
    for i, value in enumerate(values):
        named = asset_inference.named(repr(value))
        marks = [pytest.mark.asset(named.pop())] if len(named) == 1 else []
        out.append(pytest.param(value, marks=marks,
                                id=None if ids is None else ids[i]))
    return out
