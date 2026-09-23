
import typer

from bot.cli.main import cli_output, run_async
from bot.database.base import db
from bot.database.repositories import ClientRepository
from bot.encryption import decrypt_token
from bot.hetzner.client import close_client, create_client

placementgroup_app = typer.Typer(name="placement-groups", help="Placement Group management commands")

CLIENT_ID_REQUIRED = "Client ID required. Use --client or set default."


def get_client_id(ctx: typer.Context, client: int | None) -> int:
    if client:
        return client
    if ctx.obj.get("client_id"):
        return ctx.obj["client_id"]
    raise typer.BadParameter(CLIENT_ID_REQUIRED)


@placementgroup_app.command("list")
def placementgroup_list(
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
            pgs = await hetzner_client.list_placement_groups()
            await close_client(hetzner_client)

        rows = [[str(pg.id), pg.name, pg.type, str(len(pg.servers))] for pg in pgs]
        cli_output.print_table("Placement Groups", ["ID", "Name", "Type", "Servers"], rows)

    run_async(_list())


@placementgroup_app.command("get")
def placementgroup_get(
    ctx: typer.Context,
    pg_id: int,
    client: int | None = typer.Option(None, "--client", "-c", help="Client ID"),
):
    async def _get():
        client_id = get_client_id(ctx, client)
        async with db.session() as session:
            client_repo = ClientRepository(session)
            client_obj = await client_repo.get_by_id(client_id)
            token = decrypt_token(client_obj.api_token_encrypted)
            hetzner_client = await create_client(token)
            pg = await hetzner_client.get_placement_group(pg_id)
            await close_client(hetzner_client)

        from bot.utils.formatters import format_placement_group_info

        cli_output.print_panel(f"Placement Group {pg.name}", format_placement_group_info(pg))

    run_async(_get())


@placementgroup_app.command("create")
def placementgroup_create(
    ctx: typer.Context,
    name: str = typer.Option(..., "--name", "-n", help="Placement group name"),
    type: str = typer.Option("spread", "--type", "-t", help="Placement group type"),
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
                pg = await hetzner_client.create_placement_group(name, type)
                await close_client(hetzner_client)
                cli_output.print_success(f"Placement Group created: {pg.name} (ID: {pg.id})")
            except Exception as e:
                await close_client(hetzner_client)
                cli_output.print_error(f"Creation failed: {e}")

    run_async(_create())


@placementgroup_app.command("delete")
def placementgroup_delete(
    ctx: typer.Context,
    pg_id: int,
    client: int | None = typer.Option(None, "--client", "-c", help="Client ID"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
):
    async def _delete():
        client_id = get_client_id(ctx, client)
        if not yes and not cli_output.confirm(f"Delete placement group {pg_id}?"):
            cli_output.print_warning("Cancelled")
            return

        async with db.session() as session:
            client_repo = ClientRepository(session)
            client_obj = await client_repo.get_by_id(client_id)
            token = decrypt_token(client_obj.api_token_encrypted)
            hetzner_client = await create_client(token)

            try:
                await hetzner_client.delete_placement_group(pg_id)
                await close_client(hetzner_client)
                cli_output.print_success(f"Placement Group {pg_id} deleted")
            except Exception as e:
                await close_client(hetzner_client)
                cli_output.print_error(f"Deletion failed: {e}")

    run_async(_delete())


@placementgroup_app.command("rename")
def placementgroup_rename(
    ctx: typer.Context,
    pg_id: int,
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
                await hetzner_client.update_placement_group(pg_id, name=name)
                await close_client(hetzner_client)
                cli_output.print_success(f"Placement Group {pg_id} renamed to {name}")
            except Exception as e:
                await close_client(hetzner_client)
                cli_output.print_error(f"Failed: {e}")

    run_async(_rename())
