"""REQ-TEST-366 (the move map followed by every read of a base commit in the
push that carries the move) and REQ-QAC-344 criterion 7 (the asset rename
excused, and nothing else).

Each test builds a real temporary repository whose BASE commit has the old
layout - contract/ - and whose head has the new - assets/<asset>/ with the
move map - and runs the reader itself against that base (criterion 8): a
frozen item or a check's config changed in the move fails, and the same move
with no change passes. MOTHMAN_DIFF_BASE names the base, as CI's
github.event.before does.
"""
from __future__ import annotations

import os
import subprocess
import textwrap
from datetime import date
from pathlib import Path

import pytest
import yaml

from qa_tools.common import check_lifecycle as cl
from qa_tools.common import correction_trial, moved_paths, validate_schedule
from qa_tools.common import validate_check_lifecycle as vcl

REAL = Path(__file__).resolve().parent.parent

FORMER = "data-asset-1"

MAP = textwrap.dedent("""\
    former_data_asset_id: data-asset-1
    assets:
      q:
        agencies: [ag-q]
        collections: [cq]
        datasets: [dq]
        calendars: [cal-q]
      d:
        agencies: [ag-d]
        collections: [cd]
        datasets: [dd]
        calendars: [cal-d]
    moves:
      - from: contract/data-asset.yaml
        to: [assets/q/data-asset.yaml, assets/d/data-asset.yaml]
      - from: contract/people.yaml
        to: [assets/q/people.yaml, assets/d/people.yaml]
      - from: contract/ag-q/q-schema.yml
        to: assets/q/ag-q/q-schema.yml
      - from: shared/macros/m.sql
        to: dbt_shared/macros/m.sql
    """)


def _git(repo, *args, when=None) -> str:
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com"}
    if when:
        env["GIT_AUTHOR_DATE"] = env["GIT_COMMITTER_DATE"] = when
    return subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True,
                          text=True, env=env).stdout.strip()


def _write(repo: Path, files: dict[str, str]) -> None:
    for rel, text in files.items():
        path = repo / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)


def _asset(asset_id: str, agencies: list[tuple[str, str, str]], amber_past: str = "promote") -> str:
    hierarchy = "".join(
        f"    - id: {a}\n      collections:\n        - id: {c}\n          datasets:\n"
        f"            - id: {d}\n" for a, c, d in agencies)
    return (f"data_asset_id: {asset_id}\nsynthetic: true\namber_setting:\n  versions:\n"
            f"    - effective_from: '2023-01-01'\n      value: {amber_past}\n"
            f"      changelog:\n        - date: '2023-01-01'\n          author: t\n"
            f"          change: first\n"
            f"hierarchy:\n  agencies:\n{hierarchy}")


def _people(asset_id: str, agencies: list[str]) -> str:
    rows = "".join(f"  - agency: {a}\n    person: k@example.com\n    role: manager\n"
                   for a in agencies)
    return ("people:\n  - email: k@example.com\n    name: K\n    roles: [manager]\n"
            f"assignments:\n  - data_asset: {asset_id}\n    person: k@example.com\n"
            f"    role: manager\n{rows}")


def _schema(check_id: str, warn: str = ">90") -> str:
    return textwrap.dedent(f"""\
        models:
          - name: m
            columns:
              - name: c
                tests:
                  - not_null:
                      meta:
                        check_id: {check_id}
                        category: completeness
                        changelog: []
                      config:
                        warn_if: "{warn}"
        """)


BOTH = [("ag-q", "cq", "dq"), ("ag-d", "cd", "dd")]
CHECK = "ag-q.cq.dq.c.not_null_dbt"


