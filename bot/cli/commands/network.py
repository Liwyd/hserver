
import typer

from bot.cli.main import cli_output, run_async
from bot.database.base import db
from bot.database.repositories import ClientRepository
from bot.encryption import decrypt_token
from bot.hetzner.client import close_client, create_client

network_app = typer.Typer(name="networks", help="Network management commands")


def get_client_id(ctx: typer.Context, client: int | None) -> int:
    if client:
        return client
    if ctx.obj.get("client_id"):
        return ctx.obj["client_id"]
    raise typer.BadParameter("Client ID required. Use --client or set default.")


@network_app.command("list")
def network_list(
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
            networks = await hetzner_client.list_networks()
            await close_client(hetzner_client)

        rows = [[str(n.id), n.name, n.ip_range, str(len(n.subnets)), str(len(n.routes))] for n in networks]
        cli_output.print_table("Networks", ["ID", "Name", "IP Range", "Subnets", "Routes"], rows)

    run_async(_list())


@network_app.command("get")
def network_get(
    ctx: typer.Context,
    network_id: int,
    client: int | None = typer.Option(None, "--client", "-c", help="Client ID"),
):
    async def _get():
        client_id = get_client_id(ctx, client)
        async with db.session() as session:
            client_repo = ClientRepository(session)
            client_obj = await client_repo.get_by_id(client_id)
            token = decrypt_token(client_obj.api_token_encrypted)
            hetzner_client = await create_client(token)
            network = await hetzner_client.get_network(network_id)
            await close_client(hetzner_client)

        from bot.utils.formatters import format_network_info

        cli_output.print_panel(f"Network {network.name}", format_network_info(network))

    run_async(_get())


@network_app.command("create")
def network_create(
    ctx: typer.Context,
    name: str = typer.Option(..., "--name", "-n", help="Network name"),
    ip_range: str = typer.Option(..., "--ip-range", "-r", help="IP range (CIDR)"),
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
                network = await hetzner_client.create_network(name, ip_range)
                await close_client(hetzner_client)
                cli_output.print_success(f"Network created: {network.name} (ID: {network.id})")
            except Exception as e:
                await close_client(hetzner_client)
                cli_output.print_error(f"Creation failed: {e}")

    run_async(_create())


@network_app.command("delete")
def network_delete(
    ctx: typer.Context,
    network_id: int,
    client: int | None = typer.Option(None, "--client", "-c", help="Client ID"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
):
    async def _delete():
        client_id = get_client_id(ctx, client)
        if not yes and not cli_output.confirm(f"Delete network {network_id}?"):
            cli_output.print_warning("Cancelled")
            return

        async with db.session() as session:
            client_repo = ClientRepository(session)
            client_obj = await client_repo.get_by_id(client_id)
            token = decrypt_token(client_obj.api_token_encrypted)
            hetzner_client = await create_client(token)

            try:
                await hetzner_client.delete_network(network_id)
                await close_client(hetzner_client)
                cli_output.print_success(f"Network {network_id} deleted")
            except Exception as e:
                await close_client(hetzner_client)
                cli_output.print_error(f"Deletion failed: {e}")

    run_async(_delete())


@network_app.command("rename")
def network_rename(
    ctx: typer.Context,
    network_id: int,
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
                await hetzner_client.update_network(network_id, name=name)
                await close_client(hetzner_client)
                cli_output.print_success(f"Network {network_id} renamed to {name}")
            except Exception as e:
                await close_client(hetzner_client)
                cli_output.print_error(f"Failed: {e}")

    run_async(_rename())


@network_app.command("add-subnet")
def network_add_subnet(
    ctx: typer.Context,
    network_id: int,
    ip_range: str = typer.Option(..., "--ip-range", "-r", help="Subnet IP range (CIDR)"),
    type: str = typer.Option(..., "--type", "-t", help="Subnet type (cloud/vswitch)"),
    client: int | None = typer.Option(None, "--client", "-c", help="Client ID"),
):
    async def _add_subnet():
        client_id = get_client_id(ctx, client)
        async with db.session() as session:
            client_repo = ClientRepository(session)
            client_obj = await client_repo.get_by_id(client_id)
            token = decrypt_token(client_obj.api_token_encrypted)
            hetzner_client = await create_client(token)

            try:
                await hetzner_client.add_subnet(network_id, ip_range, "eu-central", type)
                await close_client(hetzner_client)
                cli_output.print_success(f"Subnet {ip_range} added to network {network_id}")
            except Exception as e:
                await close_client(hetzner_client)
                cli_output.print_error(f"Failed: {e}")

    run_async(_add_subnet())


@network_app.command("remove-subnet")
def network_remove_subnet(
    ctx: typer.Context,
    network_id: int,
    ip_range: str = typer.Option(..., "--ip-range", "-r", help="Subnet IP range (CIDR)"),
    client: int | None = typer.Option(None, "--client", "-c", help="Client ID"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
):
    async def _remove_subnet():
        client_id = get_client_id(ctx, client)
        if not yes and not cli_output.confirm(f"Remove subnet {ip_range} from network {network_id}?"):
            cli_output.print_warning("Cancelled")
            return

        async with db.session() as session:
            client_repo = ClientRepository(session)
            client_obj = await client_repo.get_by_id(client_id)
            token = decrypt_token(client_obj.api_token_encrypted)
            hetzner_client = await create_client(token)

            try:
                await hetzner_client.delete_subnet(network_id, ip_range)
                await close_client(hetzner_client)
                cli_output.print_success(f"Subnet {ip_range} removed from network {network_id}")
            except Exception as e:
                await close_client(hetzner_client)
                cli_output.print_error(f"Failed: {e}")

    run_async(_remove_subnet())


@network_app.command("add-route")
def network_add_route(
    ctx: typer.Context,
    network_id: int,
    destination: str = typer.Option(..., "--destination", "-d", help="Destination CIDR"),
    gateway: str = typer.Option(..., "--gateway", "-g", help="Gateway IP"),
    client: int | None = typer.Option(None, "--client", "-c", help="Client ID"),
):
    async def _add_route():
        client_id = get_client_id(ctx, client)
        async with db.session() as session:
            client_repo = ClientRepository(session)
            client_obj = await client_repo.get_by_id(client_id)
            token = decrypt_token(client_obj.api_token_encrypted)
            hetzner_client = await create_client(token)

            try:
                await hetzner_client.add_route(network_id, destination, gateway)
                await close_client(hetzner_client)
                cli_output.print_success(f"Route {destination} -> {gateway} added to network {network_id}")
            except Exception as e:
                await close_client(hetzner_client)
                cli_output.print_error(f"Failed: {e}")

    run_async(_add_route())


@network_app.command("remove-route")
def network_remove_route(
    ctx: typer.Context,
    network_id: int,
    destination: str = typer.Option(..., "--destination", "-d", help="Destination CIDR"),
    gateway: str = typer.Option(..., "--gateway", "-g", help="Gateway IP"),
    client: int | None = typer.Option(None, "--client", "-c", help="Client ID"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
):
    async def _remove_route():
        client_id = get_client_id(ctx, client)
        if not yes and not cli_output.confirm(f"Remove route {destination} -> {gateway} from network {network_id}?"):
            cli_output.print_warning("Cancelled")
            return

        async with db.session() as session:
            client_repo = ClientRepository(session)
            client_obj = await client_repo.get_by_id(client_id)
            token = decrypt_token(client_obj.api_token_encrypted)
            hetzner_client = await create_client(token)

            try:
                await hetzner_client.delete_route(network_id, destination, gateway)
                await close_client(hetzner_client)
                cli_output.print_success(f"Route {destination} -> {gateway} removed from network {network_id}")
            except Exception as e:
                await close_client(hetzner_client)
                cli_output.print_error(f"Failed: {e}")

    run_async(_remove_route())
