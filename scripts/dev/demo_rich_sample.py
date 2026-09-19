"""Dev-only: a small colorful rich rendering, used purely to prove
scripts/dev/tui_screenshot.py's capture pipeline end to end before the
mothman CLI itself exists. Not part of the shipped pipeline/CLI."""
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()

console.print(Panel("[bold]MOTHMAN[/bold] - QA CLI prep: screenshot pipeline check",
                     style="bold magenta", border_style="cyan"))

table = Table(title="Sample dataset status")
table.add_column("Dataset", style="cyan")
table.add_column("Status", style="bold")
table.add_column("Checks", justify="right", style="green")

table.add_row("Birth Registrations", "[green]green[/green]", "212/212")
table.add_row("Child Protection", "[yellow]amber[/yellow]", "198/204")

console.print(table)
