"""Every connection needs a stated environment, with no default, and
production asks a person to type its id before changing anything by hand
(REQ-PIPE-093)."""
from __future__ import annotations

import psycopg
import pytest

from qa_tools.common import environments, supply_db

UNREACHABLE = "postgresql://someone:s3cretpw@nohost.invalid:5999/nodb"
KEYWORD = "host=nohost.invalid port=5999 user=someone password=s3cretpw dbname=nodb"


class TestNoEnvironmentNoConnection:
    """Criteria 1 and 2."""

    def test_refused_before_connecting_naming_the_variable_and_the_ids(self, monkeypatch):
        monkeypatch.delenv(environments.ENVIRONMENT_ENV, raising=False)
        tried = []
        monkeypatch.setattr(psycopg, "connect", lambda *a, **k: tried.append(a))
        with pytest.raises(environments.EnvironmentError_) as exc:
            supply_db.connect(dsn=UNREACHABLE)
        assert not tried, "it must refuse BEFORE connecting"
        assert environments.ENVIRONMENT_ENV in str(exc.value)
        assert "production" in str(exc.value) and "local" in str(exc.value)

    def test_reads_need_it_too(self, monkeypatch):
        monkeypatch.delenv(environments.ENVIRONMENT_ENV, raising=False)
        with pytest.raises(environments.EnvironmentError_):
            supply_db.connect(read_only=True, dsn=UNREACHABLE)


class TestAnUnreachableDatabase:
    """Criterion 3."""

    @pytest.mark.parametrize("dsn", [UNREACHABLE, KEYWORD])
    def test_names_the_environment_and_host_never_the_password(self, monkeypatch, dsn):
        monkeypatch.setenv(environments.ENVIRONMENT_ENV, "local")
        with pytest.raises(supply_db.SupplyDbError) as exc:
            supply_db.connect(dsn=dsn)
        message = str(exc.value)
        assert "local" in message and "nohost.invalid" in message
        assert "s3cretpw" not in message

    def test_a_driver_error_repeating_the_password_is_scrubbed(self, monkeypatch):
        monkeypatch.setenv(environments.ENVIRONMENT_ENV, "local")

        def leaky(*a, **k):
            raise psycopg.OperationalError("bad conninfo near 'password=s3cretpw'")
        monkeypatch.setattr(psycopg, "connect", leaky)
        with pytest.raises(supply_db.SupplyDbError) as exc:
            supply_db.connect(dsn=KEYWORD)
        assert "s3cretpw" not in str(exc.value)


class TestTheDeclaredProperties:
    """Criteria 5, 8, 11 and 16."""

    def test_only_production_asks_for_confirmation(self):
        asks = {e.id: e.confirm_changes for e in environments.all_environments()}
        assert asks["production"] is True
        assert not any(asks[i] for i in ("local", "sandbox", "ci", "test"))

    def test_ticketing_is_off_for_ci_and_test(self):
        tickets = {e.id: e.ticketing for e in environments.all_environments()}
        assert tickets["ci"] is False and tickets["test"] is False

    def test_a_test_environment_publishes_asks_and_tickets_nothing(self):
        test = environments.get("test")
        assert (test.publishes, test.confirm_changes, test.ticketing) == (False, False, False)

    def test_the_suite_states_test(self):
        assert environments.current().id == "test"


class TestTicketingFollowsTheEnvironment:
    """Criteria 10, 12 and 13."""

    def test_a_platform_variable_does_not_turn_it_on(self, monkeypatch):
        from qa_tools.common import ticket_reconciler

        monkeypatch.setenv("GITHUB_REPOSITORY", "someone/else")
        assert ticket_reconciler.service_from_env() is None  # `test` declares it off

    def _ticketing_env(self, tmp_path, monkeypatch, repo):
        envs = tmp_path / "environments.yaml"
        envs.write_text("environments:\n  - {id: prodlike, label: P, ticketing: true}\n")
        monkeypatch.setattr(environments, "ENVIRONMENTS_PATH", envs)
        monkeypatch.setenv(environments.ENVIRONMENT_ENV, "prodlike")
        monkeypatch.setattr(environments, "ticket_repository", lambda: repo)

    def test_the_repository_comes_from_the_asset(self, tmp_path, monkeypatch):
        from qa_tools.common import ticket_reconciler

        self._ticketing_env(tmp_path, monkeypatch, "owner/tickets")
        monkeypatch.setenv("GITHUB_REPOSITORY", "someone/else")
        service = ticket_reconciler.service_from_env()
        assert (service.owner, service.repo) == ("owner", "tickets")

    def test_on_with_no_repository_is_refused_before_connecting(self, tmp_path, monkeypatch):
        self._ticketing_env(tmp_path, monkeypatch, None)
        tried = []
        monkeypatch.setattr(psycopg, "connect", lambda *a, **k: tried.append(a))
        with pytest.raises(environments.EnvironmentError_, match="ticket"):
            supply_db.connect(dsn=UNREACHABLE)
        assert not tried

    def test_the_asset_names_this_repository(self):
        assert environments.ticket_repository() == "keithamoss/data-poc"


class TestTypingTheEnvironment:
    """Criteria 4, 6 and 7, at the terminal's one confirmation."""

    def _production(self, tmp_path, monkeypatch):
        envs = tmp_path / "environments.yaml"
        envs.write_text("environments:\n"
                        "  - {id: production, label: P, confirm_changes: true}\n")
        monkeypatch.setattr(environments, "ENVIRONMENTS_PATH", envs)
        monkeypatch.setenv(environments.ENVIRONMENT_ENV, "production")

    def test_yes_does_not_skip_it(self, tmp_path, monkeypatch):
        from cli import common

        self._production(tmp_path, monkeypatch)
        monkeypatch.setattr(common, "require_tty", lambda hint: None)
        monkeypatch.setattr(common, "_ask_text", lambda message: "production")
        assert common.confirm_change("Record it?", yes=True) is True

    def test_a_mismatch_records_nothing(self, tmp_path, monkeypatch, capsys):
        from cli import common

        self._production(tmp_path, monkeypatch)
        monkeypatch.setattr(common, "require_tty", lambda hint: None)
        monkeypatch.setattr(common, "_ask_text", lambda message: "Production")
        assert common.confirm_change("Record it?", yes=True) is False

    def test_no_terminal_no_change(self, tmp_path, monkeypatch):
        from cli import common

        self._production(tmp_path, monkeypatch)

        def no_tty(hint):
            raise SystemExit(2)
        monkeypatch.setattr(common, "require_tty", no_tty)
        with pytest.raises(SystemExit):
            common.confirm_change("Record it?", yes=True)

    def test_elsewhere_it_is_the_ordinary_confirmation(self, monkeypatch):
        from cli import common

        assert common.confirm_change("Record it?", yes=True) is True
