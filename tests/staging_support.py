"""Shorthand for staging one file through the shared staging module
(qa_tools/tools/stage.py, REQ-QAC-242), in the two shapes these tests were
written against: Birth Registrations' one table, and one named Child
Protection table."""
from __future__ import annotations

from qa_tools.tools import stage

BDM = "civil-registration"
CP = "child-protection"


def stage_bdm(run_id: str, csv_path: str, run_date: str | None = None, **kwargs):
    return stage.stage_table(BDM, run_id, "birth_registrations", csv_path,
                             run_date=run_date, **kwargs)


def stage_cp(run_id: str, table: str, csv_path: str, **kwargs):
    return stage.stage_table(CP, run_id, table, csv_path, **kwargs)
