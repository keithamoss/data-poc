"""REQ-TEST-374: `mothman check` warns on every unanswered `PROVISIONAL`
choice in a built requirement, against a committed shrink-only baseline.

Keith, 2026-11-01 (post-build-review #292): a provisional choice is a
question waiting on a person, so the gate WARNS rather than fails - and
tightened after its critic, an item counts as answered only where it says
'SETTLED by Keith' or 'answered by Keith' followed by a date. These drive
the real gate (`validate_provisional.main`, and the real `mothman` command)
over small registers written to a temporary directory, plus the real
register and baseline once each."""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner

from qa_tools.common import validate_provisional as vp

ROOT = Path(__file__).resolve().parent.parent
WARN = 78


# ---------------------------------------------------------------- the rule


#: REQ-TEST-375: in the hand-picked set every push runs in CI.
pytestmark = pytest.mark.critical


@pytest.mark.parametrize("text", [
    "PROVISIONAL: amber rather than red.",
    "BUILT overnight, PROVISIONAL, not yet answered.",
    "PROVISIONAL - to be answered by Keith.",
    "PROVISIONAL - to be answered by Keith 2026-11-05.",
    "PROVISIONAL, WORDING SIGNED by Keith 2026-10-31.",
    "PROVISIONAL, answered.",
    "PROVISIONAL, SETTLED.",
    "PROVISIONAL, SETTLED by Keith.",
    "PROVISIONAL. CURRENT: <<<answered by Keith 2026-10-01>>>",
    "Quotes `PROVISIONAL` and then really is PROVISIONAL.",
    "PROVISIONAL - not answered by Keith 2026-10-01.",
    "PROVISIONAL - never answered by Keith 2026-10-01.",
    "PROVISIONAL - un-answered by Keith 2026-10-01.",
    "PROVISIONAL - has not been answered by Keith 2026-10-01.",
    "PROVISIONAL - not SETTLED by Keith 2026-10-01.",
])
def test_an_unanswered_marker_is_counted(text):
    assert vp.is_unanswered_marker(text)


@pytest.mark.parametrize("text", [
    "SETTLED by Keith 2026-10-06, was PROVISIONAL (overnight).",
    "PROVISIONAL (open question 1 answered by Keith 2026-10-23).",
    "PROVISIONAL; Answered by Keith, 2026-10-23.",
    "PROVISIONAL, settled by Keith on 2026-10-07 (REQ-PIPE-110 d5's lower case).",
    "Not this one. PROVISIONAL, SETTLED by Keith 2026-10-06.",
    "A builder's `PROVISIONAL` choice goes on the report.",
    "The word 'PROVISIONAL' is a mention here.",
    "CURRENT: <<<a PROVISIONAL choice>>> PROPOSED: <<<a settled one>>>",
    "a provisional choice, in lower case, is prose and not a marker.",
    "No marker here at all.",
])
def test_a_quoted_answered_or_absent_marker_is_not(text):
    assert not vp.is_unanswered_marker(text)


# ---------------------------------------------------------------- scanning


def _req(rid, status="built", decisions=(), criteria=(), nfrs=()):
    return {"id": rid, "status": status, "decisions": list(decisions),
            "acceptance_criteria": list(criteria),
            "non_functional_requirements": list(nfrs)}


def test_only_built_requirements_are_scanned_naming_field_and_item():
    register = {"requirements": [
        _req("REQ-A-001", decisions=["fine", "PROVISIONAL: x"],
             criteria=["THE SYSTEM SHALL y (PROVISIONAL)"], nfrs=["PROVISIONAL z"]),
        _req("REQ-A-002", status="not_started", decisions=["PROVISIONAL: draft"]),
    ]}
    found = [(m.req_id, m.field, m.item) for m in vp.scan(register)]
    assert found == [("REQ-A-001", "acceptance_criteria", 1),
                     ("REQ-A-001", "non_functional_requirements", 1),
                     ("REQ-A-001", "decisions", 2)]


def test_the_fingerprint_follows_the_text_not_the_position():
    a = vp.scan({"requirements": [_req("R", decisions=["PROVISIONAL: x"])]})[0]
    b = vp.scan({"requirements": [_req("R", decisions=["new", "PROVISIONAL: x"])]})[0]
    c = vp.scan({"requirements": [_req("R", decisions=["PROVISIONAL: x, reworded"])]})[0]
    assert a.fingerprint == b.fingerprint != c.fingerprint


# ---------------------------------------------------------------- the gate


