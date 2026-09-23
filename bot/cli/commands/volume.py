
import typer

from bot.cli.main import cli_output, run_async
from bot.database.base import db
from bot.database.repositories import ClientRepository
from bot.encryption import decrypt_token
from bot.hetzner.client import close_client, create_client

volume_app = typer.Typer(name="volumes", help="Volume management commands")


def get_client_id(ctx: typer.Context, client: int | None) -> int:
    if client:
        return client
    if ctx.obj.get("client_id"):
        return ctx.obj["client_id"]
    raise typer.BadParameter("Client ID required. Use --client or set default.")


@volume_app.command("list")
def volume_list(
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
            volumes = await hetzner_client.list_volumes()
            await close_client(hetzner_client)

        rows = [
            [str(v.id), v.name, f"{v.size} GB", v.location, v.server.get("name", "N/A") if v.server else "Not attached"]
            for v in volumes
        ]
        cli_output.print_table("Volumes", ["ID", "Name", "Size", "Location", "Server"], rows)

    run_async(_list())


@volume_app.command("get")
def volume_get(
    ctx: typer.Context,
    volume_id: int,
    client: int | None = typer.Option(None, "--client", "-c", help="Client ID"),
):
    async def _get():
        client_id = get_client_id(ctx, client)
        async with db.session() as session:
            client_repo = ClientRepository(session)
            client_obj = await client_repo.get_by_id(client_id)
            token = decrypt_token(client_obj.api_token_encrypted)
            hetzner_client = await create_client(token)
            volume = await hetzner_client.get_volume(volume_id)
            await close_client(hetzner_client)

        from bot.utils.formatters import format_volume_info

        cli_output.print_panel(f"Volume {volume.name}", format_volume_info(volume))

    run_async(_get())


@volume_app.command("create")
def volume_create(
    ctx: typer.Context,
    name: str = typer.Option(..., "--name", "-n", help="Volume name"),
    size: int = typer.Option(..., "--size", "-s", help="Size in GB"),
    location: str = typer.Option(..., "--location", "-l", help="Location"),
    server: int | None = typer.Option(None, "--server", help="Server ID to attach"),
    client: int | None = typer.Option(None, "--client", "-c", help="Client ID"),
):
    async def _create():
        client_id = get_client_id(ctx, client)
        async with db.session() as session:
            client_repo = ClientRepository(session)
            client_obj = await client_repo.get_by_id(client_id)
            token = decrypt_token(client_obj.api_token_encrypted)
            hetzner_client = await create_client(token)

            try:
                volume = await hetzner_client.create_volume(name, size, location, server)
                await close_client(hetzner_client)
                cli_output.print_success(f"Volume created: {volume.name} (ID: {volume.id})")
            except Exception as e:
                await close_client(hetzner_client)
                cli_output.print_error(f"Creation failed: {e}")

    run_async(_create())


@volume_app.command("delete")
def volume_delete(
    ctx: typer.Context,
    volume_id: int,
    client: int | None = typer.Option(None, "--client", "-c", help="Client ID"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
):
    async def _delete():
        client_id = get_client_id(ctx, client)
        if not yes and not cli_output.confirm(f"Delete volume {volume_id}?"):
            cli_output.print_warning("Cancelled")
            return

        async with db.session() as session:
            client_repo = ClientRepository(session)
            client_obj = await client_repo.get_by_id(client_id)
            token = decrypt_token(client_obj.api_token_encrypted)
            hetzner_client = await create_client(token)

            try:
                await hetzner_client.delete_volume(volume_id)
                await close_client(hetzner_client)
                cli_output.print_success(f"Volume {volume_id} deleted")
            except Exception as e:
                await close_client(hetzner_client)
                cli_output.print_error(f"Deletion failed: {e}")

    run_async(_delete())


@volume_app.command("resize")
def volume_resize(
    ctx: typer.Context,
    volume_id: int,
    size: int = typer.Option(..., "--size", "-s", help="New size in GB"),
    client: int | None = typer.Option(None, "--client", "-c", help="Client ID"),
):
    async def _resize():
        client_id = get_client_id(ctx, client)
        async with db.session() as session:
            client_repo = ClientRepository(session)
            client_obj = await client_repo.get_by_id(client_id)
            token = decrypt_token(client_obj.api_token_encrypted)
            hetzner_client = await create_client(token)

            try:
                await hetzner_client.resize_volume(volume_id, size)
                await close_client(hetzner_client)
                cli_output.print_success(f"Volume {volume_id} resized to {size} GB")
            except Exception as e:
                await close_client(hetzner_client)
                cli_output.print_error(f"Resize failed: {e}")

    run_async(_resize())


@volume_app.command("attach")
def volume_attach(
    ctx: typer.Context,
    volume_id: int,
    server: int = typer.Option(..., "--server", "-s", help="Server ID"),
    client: int | None = typer.Option(None, "--client", "-c", help="Client ID"),
):
    async def _attach():
        client_id = get_client_id(ctx, client)
        async with db.session() as session:
            client_repo = ClientRepository(session)
            client_obj = await client_repo.get_by_id(client_id)
            token = decrypt_token(client_obj.api_token_encrypted)
            hetzner_client = await create_client(token)

            try:
                await hetzner_client.attach_volume(volume_id, server)
                await close_client(hetzner_client)
                cli_output.print_success(f"Volume {volume_id} attached to server {server}")
            except Exception as e:
                await close_client(hetzner_client)
                cli_output.print_error(f"Attach failed: {e}")

    run_async(_attach())


@volume_app.command("detach")
def volume_detach(
    ctx: typer.Context,
    volume_id: int,
    client: int | None = typer.Option(None, "--client", "-c", help="Client ID"),
):
    async def _detach():
        client_id = get_client_id(ctx, client)
        async with db.session() as session:
            client_repo = ClientRepository(session)
            client_obj = await client_repo.get_by_id(client_id)
            token = decrypt_token(client_obj.api_token_encrypted)
            hetzner_client = await create_client(token)

            try:
                await hetzner_client.detach_volume(volume_id)
                await close_client(hetzner_client)
                cli_output.print_success(f"Volume {volume_id} detached")
            except Exception as e:
                await close_client(hetzner_client)
                cli_output.print_error(f"Detach failed: {e}")

    run_async(_detach())


@volume_app.command("rename")
def volume_rename(
    ctx: typer.Context,
    volume_id: int,
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
                await hetzner_client.update_volume(volume_id, name=name)
                await close_client(hetzner_client)
                cli_output.print_success(f"Volume {volume_id} renamed to {name}")
            except Exception as e:
                await close_client(hetzner_client)
                cli_output.print_error(f"Failed: {e}")

    run_async(_rename())
