"""Every terminal route that keeps a supply processes it through the
pipeline's own per-arrival lifecycle, and no other (REQ-PIPE-086)."""
from __future__ import annotations

import os

import click
import pytest
from click.testing import CliRunner

from cli import bdm, common, cp
from qa_tools.common import hand_filing

_runner = CliRunner()


def _csv(folder, name, header="id,name"):
    path = os.path.join(folder, name)
    with open(path, "w") as f:
        f.write(header + "\n1,a\n")
    return path


def _flat(output: str) -> str:
    import re

    return re.sub(r"[\s│╭╮╰╯─]+", " ", output)


class TestAReferenceIsATrialsOnly:
    """Criterion 14: keep or trial is decided first, a reference is asked for
    and required only for a trial, and one given for a kept supply is refused
    saying why."""

    @pytest.mark.parametrize("args, flag", [
        (["--file", "{f}", "--reference-file", "{f}", "--commit"], "--reference-file"),
    ])
    def test_bdm_refuses_a_reference_for_a_kept_file(self, tmp_path, args, flag):
        f = _csv(tmp_path, "birth_registrations_2026-01-01.csv")
        out = _runner.invoke(bdm.qa_command, [a.format(f=f) for a in args])
        assert out.exit_code != 0
        assert "last promoted supply" in _flat(out.output) and flag in _flat(out.output)

    def test_cp_refuses_a_reference_for_a_kept_folder(self, tmp_path):
        folder = tmp_path / "d"
        folder.mkdir()
        _csv(folder, "cp_clients.csv")
        out = _runner.invoke(cp.qa_command, ["--folder", str(folder), "--reference-folder",
                                             str(folder), "--commit"])
        assert out.exit_code != 0 and "last promoted supply" in _flat(out.output)

    def test_a_trial_without_a_reference_is_refused_naming_the_flag(self, tmp_path):
        f = _csv(tmp_path, "birth_registrations_2026-01-01.csv")
        out = _runner.invoke(bdm.qa_command, ["--file", f, "--trial"])
        assert out.exit_code != 0 and "--reference-file" in _flat(out.output)

    def test_an_s3_kept_supply_refuses_its_reference_before_downloading(self, monkeypatch):
        monkeypatch.setenv(common.S3_BUCKET_ENV_VAR, "b")
        out = _runner.invoke(cp.qa_command, ["--s3-delivery", "cp/d/", "--s3-reference-delivery",
                                             "cp/r/", "--commit"])
        assert out.exit_code != 0 and "--s3-reference-delivery" in _flat(out.output)

    def test_the_tui_asks_keep_before_any_reference(self, monkeypatch, tmp_path):
        folder = tmp_path / "d"
        folder.mkdir()
        _csv(folder, "cp_clients.csv")
        asked = []
        answers = iter([str(folder)])
        monkeypatch.setattr(common, "path_prompt",
                            lambda m, flag_hint: asked.append(m) or next(answers))
        monkeypatch.setattr(common, "decide_keep", lambda paths, keep: asked.append("keep?")
                            or True)
        monkeypatch.setattr(cp, "run_check_local_folder",
                            lambda folder, ref, run_by, **k: asked.append(("ran", ref))
                            or ([], None))
        monkeypatch.setattr(cp, "_finish_supply", lambda *a: None)
        cp._run_qa_interactive_local_folder("me", commit_default=False)
        assert asked[1] == "keep?" and asked[-1] == ("ran", None)
        assert len([a for a in asked if isinstance(a, str) and "reference" in a]) == 0


class TestAKeptFolderIsWhateverRecognitionPlaces:
    """Criterion 4."""

    def test_a_partial_folder_is_filed_by_recognition(self, monkeypatch, tmp_path):
        folder = tmp_path / "d"
        folder.mkdir()
        _csv(folder, "cp_clients.csv")
        _csv(folder, "cp_carers.csv")
        (folder / "covering note.pdf").write_text("hello")
        filed_paths = []

        def fake_file_or_trial(paths, *a, **k):
            filed_paths.extend(os.path.basename(p) for p in paths)
            raise click.ClickException("stop here")
        monkeypatch.setattr(common, "file_or_trial", fake_file_or_trial)
        with pytest.raises(click.ClickException, match="stop here"):
            cp.run_check_local_folder(str(folder), None, "me", keep=True)
        assert sorted(filed_paths) == ["cp_carers.csv", "cp_clients.csv"]

    def test_a_trial_folder_still_needs_all_six(self, tmp_path):
        folder = tmp_path / "d"
        folder.mkdir()
        _csv(folder, "cp_clients.csv")
        with pytest.raises(click.ClickException, match="all 6"):
            cp.run_check_local_folder(str(folder), str(folder), "me", keep=False)


class TestAFileOfAnotherCollection:
    """Criterion 5, at the terminal: refused naming the collection, before any
    question and with no trial on offer."""

    def test_cp_refuses_a_birth_registrations_file(self, monkeypatch, tmp_path):
        folder = tmp_path / "d"
        folder.mkdir()
        _csv(folder, "birth_registrations_2026-01-01.csv")
        wrote = []
        monkeypatch.setattr(hand_filing, "file_supply", lambda *a, **k: wrote.append(1))
        out = _runner.invoke(cp.qa_command, ["--folder", str(folder), "--commit"])
        assert out.exit_code != 0
        assert "civil-registration" in _flat(out.output) and not wrote
        assert "TRIAL instead" not in out.output


