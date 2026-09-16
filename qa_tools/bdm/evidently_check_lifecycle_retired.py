"""
Retired Evidently checks for run_evidently_bdm.py (plans/publishing-
and-history.md Thread D, Keith's call 2026-09-16: a check_id, once
introduced, is permanently unique - it must never be changed or
deleted, even once retired).

Evidently's checks are plain Python (hardcoded calls in
run_evidently_bdm.py), so - unlike the YAML-driven tools - there's no
"tool actually executes whatever's declared here" risk: retiring a
check here means the orchestration code simply stops calling it, same
day its entry moves from evidently_check_lifecycle.py's CHECK_LIFECYCLE
to this file's. Kept as a separate sibling file anyway, for uniformity
with the other 3 tools' own `-retired` files rather than leaving
Evidently as a special case with its own reasoning to remember.

Add `retired_as_of`/`retired_reason` to a check's dict entry when moving
it here (both required together - see check_lifecycle.py's
CheckMetadata). Never edit a check_id, never delete an entry outright.
"""
from __future__ import annotations

CHECK_LIFECYCLE: dict = {}
