"""Which deployment this is, and refusing to guess.

The refusals are the point. Once the dashboard is built where the data
is, a build that cannot say where it came from is an artifact that can
be mistaken for the published one - so every way of not knowing has to
stop rather than pick something reasonable.
"""
from __future__ import annotations

import pytest
import yaml

from qa_tools.common import environments as env


def _write(tmp_path, envs) -> str:
    path = tmp_path / "environments.yaml"
    path.write_text(yaml.safe_dump({"environments": envs}))
    return str(path)


class TestTheCommittedList:
    """Against the real committed file - the point is that this
    repository's own declaration is valid and says what it should."""

    def test_the_real_file_parses(self):
        assert [e.id for e in env.all_environments()]

    def test_exactly_one_environment_publishes(self):
        publishing = [e.id for e in env.all_environments() if e.publishes]
        assert len(publishing) == 1, \
            "two deployments that both publish race to overwrite one dashboard"

    def test_every_id_is_a_usable_identifier(self):
        """An id reaches a schema name, a file name and a URL."""
        for e in env.all_environments():
            assert env._SAFE_ID.match(e.id), e.id

    def test_every_environment_is_described(self):
        """A bare id does not tell a reader of the dashboard what they
        are looking at."""
        for e in env.all_environments():
            assert e.label and e.description, e.id


class TestKnowingWhichOneThisIs:
    def test_it_reads_the_environment_variable(self, monkeypatch, tmp_path):
        path = _write(tmp_path, [{"id": "sandbox", "label": "Sandbox"}])
        monkeypatch.setenv(env.ENVIRONMENT_ENV, "sandbox")
        assert env.current(path).id == "sandbox"

    def test_unset_is_refused_rather_than_defaulted(self, monkeypatch, tmp_path):
        """THE IMPORTANT ONE. 'local' is the tempting default and would
        mean a production build silently labelled as somebody's laptop."""
        path = _write(tmp_path, [{"id": "local", "label": "Local"}])
        monkeypatch.delenv(env.ENVIRONMENT_ENV, raising=False)
        with pytest.raises(env.EnvironmentError_, match="not set"):
            env.current(path)

    def test_the_refusal_names_the_valid_options(self, monkeypatch, tmp_path):
        path = _write(tmp_path, [{"id": "local", "label": "L"}, {"id": "production", "label": "P"}])
        monkeypatch.delenv(env.ENVIRONMENT_ENV, raising=False)
        with pytest.raises(env.EnvironmentError_) as exc:
            env.current(path)
        assert "local" in str(exc.value) and "production" in str(exc.value)

    def test_a_typo_is_refused_rather_than_becoming_a_new_environment(self, monkeypatch, tmp_path):
        """The whole reason the list is worth having: MOTHMAN_ENVIRONMENT
        =prod against a list saying `production` must stop."""
        path = _write(tmp_path, [{"id": "production", "label": "Production"}])
        monkeypatch.setenv(env.ENVIRONMENT_ENV, "prod")
        with pytest.raises(env.EnvironmentError_, match="not a declared environment"):
            env.current(path)

    def test_current_or_none_is_quiet_for_callers_that_may_not_know(self, monkeypatch, tmp_path):
        path = _write(tmp_path, [{"id": "local", "label": "L"}])
        monkeypatch.delenv(env.ENVIRONMENT_ENV, raising=False)
        assert env.current_or_none(path) is None


class TestAMalformedDeclarationStops:
    def test_a_missing_file(self, tmp_path):
        with pytest.raises(env.EnvironmentError_, match="does not exist"):
            env.all_environments(tmp_path / "nope.yaml")

    def test_an_empty_list(self, tmp_path):
        path = tmp_path / "environments.yaml"
        path.write_text("environments: []")
        with pytest.raises(env.EnvironmentError_, match="no environments"):
            env.all_environments(path)

    @pytest.mark.parametrize("bad_id", ["Production", "pro-duction", "pro duction", "", None])
    def test_an_unusable_id(self, tmp_path, bad_id):
        path = _write(tmp_path, [{"id": bad_id, "label": "x"}])
        with pytest.raises(env.EnvironmentError_, match="usable environment id"):
            env.all_environments(path)

    def test_a_duplicate_id(self, tmp_path):
        path = _write(tmp_path, [{"id": "local", "label": "A"}, {"id": "local", "label": "B"}])
        with pytest.raises(env.EnvironmentError_, match="more than once"):
            env.all_environments(path)

    def test_two_publishers(self, tmp_path):
        path = _write(tmp_path, [
            {"id": "a", "label": "A", "publishes": True},
            {"id": "b", "label": "B", "publishes": True}])
        with pytest.raises(env.EnvironmentError_, match="claim to publish"):
            env.all_environments(path)

    def test_no_publisher_is_allowed(self, tmp_path):
        """A data asset with no production deployment yet is a real
        state, not a misconfiguration."""
        path = _write(tmp_path, [{"id": "local", "label": "L"}])
        assert env.all_environments(path)
