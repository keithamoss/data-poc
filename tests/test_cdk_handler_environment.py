"""Both handlers get a stated environment and a database (REQ-PIPE-152's
decision: every connection refuses without MOTHMAN_ENVIRONMENT and a
matching qa.identity row, and the stack gave both Lambdas no environment at
all). aws_cdk is not installed here and the stack has never been
synthesised, so this reads the stack's source rather than building it."""
from __future__ import annotations

import ast
from pathlib import Path

STACK = Path(__file__).resolve().parent.parent / "aws" / "cdk" / "data_pipeline_stack.py"


def _functions() -> list[ast.Call]:
    tree = ast.parse(STACK.read_text())
    return [node for node in ast.walk(tree) if isinstance(node, ast.Call)
            and getattr(node.func, "attr", None) == "Function"]


def test_both_handlers_are_given_the_handler_environment():
    functions = _functions()
    assert len(functions) == 2
    for call in functions:
        [env] = [k.value for k in call.keywords if k.arg == "environment"]
        assert "handler_environment" in ast.unparse(env)


def test_the_environment_names_both_variables_from_required_context():
    source = STACK.read_text()
    assert '"MOTHMAN_ENVIRONMENT": self._required_context("mothman_environment")' in source
    assert '"MOTHMAN_SUPPLY_DSN": self._required_context("supply_dsn")' in source
    assert "try_get_context" in source and "raise ValueError" in source, (
        "a missing value is refused, never defaulted")
