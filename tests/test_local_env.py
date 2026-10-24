"""Reading a developer's own `.env`, without trampling anything.

The override rule is the one with teeth. CI supplies MOTHMAN_TEST_DSN
through the workflow; a `.env` that clobbered it would point the run at
a database that does not exist on the runner, and the failure would
read as a code fault rather than as a config one.
"""
from __future__ import annotations

import pytest

from qa_tools.common import local_env


@pytest.fixture(autouse=True)
def _fresh():
    """The loader is idempotent by design, so these have to reset it."""
    local_env._loaded = False
    yield
    local_env._loaded = False


def _env_file(tmp_path, body: str):
    path = tmp_path / ".env"
    path.write_text(body)
    return path


def test_it_sets_what_is_not_already_there(tmp_path, monkeypatch):
    monkeypatch.delenv("MOTHMAN_PROBE", raising=False)
    applied = local_env.load_local_env(_env_file(tmp_path, 'MOTHMAN_PROBE="from-file"\n'))
    assert applied == ["MOTHMAN_PROBE"]
    import os
    assert os.environ["MOTHMAN_PROBE"] == "from-file"


def test_it_never_overrides_something_already_set(tmp_path, monkeypatch):
    """THE ONE THAT MATTERS. CI's own value has to win."""
    monkeypatch.setenv("MOTHMAN_PROBE", "from-the-shell")
    applied = local_env.load_local_env(_env_file(tmp_path, 'MOTHMAN_PROBE="from-file"\n'))
    import os
    assert os.environ["MOTHMAN_PROBE"] == "from-the-shell"
    assert applied == [], "a name it did not set must not be reported as set"


def test_a_missing_file_is_ordinary(tmp_path):
    """Most checkouts have no .env - CI, a fresh clone, the agent
    sandbox (whose hook sets the variables directly)."""
    assert local_env.load_local_env(tmp_path / "nope.env") == []


def test_it_is_idempotent(tmp_path, monkeypatch):
    """One process can be both entry points - `mothman check` runs
    pytest, so both loaders fire."""
    monkeypatch.delenv("MOTHMAN_PROBE", raising=False)
    path = _env_file(tmp_path, 'MOTHMAN_PROBE="x"\n')
    assert local_env.load_local_env(path) == ["MOTHMAN_PROBE"]
    assert local_env.load_local_env(path) == []


def test_force_reloads(tmp_path, monkeypatch):
    monkeypatch.delenv("MOTHMAN_PROBE", raising=False)
    path = _env_file(tmp_path, 'MOTHMAN_PROBE="x"\n')
    local_env.load_local_env(path)
    monkeypatch.delenv("MOTHMAN_PROBE", raising=False)
    assert local_env.load_local_env(path, force=True) == ["MOTHMAN_PROBE"]


def test_comments_and_blank_lines_are_not_variables(tmp_path, monkeypatch):
    monkeypatch.delenv("MOTHMAN_PROBE", raising=False)
    applied = local_env.load_local_env(_env_file(
        tmp_path, '# a comment\n\nMOTHMAN_PROBE="x"\n'))
    assert applied == ["MOTHMAN_PROBE"]


class TestTheCommittedExample:
    """`.env.example` is the half that IS committed, so it has to stay
    honest about what the code reads."""

    def test_it_exists(self):
        assert local_env.EXAMPLE_PATH.exists()

    def test_it_holds_no_real_secret(self):
        """It is committed to a public repository. A placeholder
        password is fine; anything that looks like a real host is not."""
        body = local_env.EXAMPLE_PATH.read_text()
        assert "localhost" in body
        for suspicious in (".rds.amazonaws.com", ".azure.com", ".supabase.co"):
            assert suspicious not in body, f"{suspicious} looks like a real host"

    @pytest.mark.parametrize("name", [
        "MOTHMAN_SUPPLY_DSN", "MOTHMAN_TEST_DSN", "MOTHMAN_ENVIRONMENT",
    ])
    def test_it_documents_every_variable_the_code_requires(self, name):
        """A variable the code refuses to start without, missing from
        the file whose whole job is to name them, is the gap this
        catches."""
        assert name in local_env.EXAMPLE_PATH.read_text()

    def test_the_env_file_itself_is_gitignored(self):
        """It holds a password and this repository is public."""
        ignored = (local_env.ROOT / ".gitignore").read_text().splitlines()
        assert ".env" in [line.strip() for line in ignored]
