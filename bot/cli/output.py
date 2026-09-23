
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm
from rich.table import Table

console = Console()


class CLIOutput:
    def print_table(self, title: str, columns: list, rows: list):
        table = Table(title=title, show_header=True, header_style="bold cyan")
        for col in columns:
            table.add_column(col)
        for row in rows:
            table.add_row(*[str(cell) for cell in row])
        console.print(table)

    def print_panel(self, title: str, content: str, style: str = "white"):
        panel = Panel(content, title=title, border_style=style)
        console.print(panel)

    def print_success(self, msg: str):
        console.print(f"[green]✅ {msg}[/green]")

    def print_error(self, msg: str):
        console.print(f"[red]❌ {msg}[/red]")

    def print_warning(self, msg: str):
        console.print(f"[yellow]⚠️ {msg}[/yellow]")

    def print_info(self, msg: str):
        console.print(f"[blue]ℹ️ {msg}[/blue]")

    def confirm(self, prompt: str) -> bool:
        return Confirm.ask(f"[yellow]{prompt}[/yellow]")

    def spinner(self, text: str):
        return console.status(f"[bold green]{text}[/bold green]")

    def mask_token(self, token: str) -> str:
        if len(token) <= 12:
            return "*" * len(token)
        return token[:8] + "..." + token[-4:]
