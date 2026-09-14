"""Tool-generic code shared across datasets - subprocess/API invocation
boilerplate and manifest-parsing plumbing that's identical regardless of
which dataset is being checked. Never anything dataset-specific (which
tests exist, what they mean) - that stays in qa_tools/<dataset>/."""
