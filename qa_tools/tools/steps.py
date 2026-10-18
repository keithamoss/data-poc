"""The shared orchestrator's steps, by name, in the order a run takes them -
on its own so that a progress bar can be sized without importing a QA tool
(REQ-TEST-245 criterion 7: `mothman --help` loads none)."""

RUN_STEPS = ("dbt-core", "Soda Core", "datacontract-cli", "Evidently", "Dataset statistics")
