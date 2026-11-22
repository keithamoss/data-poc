"""The ORDER of the dataset statuses and the WORDS for them, held once
(REQ-PIPE-390, SPLIT D4 SETTLED by Keith 2026-11-03): nodata below green
below amber below red, and the label, verb and count a person reads for
each status.

EVERY PYTHON READER READS THESE: qa_tools/common/dataset_status.py's
rollups, qa_tools/common/rechecking.py, the bootstrap's target agreement and
the Linkage Products provider rank statuses through ORDERED_STATUSES, and the
terminal and the scenario map's writer word them through status_words - so a
re-check, a target trial, a planned verdict and the scenario map cannot rank
or name green, amber and red differently. `mothman check`'s imports gate
fails a module outside asset_model/ and tests/ that defines a ranking of its
own (criterion 5).

THE DASHBOARD PAGE KEEPS ITS OWN COPY (criterion 4): it has no build step,
so status-cases.json's shared cases are the agreement between them
(tests/test_status_parity.py, tests-js/status-parity.test.js).

THE REST OF THE STATUS RULES - which statuses are recognised where, the
rollups, threshold arithmetic - stay in qa_tools/common/dataset_status.py,
which reads dashboard JSON; only the order and the words are shared, because
only they are what the generator and the bootstrap need.
"""
from __future__ import annotations


class UnknownStatusError(ValueError):
    """A recorded status neither implementation recognises.

    Raised rather than fallen back on, and that is the whole point of
    REQ-QAC-047. The previous behaviour converted "I do not know what
    this is" into "this is fine" - an unrecognised verdict fell through
    to threshold arithmetic here, and passed straight out to a rollup
    that could not order it in the dashboard, where the reduce kept its
    green seed. Two different routes to the same false green.

    This changes the failure mode from silently-wrong to noisily-broken.
    That is deliberate: a malformed committed result now stops a
    dashboard build that would previously have rendered a green tile."""


# The agreed vocabulary. Held to status-cases.json by tests/
# test_status_parity.py and tests-js/status-parity.test.js, which is what
# stops this module and the dashboard's own STATUS_ORDER drifting apart
# the way they did in plans/qa-pipeline.md item 74.
#
# The numbers ARE the rule: worst-of is a reduce seeded at green, so
# nodata sits below green where it can only ever lose. "Nothing to show
# yet" must not outrank a real green, and must not look like the worst
# outcome either.
ORDERED_STATUSES = {"nodata": -1, "green": 0, "amber": 1, "red": 2}

# Retained under its original name because callers outside this module
# index it directly. Same mapping, now including nodata - whose absence
# was the defect.
STATUS_ORDER = ORDERED_STATUSES


#: The three VERDICTS in their order - the ordered statuses less nodata,
#: which is "nothing to measure", not a verdict. What a re-check, a target
#: trial and a planned verdict rank by (rechecking.is_worse,
#: target_agreement.responsible, the Linkage Products provider's worst()),
#: where a quiet status is a verdict of its own and never ranked against
#: green (REQ-PIPE-390 criterion 1).
VERDICT_ORDER = {s: n for s, n in ORDERED_STATUSES.items() if n >= 0}


#: The words a person reads for each status (REQ-DASH-359 criterion 1,
#: REQ-TEST-360 criterion 1): the LABEL for a pill, a legend or a status
#: reached or held ('Fail', 'became Fail'); the VERB form for running prose
#: ('failing because ...'); the COUNT form for a count ('2 failing'). Held
#: equal to status-cases.json's vocabulary.labels block by tests/
#: test_status_parity.py, as the page's own copy is by tests-js/
#: status-parity.test.js - so the terminal's words and the page's cannot
#: drift apart. The stored VALUES (the keys) do not change.
STATUS_WORDS = {
    "green": {"label": "Pass", "verb": "passing", "count": "passing"},
    "amber": {"label": "Warn", "verb": "warning", "count": "warning"},
    "red": {"label": "Fail", "verb": "failing", "count": "failing"},
    "nodata": {"label": "No data", "verb": "no data", "count": "no data"},
    "exhausted": {"label": "Schedule ended", "verb": "schedule ended",
                  "count": "schedule ended"},
    "inactive": {"label": "No rule defined", "verb": "no rule defined",
                 "count": "no rule defined"},
    "notchecked": {"label": "Not checked", "verb": "not checked", "count": "not checked"},
    "notyetchecked": {"label": "Not yet checked", "verb": "not yet checked",
                      "count": "not yet checked"},
    "notcounted": {"label": "Not counted", "verb": "not counted", "count": "not counted"},
    "turnedoff": {"label": "Turned off", "verb": "turned off", "count": "turned off"},
}
STATUS_WORD_FORMS = ("label", "verb", "count")


def status_words(value: str, form: str = "label") -> str:
    """A status in the words a person reads - 'Fail', 'failing' - never its
    stored value. REFUSES a status it has no word for (REQ-QAC-047's rule):
    a raw 'red' printed because nothing recognised it is exactly the leak
    REQ-DASH-359 closes, and a guess is worse than a refusal."""
    if form not in STATUS_WORD_FORMS:
        raise ValueError(f"unknown status word form {form!r}; forms are "
                         f"{', '.join(STATUS_WORD_FORMS)}")
    words = STATUS_WORDS.get(value) if isinstance(value, str) else None
    if words is None:
        raise UnknownStatusError(
            f"unrecognised status {value!r}: it has no words to show, so it is refused "
            "rather than printed raw - see status-cases.json.")
    return words[form]
