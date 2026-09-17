"""Neither qa_tools/{bdm,cp}/evidently_check_lifecycle_retired.py is ever
`import`-ed by real code - qa_tools/common/validate_check_lifecycle.py
reads them as plain text (a real Python dict literal it evals, not a
module it imports - see that module's own docstring), since it needs
BOTH the current working-tree content and a previous git ref's content,
and only the former can be a real import. This exists purely so the
files themselves stay import-clean and their current (still-empty, per
each file's own docstring - no Evidently check has been retired yet)
shape gets checked somewhere, matching the pattern every other
`-retired.py`/`-retired.yaml` file's shape gets exercised through their
own tool's real invocation."""
from __future__ import annotations

from qa_tools.bdm.evidently_check_lifecycle_retired import CHECK_LIFECYCLE as bdm_retired
from qa_tools.cp.evidently_check_lifecycle_retired import CHECK_LIFECYCLE as cp_retired


def test_bdm_retired_evidently_checks_is_currently_empty():
    assert bdm_retired == {}


def test_cp_retired_evidently_checks_is_currently_empty():
    assert cp_retired == {}
