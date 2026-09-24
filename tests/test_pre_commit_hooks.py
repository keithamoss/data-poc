"""The repo's own `local` pre-commit hooks actually fire, and actually
run something that exists.

A pre-commit hook has a failure mode that looks exactly like success: a
`files:` pattern that matches nothing, or an `entry:` naming a command
that is not there, is a hook that never fails because it never runs.
This repo has already been bitten by that shape once - four subagent
files whose frontmatter had never parsed, caught only because somebody
counted files rather than parsing them (.pre-commit-config.yaml's own
comment on `mothman-check-agents`).

So these tests check the two things a hook cannot check about itself:
that the command it names is a real `mothman` command, and that its
file pattern matches something real in the repository today.
"""
from __future__ import annotations

import re
import shlex
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / ".pre-commit-config.yaml"


def _local_hooks() -> list[dict]:
    doc = yaml.safe_load(CONFIG.read_text())
    return [hook for repo in doc["repos"] if repo["repo"] == "local"
            for hook in repo["hooks"]]


def _tracked_files() -> list[str]:
    out = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True,
                          text=True, check=True)
    return out.stdout.splitlines()


def _mothman_paths() -> set[str]:
    """Every invocable `mothman ...` command path, from the real tree."""
    from click import Group

    from cli.app import cli

    paths = set()

    def walk(command, path):
        paths.add(path.strip())
        if isinstance(command, Group):
            for name, sub in command.commands.items():
                walk(sub, f"{path} {name}")

    walk(cli, "")
    return paths


@pytest.mark.parametrize("hook", _local_hooks(), ids=lambda h: h["id"])
class TestEveryLocalHookIsReal:
    def test_it_runs_a_command_that_exists(self, hook):
        parts = shlex.split(hook["entry"])
        assert parts[:3] == ["uv", "run", "mothman"], (
            f"{hook['id']} does not go through mothman: {hook['entry']!r}")
        words = [p for p in parts[3:] if not p.startswith("-")]
        # Options and their values trail the command path, so take the
        # longest leading run of words that names a real command.
        candidates = {" ".join(words[:n]) for n in range(1, len(words) + 1)}
        assert candidates & _mothman_paths(), (
            f"{hook['id']} names no real mothman command: {hook['entry']!r}")

    def test_its_file_pattern_matches_something_in_the_repository(self, hook):
        pattern = re.compile(hook["files"])
        matched = [f for f in _tracked_files() if pattern.search(f)]
        assert matched, (
            f"{hook['id']} matches no tracked file, so it never runs: "
            f"{hook['files']!r}")


class TestTheScheduleConfigIsGatedAtCommitTime:
    """Keith's own call, 2026-09-25: catch a calendar mistake at commit
    rather than after a push.

    It does NOT close post-build-review #19 and is not meant to - the
    harmful path there ends in a VALID configuration, so running the
    same validator sooner still passes. This gate is about the feedback
    loop, not the message.
    """

    def test_editing_the_asset_configuration_triggers_a_hook(self):
        covering = [h["id"] for h in _local_hooks()
                    if re.compile(h["files"]).search("contract/data-asset.yaml")]
        assert covering, (
            "nothing at commit time looks at contract/data-asset.yaml, where a "
            "one-character calendar name can leave a dataset expecting nothing")
