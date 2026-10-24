"""The grouped, filtered picker (REQ-TEST-252 criteria 5, 7 and 8), driven
in-process with keystrokes - the same Application a person sees, fed through
prompt_toolkit's pipe input rather than a terminal."""
from __future__ import annotations

import pytest

from cli import common

GROUPS = [("Department of Health - Hospitals", ["Hospital Admissions", "Emergency Waits"]),
          ("Department of Justice", ["Court Lodgements"])]
#: What else a choice is known by (REQ-TEST-252, Keith 2026-10-18: "filter on
#: short and names") - its short, its id and its datasets' names.
CANCELLED = "<cancelled with Ctrl-C>"
TERMS = {"Hospital Admissions": ("hadm", "hospital-admissions"),
         "Emergency Waits": ("edw", "ed-waits", "ED Triage"),
         "Court Lodgements": ("clod", "court-lodgements")}


def _pick(keys: str, *, top=(), terms=None):
    from prompt_toolkit.application import create_app_session
    from prompt_toolkit.input import create_pipe_input
    from prompt_toolkit.output import DummyOutput

    with create_pipe_input() as inp, create_app_session(input=inp, output=DummyOutput()):
        question = common._filtered_question("Which dataset?", GROUPS, tuple(top), terms or {})
        # CTRL-C LAST, so a picker that ignores an Enter it should act on
        # raises here rather than waiting for input for ever.
        inp.send_text(keys + "\x03")
        # IN A THREAD OF ITS OWN (post-build-review #271): a Playwright test on
        # the same worker leaves pytest-playwright's session-scoped sync
        # Playwright - and its running event loop - in the main thread for the
        # rest of the session, and prompt_toolkit's run() is asyncio.run(),
        # which refuses to start inside one. in_thread is prompt_toolkit's own
        # option for exactly that case, and it behaves the same with no loop.
        try:
            return question.application.run(in_thread=True)
        except KeyboardInterrupt:  # pytest would take it as its own and stop
            return CANCELLED


class TestTheFilter:
    def test_it_matches_a_choices_label_case_insensitively(self):
        assert _pick("ADMIS\r") == "Hospital Admissions"

    def test_it_matches_a_group_heading(self):
        assert _pick("justice\r") == "Court Lodgements"

    @pytest.mark.parametrize("typed,expected", [("hadm", "Hospital Admissions"),
                                                ("court-lodg", "Court Lodgements"),
                                                ("triage", "Emergency Waits")])
    def test_it_matches_a_short_an_id_and_a_dataset_name(self, typed, expected):
        assert _pick(f"{typed}\r", terms=TERMS) == expected

    def test_a_top_entry_is_found_by_its_own_text(self):
        """post-build-review #231: a top entry was never filtered, but did not
        count as a match either, so typing toward it left it highlighted
        under 'Nothing matches' and Enter did nothing."""
        assert _pick("corr\r", top=("Pending corrections (2)",)) == "Pending corrections (2)"


class TestNothingMatches:
    def test_enter_keeps_the_prompt_open_and_ctrl_c_leaves(self):
        assert _pick("zzz\r") == CANCELLED

    def test_deleting_widens_it_again(self):
        assert _pick("zzz\r\x7f\x7f\x7fcourt\r") == "Court Lodgements"

    def test_a_heading_is_never_an_answer(self):
        for keys in ("\r", "\x1b[B\r", "\x1b[B\x1b[B\r", "\x1b[B\x1b[B\x1b[B\r"):
            got = _pick(keys)
            assert got not in {h for h, _ in GROUPS}, (keys, got)
