
import typer

from bot.cli.main import cli_output, run_async
from bot.database.base import db
from bot.database.repositories import ClientRepository
from bot.encryption import decrypt_token
from bot.hetzner.client import close_client, create_client

firewall_app = typer.Typer(name="firewalls", help="Firewall management commands")


def get_client_id(ctx: typer.Context, client: int | None) -> int:
    if client:
        return client
    if ctx.obj.get("client_id"):
        return ctx.obj["client_id"]
    raise typer.BadParameter("Client ID required. Use --client or set default.")


@firewall_app.command("list")
def firewall_list(
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
            firewalls = await hetzner_client.list_firewalls()
            await close_client(hetzner_client)

        rows = [[str(f.id), f.name, str(len(f.rules)), str(len(f.applied_to))] for f in firewalls]
        cli_output.print_table("Firewalls", ["ID", "Name", "Rules", "Applied To"], rows)

    run_async(_list())


@firewall_app.command("get")
def firewall_get(
    ctx: typer.Context,
    firewall_id: int,
    client: int | None = typer.Option(None, "--client", "-c", help="Client ID"),
):
    async def _get():
        client_id = get_client_id(ctx, client)
        async with db.session() as session:
            client_repo = ClientRepository(session)
            client_obj = await client_repo.get_by_id(client_id)
            token = decrypt_token(client_obj.api_token_encrypted)
            hetzner_client = await create_client(token)
            firewall = await hetzner_client.get_firewall(firewall_id)
            await close_client(hetzner_client)

        from bot.utils.formatters import format_firewall_info

        cli_output.print_panel(f"Firewall {firewall.name}", format_firewall_info(firewall))

    run_async(_get())


@firewall_app.command("create")
def firewall_create(
    ctx: typer.Context,
    name: str = typer.Option(..., "--name", "-n", help="Firewall name"),
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
                firewall = await hetzner_client.create_firewall(name)
                await close_client(hetzner_client)
                cli_output.print_success(f"Firewall created: {firewall.name} (ID: {firewall.id})")
            except Exception as e:
                await close_client(hetzner_client)
                cli_output.print_error(f"Creation failed: {e}")

    run_async(_create())


@firewall_app.command("delete")
def firewall_delete(
    ctx: typer.Context,
    firewall_id: int,
    client: int | None = typer.Option(None, "--client", "-c", help="Client ID"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
):
    async def _delete():
        client_id = get_client_id(ctx, client)
        if not yes and not cli_output.confirm(f"Delete firewall {firewall_id}?"):
            cli_output.print_warning("Cancelled")
            return

        async with db.session() as session:
            client_repo = ClientRepository(session)
            client_obj = await client_repo.get_by_id(client_id)
            token = decrypt_token(client_obj.api_token_encrypted)
            hetzner_client = await create_client(token)

            try:
                await hetzner_client.delete_firewall(firewall_id)
                await close_client(hetzner_client)
                cli_output.print_success(f"Firewall {firewall_id} deleted")
            except Exception as e:
                await close_client(hetzner_client)
                cli_output.print_error(f"Deletion failed: {e}")

    run_async(_delete())


@firewall_app.command("rename")
def firewall_rename(
    ctx: typer.Context,
    firewall_id: int,
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
                await hetzner_client.update_firewall(firewall_id, name=name)
                await close_client(hetzner_client)
                cli_output.print_success(f"Firewall {firewall_id} renamed to {name}")
            except Exception as e:
                await close_client(hetzner_client)
                cli_output.print_error(f"Failed: {e}")

    run_async(_rename())


@firewall_app.command("apply")
def firewall_apply(
    ctx: typer.Context,
    firewall_id: int,
    server: int = typer.Option(..., "--server", "-s", help="Server ID"),
    client: int | None = typer.Option(None, "--client", "-c", help="Client ID"),
):
    async def _apply():
        client_id = get_client_id(ctx, client)
        async with db.session() as session:
            client_repo = ClientRepository(session)
            client_obj = await client_repo.get_by_id(client_id)
            token = decrypt_token(client_obj.api_token_encrypted)
            hetzner_client = await create_client(token)

            try:
                await hetzner_client.apply_firewall_to_resources(firewall_id, [{"server": {"id": server}}])
                await close_client(hetzner_client)
                cli_output.print_success(f"Firewall {firewall_id} applied to server {server}")
            except Exception as e:
                await close_client(hetzner_client)
                cli_output.print_error(f"Failed: {e}")

    run_async(_apply())


@firewall_app.command("remove")
def firewall_remove(
    ctx: typer.Context,
    firewall_id: int,
    server: int = typer.Option(..., "--server", "-s", help="Server ID"),
    client: int | None = typer.Option(None, "--client", "-c", help="Client ID"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
):
    async def _remove():
        client_id = get_client_id(ctx, client)
        if not yes and not cli_output.confirm(f"Remove firewall {firewall_id} from server {server}?"):
            cli_output.print_warning("Cancelled")
            return

        async with db.session() as session:
            client_repo = ClientRepository(session)
            client_obj = await client_repo.get_by_id(client_id)
            token = decrypt_token(client_obj.api_token_encrypted)
            hetzner_client = await create_client(token)

            try:
                await hetzner_client.remove_firewall_from_resources(firewall_id, [{"server": {"id": server}}])
                await close_client(hetzner_client)
                cli_output.print_success(f"Firewall {firewall_id} removed from server {server}")
            except Exception as e:
                await close_client(hetzner_client)
                cli_output.print_error(f"Failed: {e}")

    run_async(_remove())