class TestAKeptSingleTableIsAnArrival:
    """Criteria 1 and 3: through the lifecycle, its siblings from its filed
    period - nothing borrowed from an earlier run's delivery."""

    def test_it_goes_through_the_filed_delivery_and_borrows_nothing(self, monkeypatch,
                                                                    tmp_path):
        from types import SimpleNamespace

        f = _csv(tmp_path, "cp_clients.csv")
        filed = SimpleNamespace(delivery_name="handfiled-x", paths=[f], run_id="cp_clients__1",
                                received_at=None)
        monkeypatch.setattr(common, "file_or_trial", lambda *a, **k: filed)
        through = []
        monkeypatch.setattr(cp, "_check_filed_delivery",
                            lambda filed, run_by, on_step=None: through.append(filed) or [])
        monkeypatch.setattr(cp, "default_reference",
                            lambda *a: pytest.fail("a kept table borrowed its siblings"))
        results, got = cp.run_check_single_table("cp_clients", f, "me", keep=True)
        assert through == [filed] and got is filed

    def test_a_table_recognition_disagrees_with_is_refused(self, tmp_path):
        f = _csv(tmp_path, "cp_carers.csv")
        with pytest.raises(click.ClickException, match="recognised as cp_carers"):
            cp.run_check_single_table("cp_clients", f, "me", keep=True)


class TestARecordedArrivalIsNeverRecordedAgain:
    """Criteria 6 to 8."""

    def test_commit_is_refused_naming_trial(self, monkeypatch):
        monkeypatch.setattr(common, "recorded_runs", lambda ids: set(ids))
        with pytest.raises(click.ClickException, match="--trial"):
            common.decide_record("cp_clients__1", keep=True)

    def test_asked_at_the_terminal_it_runs_a_trial_saying_why(self, monkeypatch, capsys):
        monkeypatch.setattr(common, "recorded_runs", lambda ids: set(ids))
        assert common.decide_record("cp_clients__1", keep=None) is False
        assert "already has recorded QA" in capsys.readouterr().out

    def test_the_picker_marks_it(self, monkeypatch):
        monkeypatch.setattr(common, "recorded_runs", lambda ids: {"cp_clients__1"})
        manifest = [{"run_id": "cp_clients__1", "received_at": "2026-01-01T00:00:00+00:00",
                     "delivery": "d"},
                    {"run_id": "cp_clients__2", "received_at": "2026-01-02T00:00:00+00:00",
                     "delivery": "e"}]
        choices = cp.picker_choices(manifest)
        assert choices[0].endswith("- recorded") and not choices[1].endswith("- recorded")
        assert bdm.picker_choices(manifest)[0].endswith("- recorded")

    def test_an_unrecorded_arrival_may_be_kept(self, monkeypatch):
        monkeypatch.setattr(common, "recorded_runs", lambda ids: set())
        assert common.decide_record("cp_clients__1", keep=True) is True


class TestAFallbackTrialAsksForItsReference:
    """Criterion 14, post-build-review #120 D5: a kept file filing refused,
    turned into a trial at the terminal, used to stop at once saying "pass
    --reference-file" - a trial offered and then not runnable, and a flag
    named to a person in a menu."""

    def _tty(self, monkeypatch, on):
        import sys

        monkeypatch.setattr(sys.stdin, "isatty", lambda: on)
        monkeypatch.setattr(sys.stdout, "isatty", lambda: on)

    def test_at_a_terminal_it_is_asked_for(self, monkeypatch):
        self._tty(monkeypatch, True)
        asked = []
        monkeypatch.setattr(common, "path_prompt",
                            lambda m, flag_hint: asked.append(m) or "/x/ref.csv")
        got = common.reference_for_fallback_trial(None, "--reference-file", "file")
        assert got == "/x/ref.csv" and "reference" in asked[0].lower()

    def test_one_already_given_is_used(self, monkeypatch):
        monkeypatch.setattr(common, "path_prompt", lambda *a, **k: pytest.fail("asked"))
        assert common.reference_for_fallback_trial("/r.csv", "--reference-file", "file") == \
            "/r.csv"

    def test_no_answer_runs_nothing_and_says_so(self, monkeypatch):
        self._tty(monkeypatch, True)
        monkeypatch.setattr(common, "path_prompt", lambda m, flag_hint: None)
        with pytest.raises(click.ClickException, match="Nothing was run") as caught:
            common.reference_for_fallback_trial(None, "--reference-file", "file")
        assert "--reference-file" not in str(caught.value.message)

    def test_without_a_terminal_it_names_the_flag(self, monkeypatch):
        self._tty(monkeypatch, False)
        with pytest.raises(click.ClickException, match="--reference-file"):
            common.reference_for_fallback_trial(None, "--reference-file", "file")


class TestTheHelpSaysWhatTheRoutesNowDo:
    """#120 D11: two help texts still described defaults that criterion 14
    and REQ-QAC-108 removed."""

    @pytest.mark.parametrize("command", [bdm.qa_command, cp.qa_command])
    def test_no_stale_default(self, command):
        out = _flat(_runner.invoke(command, ["--help"]).output)
        assert "auto-pull" not in out and "defaults to the last Promoted run" not in out
