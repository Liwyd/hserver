
import typer

from bot.cli.main import cli_output, run_async
from bot.database.base import db
from bot.database.repositories import ClientRepository
from bot.encryption import decrypt_token
from bot.hetzner.client import close_client, create_client

bot_app = typer.Typer(name="bot", help="Bot management commands")


@bot_app.command("status")
def bot_status(ctx: typer.Context):
    """Show connection status, list all clients, show resource counts"""

    async def _status():
        async with db.session() as session:
            client_repo = ClientRepository(session)
            clients = await client_repo.list_all()

            cli_output.print_table(
                "Registered Clients",
                ["ID", "Remark", "Token"],
                [[str(c.id), c.remark, cli_output.mask_token(decrypt_token(c.api_token_encrypted))] for c in clients],
            )

            cli_output.print_success("Connection: OK")

            for client in clients:
                token = decrypt_token(client.api_token_encrypted)
                hetzner_client = await create_client(token)

                try:
                    servers = await hetzner_client.list_servers()
                    primary_ips = await hetzner_client.list_primary_ips()
                    volumes = await hetzner_client.list_volumes()
                    networks = await hetzner_client.list_networks()
                    ssh_keys = await hetzner_client.list_ssh_keys()

                    cli_output.print_panel(
                        f"Account Summary - {client.remark}",
                        f"Servers: {len(servers)} | Primary IPs: {len(primary_ips)} | Volumes: {len(volumes)} | Networks: {len(networks)} | SSH Keys: {len(ssh_keys)}",
                    )
                except Exception:
                    cli_output.print_error(f"Failed to connect to {client.remark}")
                finally:
                    await close_client(hetzner_client)

    run_async(_status())


@bot_app.command("update")
def bot_update():
    """Update the bot (pulls latest, rebuilds Docker, runs migrations)"""
    cli_output.print_info("Update functionality runs via the update.sh script")
    cli_output.print_info("Run: sudo /opt/servermanagerbot/scripts/update.sh")


@bot_app.command("restart")
def bot_restart():
    """Restart bot services"""
    cli_output.print_info("Restart functionality runs via Docker Compose")
    cli_output.print_info("Run: docker compose -f /opt/servermanagerbot/docker/docker-compose.yml restart")


@bot_app.command("stop")
def bot_stop():
    """Stop bot services"""
    cli_output.print_info("Stop functionality runs via Docker Compose")
    cli_output.print_info("Run: docker compose -f /opt/servermanagerbot/docker/docker-compose.yml stop")


@bot_app.command("start")
def bot_start():
    """Start bot services"""
    cli_output.print_info("Start functionality runs via Docker Compose")
    cli_output.print_info("Run: docker compose -f /opt/servermanagerbot/docker/docker-compose.yml start")


@bot_app.command("logs")
def bot_logs(
    follow: bool = typer.Option(False, "-f", "--follow", help="Follow logs"),
    lines: int = typer.Option(100, "-n", "--lines", help="Number of lines"),
):
    """Follow logs"""
    cli_output.print_info("Logs functionality runs via Docker Compose")
    cli_output.print_info(
        f"Run: docker compose -f /opt/servermanagerbot/docker/docker-compose.yml logs {'-f' if follow else ''} --tail={lines}"
    )


@bot_app.command("install")
def bot_install():
    """Install the bot from scratch"""
    cli_output.print_info("Install functionality runs via the install.sh script")
    cli_output.print_info("Run: sudo /opt/servermanagerbot/scripts/install.sh")


@bot_app.command("uninstall")
def bot_uninstall(
    confirm: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
):
    """Remove the bot"""
    cli_output.print_info("Uninstall functionality runs via the uninstall.sh script")
    cli_output.print_info("Run: sudo /opt/servermanagerbot/scripts/uninstall.sh")