@pytest.fixture
def repo(tmp_path, monkeypatch):
    """A scratch git repository holding a register and (optionally) a
    baseline - never the real tree."""
    monkeypatch.delenv(vp.WARNING_EXIT_VAR, raising=False)
    monkeypatch.delenv("MOTHMAN_DIFF_BASE", raising=False)
    monkeypatch.delenv("PRE_COMMIT", raising=False)
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    for k, v in (("user.email", "t@example.com"), ("user.name", "t")):
        subprocess.run(["git", "-C", str(tmp_path), "config", k, v], check=True)
    return tmp_path


def _write_register(root: Path, *reqs):
    (root / "requirements.yaml").write_text(yaml.safe_dump({"requirements": list(reqs)}))


def _commit(root: Path, message="c"):
    subprocess.run(["git", "-C", str(root), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(root), "commit", "-q", "-m", message], check=True)
    return subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"], check=True,
                          capture_output=True, text=True).stdout.strip()


def test_a_new_marker_warns_naming_it_and_never_fails(repo, monkeypatch, capsys):
    _write_register(repo, _req("REQ-A-001", decisions=["ok", "PROVISIONAL: x"]))
    vp.write_baseline(repo, [])
    assert vp.main([], root=repo) == 0  # CI: no warning channel asked for
    out = capsys.readouterr().out
    assert "REQ-A-001 decisions item 2" in out
    monkeypatch.setenv(vp.WARNING_EXIT_VAR, str(WARN))
    assert vp.main([], root=repo) == WARN


def test_a_baselined_marker_is_not_listed(repo, monkeypatch, capsys):
    monkeypatch.setenv(vp.WARNING_EXIT_VAR, str(WARN))
    _write_register(repo, _req("REQ-A-001", decisions=["PROVISIONAL: x"]))
    vp.write_baseline(repo, vp.scan(vp.load_register(repo)))
    assert vp.main([], root=repo) == 0
    assert "REQ-A-001" not in capsys.readouterr().out


def test_a_quoted_or_answered_marker_is_not_listed(repo, monkeypatch, capsys):
    monkeypatch.setenv(vp.WARNING_EXIT_VAR, str(WARN))
    _write_register(repo, _req("REQ-A-001", decisions=[
        "the `PROVISIONAL` word", "SETTLED by Keith 2026-10-06, was PROVISIONAL"]))
    vp.write_baseline(repo, [])
    assert vp.main([], root=repo) == 0
    assert "REQ-A-001" not in capsys.readouterr().out


def test_an_answered_baseline_entry_fails_until_it_is_taken_off(repo, capsys):
    _write_register(repo, _req("REQ-A-001", decisions=["PROVISIONAL: x"]))
    vp.write_baseline(repo, vp.scan(vp.load_register(repo)))
    _write_register(repo, _req("REQ-A-001", decisions=[
        "PROVISIONAL: x - SETTLED by Keith 2026-11-02"]))
    assert vp.main([], root=repo) == 1
    assert "only shrinks" in capsys.readouterr().out
    assert vp.main(["--prune"], root=repo) == 0
    assert vp.load_baseline(repo) == set()
    assert vp.main([], root=repo) == 0


def test_a_changed_item_leaves_the_baseline_and_then_warns(repo, monkeypatch):
    monkeypatch.setenv(vp.WARNING_EXIT_VAR, str(WARN))
    _write_register(repo, _req("REQ-A-001", decisions=["PROVISIONAL: x"]))
    vp.write_baseline(repo, vp.scan(vp.load_register(repo)))
    _write_register(repo, _req("REQ-A-001", decisions=["PROVISIONAL: x, reworded"]))
    assert vp.main([], root=repo) == 1
    assert vp.main(["--prune"], root=repo) == 0
    assert vp.main([], root=repo) == WARN


def test_the_baseline_cannot_gain_an_entry(repo, monkeypatch, capsys):
    _write_register(repo, _req("REQ-A-001", decisions=["PROVISIONAL: x"]))
    vp.write_baseline(repo, [])
    base = _commit(repo)
    _write_register(repo, _req("REQ-A-001", decisions=["PROVISIONAL: x"]),
                    _req("REQ-A-002", decisions=["PROVISIONAL: y"]))
    (repo / vp.BASELINE).unlink()
    vp.write_baseline(repo, vp.scan(vp.load_register(repo)))
    monkeypatch.setenv("MOTHMAN_DIFF_BASE", base)
    assert vp.main([], root=repo) == 1
    out = capsys.readouterr().out
    assert "gained" in out and "REQ-A-001" in out and "REQ-A-002" in out


def test_shrinking_against_the_base_is_allowed(repo, monkeypatch):
    _write_register(repo, _req("REQ-A-001", decisions=["PROVISIONAL: x"]))
    vp.write_baseline(repo, vp.scan(vp.load_register(repo)))
    base = _commit(repo)
    _write_register(repo, _req("REQ-A-001", decisions=["answered by Keith 2026-11-02"]))
    assert vp.main(["--prune"], root=repo) == 0
    monkeypatch.setenv("MOTHMAN_DIFF_BASE", base)
    assert vp.main([], root=repo) == 0


