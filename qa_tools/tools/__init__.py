"""The shared QA tool modules (REQ-QAC-242): one per tool, and one staging
module, serving every collection. What differs by collection is read from
its adapter's per-tool sub-objects and named legacy flags
(qa_tools/collections/base.py) - never chosen by comparing a collection's
id, short or run prefix (criterion 6)."""
