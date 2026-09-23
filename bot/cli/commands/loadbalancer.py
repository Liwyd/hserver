
import typer

from bot.cli.main import cli_output, run_async
from bot.database.base import db
from bot.database.repositories import ClientRepository
from bot.encryption import decrypt_token
from bot.hetzner.client import close_client, create_client

loadbalancer_app = typer.Typer(name="load-balancers", help="Load Balancer management commands")


def get_client_id(ctx: typer.Context, client: int | None) -> int:
    if client:
        return client
    if ctx.obj.get("client_id"):
        return ctx.obj["client_id"]
    raise typer.BadParameter("Client ID required. Use --client or set default.")


@loadbalancer_app.command("list")
def loadbalancer_list(
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
            lbs = await hetzner_client.list_load_balancers()
            await close_client(hetzner_client)

        rows = [
            [
                str(lb.id),
                lb.name,
                lb.load_balancer_type.get("name", "N/A"),
                lb.public_net.get("ipv4", {}).get("ip", "N/A"),
                lb.location.get("name", "N/A"),
                str(len(lb.targets)),
            ]
            for lb in lbs
        ]
        cli_output.print_table("Load Balancers", ["ID", "Name", "Type", "IP", "Location", "Targets"], rows)

    run_async(_list())


@loadbalancer_app.command("get")
def loadbalancer_get(
    ctx: typer.Context,
    lb_id: int,
    client: int | None = typer.Option(None, "--client", "-c", help="Client ID"),
):
    async def _get():
        client_id = get_client_id(ctx, client)
        async with db.session() as session:
            client_repo = ClientRepository(session)
            client_obj = await client_repo.get_by_id(client_id)
            token = decrypt_token(client_obj.api_token_encrypted)
            hetzner_client = await create_client(token)
            lb = await hetzner_client.get_load_balancer(lb_id)
            await close_client(hetzner_client)

        from bot.utils.formatters import format_load_balancer_info

        cli_output.print_panel(f"Load Balancer {lb.name}", format_load_balancer_info(lb))

    run_async(_get())


@loadbalancer_app.command("create")
def loadbalancer_create(
    ctx: typer.Context,
    name: str = typer.Option(..., "--name", "-n", help="Load balancer name"),
    type: str = typer.Option("lb11", "--type", "-t", help="Load balancer type"),
    location: str = typer.Option(..., "--location", "-l", help="Location"),
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
                lb = await hetzner_client.create_load_balancer(name, type, location)
                await close_client(hetzner_client)
                cli_output.print_success(f"Load Balancer created: {lb.name} (ID: {lb.id})")
            except Exception as e:
                await close_client(hetzner_client)
                cli_output.print_error(f"Creation failed: {e}")

    run_async(_create())


@loadbalancer_app.command("delete")
def loadbalancer_delete(
    ctx: typer.Context,
    lb_id: int,
    client: int | None = typer.Option(None, "--client", "-c", help="Client ID"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
):
    async def _delete():
        client_id = get_client_id(ctx, client)
        if not yes and not cli_output.confirm(f"Delete load balancer {lb_id}?"):
            cli_output.print_warning("Cancelled")
            return

        async with db.session() as session:
            client_repo = ClientRepository(session)
            client_obj = await client_repo.get_by_id(client_id)
            token = decrypt_token(client_obj.api_token_encrypted)
            hetzner_client = await create_client(token)

            try:
                await hetzner_client.delete_load_balancer(lb_id)
                await close_client(hetzner_client)
                cli_output.print_success(f"Load Balancer {lb_id} deleted")
            except Exception as e:
                await close_client(hetzner_client)
                cli_output.print_error(f"Deletion failed: {e}")

    run_async(_delete())


@loadbalancer_app.command("rename")
def loadbalancer_rename(
    ctx: typer.Context,
    lb_id: int,
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
                await hetzner_client.update_load_balancer(lb_id, name=name)
                await close_client(hetzner_client)
                cli_output.print_success(f"Load Balancer {lb_id} renamed to {name}")
            except Exception as e:
                await close_client(hetzner_client)
                cli_output.print_error(f"Failed: {e}")

    run_async(_rename())


@loadbalancer_app.command("add-target")
def loadbalancer_add_target(
    ctx: typer.Context,
    lb_id: int,
    server: int = typer.Option(..., "--server", "-s", help="Server ID"),
    client: int | None = typer.Option(None, "--client", "-c", help="Client ID"),
):
    async def _add_target():
        client_id = get_client_id(ctx, client)
        async with db.session() as session:
            client_repo = ClientRepository(session)
            client_obj = await client_repo.get_by_id(client_id)
            token = decrypt_token(client_obj.api_token_encrypted)
            hetzner_client = await create_client(token)

            try:
                await hetzner_client.add_load_balancer_target(lb_id, {"type": "server", "server": {"id": server}})
                await close_client(hetzner_client)
                cli_output.print_success(f"Target server {server} added to load balancer {lb_id}")
            except Exception as e:
                await close_client(hetzner_client)
                cli_output.print_error(f"Failed: {e}")

    run_async(_add_target())


@loadbalancer_app.command("remove-target")
def loadbalancer_remove_target(
    ctx: typer.Context,
    lb_id: int,
    server: int = typer.Option(..., "--server", "-s", help="Server ID"),
    client: int | None = typer.Option(None, "--client", "-c", help="Client ID"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
):
    async def _remove_target():
        client_id = get_client_id(ctx, client)
        if not yes and not cli_output.confirm(f"Remove target server {server} from load balancer {lb_id}?"):
            cli_output.print_warning("Cancelled")
            return

        async with db.session() as session:
            client_repo = ClientRepository(session)
            client_obj = await client_repo.get_by_id(client_id)
            token = decrypt_token(client_obj.api_token_encrypted)
            hetzner_client = await create_client(token)

            try:
                await hetzner_client.remove_load_balancer_target(lb_id, {"type": "server", "server": {"id": server}})
                await close_client(hetzner_client)
                cli_output.print_success(f"Target server {server} removed from load balancer {lb_id}")
            except Exception as e:
                await close_client(hetzner_client)
                cli_output.print_error(f"Failed: {e}")

    run_async(_remove_target())
