
import typer

from bot.cli.main import cli_output, run_async
from bot.database.base import db
from bot.database.repositories import ClientRepository
from bot.encryption import decrypt_token
from bot.hetzner.client import close_client, create_client

snapshot_app = typer.Typer(name="snapshots", help="Snapshot management commands")

CLIENT_ID_REQUIRED = "Client ID required. Use --client or set default."


def get_client_id(ctx: typer.Context, client: int | None) -> int:
    if client:
        return client
    if ctx.obj.get("client_id"):
        return ctx.obj["client_id"]
    raise typer.BadParameter(CLIENT_ID_REQUIRED)


@snapshot_app.command("list")
def snapshot_list(
    ctx: typer.Context,
    client: int | None = typer.Option(None, "--client", "-c", help="Client ID"),
):
    async def _list():
        client_id = get_client_id(ctx, client)
        async with db.session() as session:
            client_repo = ClientRepository(session)
            client_obj = await client_repo.get_by_id(client_id)
            token = decrypt_token(client_obj.api_token_encrypted)
            hetzner_client = await create_client(token)
            snapshots = await hetzner_client.list_snapshots()
            await close_client(hetzner_client)

        rows = [
            [
                str(s.id),
                s.name or s.description,
                s.status,
                f"{s.size / (1024**3):.1f} GB",
                s.server.get("name", "N/A") if s.server else "N/A",
            ]
            for s in snapshots
        ]
        cli_output.print_table("Snapshots", ["ID", "Name", "Status", "Size", "Server"], rows)

    run_async(_list())


@snapshot_app.command("get")
def snapshot_get(
    ctx: typer.Context,
    snapshot_id: int,
    client: int | None = typer.Option(None, "--client", "-c", help="Client ID"),
):
    async def _get():
        client_id = get_client_id(ctx, client)
        async with db.session() as session:
            client_repo = ClientRepository(session)
            client_obj = await client_repo.get_by_id(client_id)
            token = decrypt_token(client_obj.api_token_encrypted)
            hetzner_client = await create_client(token)
            snapshot = await hetzner_client.get_snapshot(snapshot_id)
            await close_client(hetzner_client)

        from bot.utils.formatters import format_snapshot_info

        cli_output.print_panel(f"Snapshot {snapshot.name or snapshot.description}", format_snapshot_info(snapshot))

    run_async(_get())


@snapshot_app.command("delete")
def snapshot_delete(
    ctx: typer.Context,
    snapshot_id: int,
    client: int | None = typer.Option(None, "--client", "-c", help="Client ID"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
):
    async def _delete():
        client_id = get_client_id(ctx, client)
        if not yes and not cli_output.confirm(f"Delete snapshot {snapshot_id}?"):
            cli_output.print_warning("Cancelled")
            return

        async with db.session() as session:
            client_repo = ClientRepository(session)
            client_obj = await client_repo.get_by_id(client_id)
            token = decrypt_token(client_obj.api_token_encrypted)
            hetzner_client = await create_client(token)

            try:
                await hetzner_client.delete_snapshot(snapshot_id)
                await close_client(hetzner_client)
                cli_output.print_success(f"Snapshot {snapshot_id} deleted")
            except Exception as e:
                await close_client(hetzner_client)
                cli_output.print_error(f"Deletion failed: {e}")

    run_async(_delete())


@snapshot_app.command("rename")
def snapshot_rename(
    ctx: typer.Context,
    snapshot_id: int,
    name: str = typer.Option(..., "--name", "-n", help="New name"),
    client: int | None = typer.Option(None, "--client", "-c", help="Client ID"),
):
    async def _rename():
        client_id = get_client_id(ctx, client)
        async with db.session() as session:
            client_repo = ClientRepository(session)
            client_obj = await client_repo.get_by_id(client_id)
            token = decrypt_token(client_obj.api_token_encrypted)
            hetzner_client = await create_client(token)

            try:
                await hetzner_client.change_snapshot_description(snapshot_id, name)
                await close_client(hetzner_client)
                cli_output.print_success(f"Snapshot {snapshot_id} renamed to {name}")
            except Exception as e:
                await close_client(hetzner_client)
                cli_output.print_error(f"Failed: {e}")

    run_async(_rename())
