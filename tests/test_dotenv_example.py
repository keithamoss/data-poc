"""`.env.example` names the server, not a database (post-build-review #334
L6; Keith, 2026-11-15): a `.env` copied from it would otherwise point every
command at the pre-split `supply`, which no asset owns, over the session
hook's MOTHMAN_PG."""
from __future__ import annotations

from pathlib import Path

import pytest
from dotenv import dotenv_values

from qa_tools.common import supply_db

ROOT = Path(__file__).resolve().parent.parent


def test_it_sets_a_server_and_no_supply_database():
    values = dotenv_values(ROOT / ".env.example")
    assert values, ".env.example holds no values - the test would prove nothing"
    assert supply_db.SUPPLY_DSN_ENV not in values
    server = values[supply_db.SERVER_ENV]
    assert supply_db.on_server(server, "supply_quarterly").endswith("/supply_quarterly")


#: The data asset this module's tests act for (C11).
pytestmark = pytest.mark.asset("quarterly")