def test_the_baseline_is_written_once(repo, capsys):
    _write_register(repo, _req("REQ-A-001", decisions=["PROVISIONAL: x"]))
    assert vp.main(["--write-baseline"], root=repo) == 0
    assert len(vp.load_baseline(repo)) == 1
    assert vp.main(["--write-baseline"], root=repo) == 1
    assert "already exists" in capsys.readouterr().out


def test_a_missing_baseline_fails_rather_than_warning_on_everything(repo, capsys):
    _write_register(repo, _req("REQ-A-001", decisions=["PROVISIONAL: x"]))
    assert vp.main([], root=repo) == 1
    assert vp.BASELINE in capsys.readouterr().out


# ---------------------------------------------------------------- the real tree


def test_the_real_baseline_holds_and_is_not_empty():
    baseline = vp.load_baseline(ROOT)
    assert baseline, "the committed baseline must not be empty"
    live = {m.key for m in vp.scan(vp.load_register(ROOT))}
    assert baseline <= live, "a stale baseline entry - run --prune"


def test_this_requirement_never_flags_itself():
    reg = vp.load_register(ROOT)
    assert [m for m in vp.scan(reg) if m.req_id == "REQ-TEST-374"] == []


def test_the_real_command_passes_or_warns(monkeypatch):
    from cli.app import cli
    monkeypatch.delenv(vp.WARNING_EXIT_VAR, raising=False)
    result = CliRunner().invoke(cli, ["dashboard", "validate-provisional"])
    assert result.exit_code == 0, result.output
    assert "provisional" in result.output.lower()


def test_ci_runs_it_without_the_warning_channel():
    """Reads configuration, not behaviour: there is no CI to run here, and
    the property is that a warning cannot turn the workflow step red."""
    wf = yaml.safe_load((ROOT / ".github/workflows/validate-config.yml").read_text())
    steps = [s for job in wf["jobs"].values() for s in job["steps"]]
    mine = [s for s in steps if "validate-provisional" in (s.get("run") or "")]
    assert len(mine) == 1
    assert vp.WARNING_EXIT_VAR not in yaml.safe_dump(wf)


def test_a_shallow_clone_says_the_gain_check_was_skipped(repo, tmp_path_factory,
                                                         monkeypatch, capsys):
    """CI's checkout cannot always reach the push's base. Then the gain
    check cannot run, and says so rather than passing in silence."""
    _write_register(repo, _req("REQ-A-001", decisions=["PROVISIONAL: x"]))
    vp.write_baseline(repo, [])
    base = _commit(repo)
    _write_register(repo, _req("REQ-A-001", decisions=["PROVISIONAL: x"]),
                    _req("REQ-A-002", decisions=["PROVISIONAL: y"]))
    (repo / vp.BASELINE).unlink()
    vp.write_baseline(repo, vp.scan(vp.load_register(repo)))  # a gain
    _commit(repo)
    shallow = tmp_path_factory.mktemp("shallow") / "clone"
    subprocess.run(["git", "clone", "-q", "--depth", "1", f"file://{repo}", str(shallow)],
                   check=True)
    subprocess.run(["git", "-C", str(shallow), "checkout", "-q", "--detach"], check=True)
    monkeypatch.setenv("MOTHMAN_DIFF_BASE", base)  # not in the clone
    assert vp._baseline_at_base(shallow) is None
    assert vp.main([], root=shallow) == 0
    out = capsys.readouterr().out
    assert "gain check skipped" in out and base in out


def test_the_real_command_warns_on_a_new_marker_and_exits_0(repo, monkeypatch):
    from cli.app import cli
    _write_register(repo, _req("REQ-A-001", decisions=["ok", "PROVISIONAL: x"]))
    vp.write_baseline(repo, [])
    monkeypatch.setattr(vp, "ROOT", repo)
    result = CliRunner().invoke(cli, ["dashboard", "validate-provisional"])
    assert result.exit_code == 0, result.output
    assert "warning: REQ-A-001 decisions item 2" in result.output
    monkeypatch.setenv(vp.WARNING_EXIT_VAR, str(WARN))
    assert CliRunner().invoke(cli, ["dashboard", "validate-provisional"]).exit_code == WARN


#: The data asset this module's tests act for, unless a test says otherwise
#: (C11, Keith 2026-11-02: every test module names its asset).
pytestmark = [*(pytestmark if isinstance(pytestmark, list) else [pytestmark]), pytest.mark.asset("quarterly")]
