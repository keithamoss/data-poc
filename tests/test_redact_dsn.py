"""post-build-review #86 - a connection string in an error message never
carries its password, whichever form it is written in.

`_redact` handled only the URL form (`postgresql://user:pw@host`). The
keyword form libpq equally accepts - `host=... password=...` - passed
through untouched, and errors from here reach CI logs on a public
repository. Latent: every DSN this project sets is URL-form, which is
exactly how a gap like this survives until the day it doesn't.
"""
from __future__ import annotations

import pytest

from qa_tools.common import supply_db

SECRET = "s3cretpw"


@pytest.mark.parametrize("dsn", [
    f"postgresql://user:{SECRET}@db.example:5432/supply",
    f"host=db.example port=5432 user=u password={SECRET} dbname=supply",
    f"host=db.example password='{SECRET}' dbname=supply",
    f"host=db.example password = {SECRET} dbname=supply",
    f"postgresql://db.example/supply?user=u&password={SECRET}",
], ids=["url", "keyword", "keyword-quoted", "keyword-spaced", "url-query"])
def test_the_password_never_survives(dsn):
    assert SECRET not in supply_db._redact(dsn)


def test_the_host_is_still_named():
    """The point of the message is to say WHERE it could not reach."""
    assert "db.example" in supply_db._redact(
        f"host=db.example password={SECRET} dbname=supply")


def test_a_string_that_cannot_be_parsed_shows_nothing_of_itself():
    """A malformed string may put the password anywhere; with nothing to
    anchor on, the safe answer is to show none of it."""
    got = supply_db._redact(f"host=db.example {SECRET} password")
    assert SECRET not in got


def test_connecting_with_a_bad_keyword_dsn_leaks_nothing():
    """End to end, through connect(): its message also quotes psycopg's
    own error, which must not reintroduce what _redact removed."""
    with pytest.raises(supply_db.SupplyDbError) as caught:
        supply_db.connect(dsn=f"host=127.0.0.1 port=1 password={SECRET} user",
                          label="test-redact")
    assert SECRET not in str(caught.value)
