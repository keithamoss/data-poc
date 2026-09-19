"""mothman github - GitHub workflow/people automation, Tier 2 (plans/
tooling.md #1 Phase 4's own "GitHub workflow/people automation" group).
Every command here calls the real, unmodified main() each retired
bare-script invocation already called - GITHUB_REPOSITORY/GH_TOKEN come
from the real environment (GitHub Actions sets both automatically; a
human running these locally needs gh authenticated and
GITHUB_REPOSITORY set themselves, same as before this reorg)."""
from __future__ import annotations

import rich_click as click


@click.group("github")
def github_group() -> None:
    """GitHub workflow/people automation - Tier 2 (CI/automation)."""


@github_group.command("sync-tickets")
def sync_tickets_command() -> None:
    """Open/comment-and-close a real GitHub Issue per dataset, keyed off its current aggregate QA status."""
    from qa_tools.common.ticket_sync import main as sync_main
    sync_main()


@github_group.command("sync-acceptances")
def sync_acceptances_command() -> None:
    """Fetch every real qa-ticket issue's own comments (for /accept matching) - prints JSON to stdout."""
    from qa_tools.common.acceptance_sync import main as sync_main
    sync_main()


@github_group.command("sync-leaderboard")
def sync_leaderboard_command() -> None:
    """Fetch every real qa-ticket issue's own closed/reopened history (for the leaderboard) - prints JSON to stdout."""
    from qa_tools.common.leaderboard import main as sync_main
    sync_main()