@pytest.fixture
def moved(tmp_path, monkeypatch):
    """A repository whose base is the old layout; `move(...)` writes and
    commits the new one, overriding any new file given, and returns the
    repository."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _write(repo, {"contract/data-asset.yaml": _asset(FORMER, BOTH),
                  "contract/people.yaml": _people(FORMER, ["ag-q", "ag-d"]),
                  "contract/ag-q/q-schema.yml": _schema(f"{FORMER}.{CHECK}"),
                  "shared/macros/m.sql": "{% macro m() %}1{% endmacro %}\n"})
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "base", when="2026-09-01T09:00:00+08:00")
    base = _git(repo, "rev-parse", "HEAD")
    monkeypatch.setenv("MOTHMAN_DIFF_BASE", base)
    for module in (vcl, validate_schedule):
        monkeypatch.setattr(module, "ROOT", repo)
    validate_schedule._content_at.cache_clear()

    def move(with_map: bool = True, **override) -> Path:
        files = {"assets/q/data-asset.yaml": _asset("q", BOTH[:1]),
                 "assets/d/data-asset.yaml": _asset("d", BOTH[1:]),
                 "assets/q/people.yaml": _people("q", ["ag-q"]),
                 "assets/d/people.yaml": _people("d", ["ag-d"]),
                 "assets/q/ag-q/q-schema.yml": _schema(f"q.{CHECK}"),
                 "dbt_shared/macros/m.sql": "{% macro m() %}1{% endmacro %}\n"}
        files.update({k.replace("__", "/"): v for k, v in override.items()})
        if with_map:
            files["assets/moved-paths.yaml"] = MAP
        _git(repo, "rm", "-rq", "contract", "shared")
        _write(repo, files)
        _git(repo, "add", "-A")
        _git(repo, "commit", "-qm", "the move", when="2026-10-01T09:00:00+08:00")
        validate_schedule._content_at.cache_clear()
        return repo

    move.base = base
    move.repo = repo
    return move


# ---- the map itself (criteria 1 and 7) ----------------------------------

class TestTheMapAppliesOnlyToThePushCarryingTheMove:
    def test_it_applies_where_the_base_holds_no_assets_folder(self, moved):
        repo = moved()
        assert moved_paths.applies(repo) is not None

    def test_it_does_not_apply_once_the_base_holds_assets(self, moved, monkeypatch):
        repo = moved()
        monkeypatch.setenv("MOTHMAN_DIFF_BASE", _git(repo, "rev-parse", "HEAD"))
        assert moved_paths.applies(repo) is None
        assert vcl._old_file_content("assets/q/ag-q/q-schema.yml", "HEAD") is not None
        assert moved_paths.old_path("assets/q/ag-q/q-schema.yml", repo) is None

    def test_without_a_map_nothing_is_followed(self, moved):
        repo = moved(with_map=False)
        assert moved_paths.applies(repo) is None
        assert vcl._old_file_content("assets/q/ag-q/q-schema.yml", moved.base) is None


# ---- the check-lifecycle gate (criterion 2's _sources reads) ------------

def _lifecycle_errors(repo: Path, monkeypatch) -> list[str]:
    monkeypatch.setattr(vcl, "_sources", lambda ref: (
        [("assets/q/ag-q/q-schema.yml", cl.parse_dbt_check_metadata)], []))
    monkeypatch.setattr(vcl, "_moved_ids", lambda: moved_paths.id_rename(repo, "q"))
    ref = os.environ["MOTHMAN_DIFF_BASE"]
    old, new = vcl.collect_checks(ref), vcl.collect_checks(None)
    moved_ids = vcl._moved_ids()
    return vcl._by_source_file(cl.validate(old, new, moved=moved_ids), old, new, ref, moved_ids)


class TestTheLifecycleGateFollowsTheMove:
    def test_the_moved_check_is_read_at_its_old_path(self, moved):
        moved()
        assert vcl._old_file_content("assets/q/ag-q/q-schema.yml", moved.base) == \
            _schema(f"{FORMER}.{CHECK}")

    def test_a_move_that_changes_nothing_passes(self, moved, monkeypatch):
        repo = moved()
        assert _lifecycle_errors(repo, monkeypatch) == []

    def test_a_check_config_changed_in_the_move_fails(self, moved, monkeypatch):
        repo = moved(**{"assets__q__ag-q__q-schema.yml": _schema(f"q.{CHECK}", warn=">50")})
        errors = _lifecycle_errors(repo, monkeypatch)
        assert errors == [f"Check config changed without a new changelog entry: 'q.{CHECK}'"]

    def test_a_folder_the_move_created_is_listed_at_the_base(self, moved):
        moved()
        assert vcl._files_in("dbt_shared/macros", moved.base) == ["dbt_shared/macros/m.sql"]
        assert vcl._old_file_content("dbt_shared/macros/m.sql", moved.base) == \
            "{% macro m() %}1{% endmacro %}\n"


# ---- REQ-QAC-344 criterion 7: the rename and nothing else ----------------

def _check(check_id: str, config_hash: str = "h") -> cl.CheckMetadata:
    return cl.CheckMetadata(check_id=check_id, category="completeness", tool="dbt",
                            config_hash=config_hash, source_file="x.yml", changelog=[])


class TestTheRenameIsExcusedAndNothingElse:
    MOVED = (FORMER, "q")

    def test_the_moves_renamed_id_passes(self):
        assert cl.validate([_check(f"{FORMER}.{CHECK}")], [_check(f"q.{CHECK}")],
                           moved=self.MOVED) == []

    def test_without_the_map_the_rename_fails_as_disappeared(self):
        errors = cl.validate([_check(f"{FORMER}.{CHECK}")], [_check(f"q.{CHECK}")])
        assert any("disappeared" in e for e in errors)

    def test_an_id_renamed_any_other_way_still_fails(self):
        errors = cl.validate([_check(f"{FORMER}.{CHECK}")],
                             [_check("q.ag-q.cq.dq.c.unique_dbt")], moved=self.MOVED)
        assert any("disappeared" in e and FORMER in e for e in errors)
        errors = cl.validate([_check(f"{FORMER}.{CHECK}")], [_check(f"d.{CHECK}")],
                             moved=self.MOVED)
        assert any("disappeared" in e for e in errors)

    def test_a_renamed_id_whose_config_hash_also_changed_fails(self):
        errors = cl.validate([_check(f"{FORMER}.{CHECK}", "h1")],
                             [_check(f"q.{CHECK}", "h2")], moved=self.MOVED)
        assert errors == [f"Check config changed without a new changelog entry: 'q.{CHECK}'"]


# ---- the setting freeze in validate_schedule (lines 993-996 then) --------

def _amber_errors(repo: Path) -> list:
    path = repo / "assets/q/data-asset.yaml"
    src = validate_schedule.Source(path, path.parent)
    raw = yaml.safe_load(path.read_text())
    return validate_schedule._amber_setting_errors(raw, src, date(2026, 11, 1),
                                                   os.environ["MOTHMAN_DIFF_BASE"])


class TestTheSettingFreezeFollowsTheMove:
    def test_a_divided_file_is_read_as_this_assets_part(self, moved):
        moved()
        doc = yaml.safe_load(validate_schedule._content_at("assets/q/data-asset.yaml", moved.base))
        assert doc == yaml.safe_load(_asset("q", BOTH[:1]))

    def test_a_move_that_changes_nothing_passes(self, moved):
        assert _amber_errors(moved()) == []

    def test_a_past_version_changed_in_the_move_fails(self, moved):
        repo = moved(**{"assets__q__data-asset.yaml": _asset("q", BOTH[:1], amber_past="hold")})
        errors = _amber_errors(repo)
        assert errors and "2023-01-01" in str(errors[0])


# ---- the people file read at the base (PEOPLE_REL then) ------------------

class TestThePeopleFileAtTheBaseFollowsTheMove:
    def test_it_is_read_as_this_assets_part(self, moved):
        moved()
        doc = yaml.safe_load(validate_schedule._content_at("assets/q/people.yaml", moved.base))
        assert doc == yaml.safe_load(_people("q", ["ag-q"]))

    def test_an_approver_removed_in_the_move_is_seen(self, moved):
        moved(**{"assets__q__people.yaml": _people("q", [])})
        base = yaml.safe_load(validate_schedule._content_at("assets/q/people.yaml", moved.base))
        now = yaml.safe_load((moved.repo / "assets/q/people.yaml").read_text())
        assert base != now


# ---- _version_added_on walks base..HEAD through the move (criterion 6) ---

class TestTheAddedOnWalkFollowsTheMove:
    def test_a_version_added_before_the_move_is_dated_by_its_own_commit(self, moved):
        repo = moved.repo
        second = {"effective_from": "2026-09-20", "value": "hold",
                  "changelog": [{"date": "2026-09-20", "author": "t", "change": "second"}]}
        old = yaml.safe_load(_asset(FORMER, BOTH))
        old["amber_setting"]["versions"].append(second)
        _write(repo, {"contract/data-asset.yaml": yaml.safe_dump(old, sort_keys=False)})
        _git(repo, "commit", "-qam", "the version", when="2026-09-20T09:00:00+08:00")
        q = yaml.safe_load(_asset("q", BOTH[:1]))
        q["amber_setting"]["versions"].append(second)
        moved(**{"assets__q__data-asset.yaml": yaml.safe_dump(q, sort_keys=False)})
        assert validate_schedule._version_added_on(
            "assets/q/data-asset.yaml", moved.base, "2026-09-20") == date(2026, 9, 20)


# ---- correction_trial's base reads (lines 623 and 651-653 then) ----------

class TestCorrectionTrialReadsTheBaseThroughTheMove:
    def test_the_real_agreement_divides_into_readable_parts(self, tmp_path, monkeypatch):
        """The real contract/ calendar and data-asset files at a base, read for
        each asset of a map dividing them as the split does: each part is a
        readable agreement and holds its own asset's collections only."""
        repo = tmp_path / "real"
        repo.mkdir()
        _git(repo, "init", "-q")
        src = REAL / "contract" if (REAL / "contract").is_dir() else None
        if src is None:
            pytest.skip("the tree is already moved; the base read is covered above")
        _write(repo, {"contract/calendar.yaml": (src / "calendar.yaml").read_text(),
                      "contract/data-asset.yaml": (src / "data-asset.yaml").read_text()})
        _git(repo, "add", "-A")
        _git(repo, "commit", "-qm", "base")
        monkeypatch.setenv("MOTHMAN_DIFF_BASE", _git(repo, "rev-parse", "HEAD"))
        monkeypatch.setattr(validate_schedule, "ROOT", repo)
        validate_schedule._content_at.cache_clear()
        _write(repo, {"assets/moved-paths.yaml": textwrap.dedent("""\
            former_data_asset_id: data-asset-1
            assets:
              daily:
                agencies: [registry-services]
                collections: [civil-registration]
                datasets: [birth-registrations]
                calendars: [daily]
                change_references: [REQ-GEN-205-WINDOW]
              quarterly:
                agencies: [child-protection-family-support, department-of-health]
                collections: [child-protection, emergency-department, linkage-products]
                datasets: [cp-clients, cp-notifications, cp-investigations, cp-placements,
                           cp-carers, cp-case-workers, ed-presentations, linkage-keys,
                           geo-cp-clients, geo-ed-presentations]
                calendars: [quarterly]
                change_references: [REQ-GEN-205, REQ-PIPE-181, REQ-GEN-218]
            moves:
              - from: contract/calendar.yaml
                to: [assets/quarterly/calendar.yaml, assets/daily/calendar.yaml]
              - from: contract/data-asset.yaml
                to: [assets/quarterly/data-asset.yaml, assets/daily/data-asset.yaml]
            """)})
        for asset, colls in (("daily", {"civil-registration"}),
                             ("quarterly", {"child-protection", "emergency-department",
                                            "linkage-products"})):
            from qa_tools.common import agreement_freeze

            monkeypatch.setattr(agreement_freeze, "calendar_rel",
                                lambda a=asset: f"assets/{a}/calendar.yaml")
            monkeypatch.setattr(agreement_freeze, "asset_rel",
                                lambda a=asset: f"assets/{a}/data-asset.yaml")
            cal, doc = correction_trial.at_ref(os.environ["MOTHMAN_DIFF_BASE"])
            assert {c["id"] for c in cal["collections"]} == colls
            assert {c["id"] for a in doc["hierarchy"]["agencies"]
                    for c in a["collections"]} == colls
            assert doc["data_asset_id"] == asset
            assert {d["id"] for d in cal["datasets"]} == {
                d["id"] for a in doc["hierarchy"]["agencies"] for c in a["collections"]
                for d in c["datasets"]}

    def test_without_the_map_the_base_cannot_be_read(self, moved, monkeypatch):
        moved(with_map=False)
        from qa_tools.common import agreement_freeze

        monkeypatch.setattr(agreement_freeze, "calendar_rel", lambda: "assets/q/calendar.yaml")
        with pytest.raises(correction_trial.Unreadable):
            correction_trial.at_ref(moved.base)


#: The data asset this module's tests act for, unless a test says otherwise
#: (C11, Keith 2026-11-02: every test module names its asset).
pytestmark = pytest.mark.asset("quarterly")
