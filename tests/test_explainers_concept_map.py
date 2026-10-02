"""The explainers' concept map: groups in reading order, pages and their
sections, and every concept in exactly one place (REQ-DOCS-120)."""
from __future__ import annotations

import copy
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

from qa_tools.common import explainers as ex
from qa_tools.common import validate_explainers as v

GOOD = {
    "group_page_parts": list(ex.GROUP_PAGE_PARTS),
    "groups": [
        {"number": 0, "slug": "0-overview", "title": "The overview", "read_first": [], "pages": []},
        {"number": 1, "slug": "1-shape", "title": "The shape of the asset", "read_first": [0], "pages": [
            {"slug": "the-data-contract", "title": "The data contract", "sections": []}]},
        {"number": 2, "slug": "2-calendar", "title": "The calendar", "read_first": [0, 1], "pages": [
            {"slug": "periods-and-slots", "title": "Periods and slots", "sections": []},
            {"slug": "the-supply-calendar", "title": "The supply calendar",
             "sections": ["runway", "a schedule that runs out"]}]},
    ],
    "glossary_only": ["cadence rule"],
    "excluded": [{"concept": "freshness capping", "went": "parked", "why": "No requirement yet."}],
}


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    (tmp_path / ".claude/skills/docs-house-style").mkdir(parents=True)
    shutil.copy(v.REPO_ROOT / v.HOUSE_STANDARD, tmp_path / v.HOUSE_STANDARD)
    (tmp_path / "requirements.yaml").write_text(yaml.safe_dump({"requirements": []}))
    (tmp_path / "docs/explainers").mkdir(parents=True)
    write(tmp_path, GOOD)
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    return tmp_path


def write(repo: Path, cmap: dict) -> None:
    (repo / "docs/explainers/concept-map.yaml").write_text(yaml.safe_dump(cmap, sort_keys=False))


def changed(**edits) -> dict:
    cmap = copy.deepcopy(GOOD)
    for path, value in edits.items():
        target = cmap
        keys = path.split("__")
        for k in keys[:-1]:
            target = target[int(k)] if k.isdigit() else target[k]
        last = keys[-1]
        target[int(last) if last.isdigit() else last] = value
    return cmap


def messages(repo: Path) -> list[str]:
    return [f.message for f in v.Validator(repo).run() if f.rule.startswith("concept-map")]


def test_a_good_map_passes(repo):
    assert messages(repo) == []


def test_the_real_map_passes():
    """The committed map is held to the same rules."""
    if not (v.REPO_ROOT / ex.CONCEPT_MAP).exists():
        pytest.skip("no concept map committed yet")
    assert ex.concept_map_problems(ex.load_concept_map()) == []


def test_an_unknown_key_is_rejected(repo):
    cmap = changed()
    cmap["groups"][1]["colour"] = "blue"
    write(repo, cmap)
    assert any(f.rule == "concept-map-schema" for f in v.Validator(repo).run())


def test_a_missing_key_is_rejected(repo):
    cmap = changed()
    del cmap["groups"][2]["pages"][0]["sections"]
    write(repo, cmap)
    assert any(f.rule == "concept-map-schema" for f in v.Validator(repo).run())


def test_a_repeated_group_number_is_rejected(repo):
    write(repo, changed(groups__2__number=1))
    assert any("group 1 is listed more than once" in m for m in messages(repo))


def test_groups_out_of_reading_order_are_rejected(repo):
    cmap = changed()
    cmap["groups"][1], cmap["groups"][2] = cmap["groups"][2], cmap["groups"][1]
    write(repo, cmap)
    assert any("numbered reading order" in m for m in messages(repo))


def test_a_repeated_page_is_rejected(repo):
    cmap = changed()
    cmap["groups"][2]["pages"].append({"slug": "the-data-contract", "title": "Contracts again", "sections": []})
    write(repo, cmap)
    assert any("'the-data-contract' is listed in group 1 and group 2" in m for m in messages(repo))


@pytest.mark.parametrize("where", ["section", "glossary_only", "excluded", "title"])
def test_one_concept_in_two_places_is_rejected(repo, where):
    cmap = changed()
    if where == "section":
        cmap["groups"][1]["pages"][0]["sections"].append("Runway")
    elif where == "glossary_only":
        cmap["glossary_only"].append("runway")
    elif where == "excluded":
        cmap["excluded"].append({"concept": "runway", "went": "parked", "why": "x"})
    else:
        cmap["groups"][1]["pages"].append({"slug": "runway", "title": "Runway", "sections": []})
    write(repo, cmap)
    assert any("'" in m and "is in two places" in m for m in messages(repo))


def test_read_first_must_point_backwards_at_a_real_group(repo):
    write(repo, changed(groups__1__read_first=[2]))
    assert any("comes after it" in m for m in messages(repo))
    write(repo, changed(groups__1__read_first=[7]))
    assert any("does not exist" in m for m in messages(repo))


def test_an_exclusion_says_where_it_went(repo):
    write(repo, changed(excluded=[{"concept": "freshness capping", "went": "the bin", "why": "x"}]))
    assert any("say one of pipeline-docs, parked, not-explained" in m for m in messages(repo))


def test_the_four_group_page_parts_are_recorded(repo):
    write(repo, changed(group_page_parts=["story", "concept_cards"]))
    assert any("group_page_parts must be exactly" in m for m in messages(repo))
