
import typer

from bot.cli.main import cli_output, run_async
from bot.database.base import db
from bot.database.repositories import ClientRepository
from bot.encryption import decrypt_token
from bot.hetzner.client import close_client, create_client
from bot.hetzner.models import ServerCreateRequest

server_app = typer.Typer(name="servers", help="Server management commands")

CLIENT_ID_REQUIRED = "Client ID required. Use --client or set default."


def get_client_id(ctx: typer.Context, client: int | None) -> int:
    if client:
        return client
    if ctx.obj.get("client_id"):
        return ctx.obj["client_id"]
    raise typer.BadParameter(CLIENT_ID_REQUIRED)


@server_app.command("list")
def server_list(
    ctx: typer.Context,
    client: int | None = typer.Option(None, "--client", "-c", help="Client ID"),
):
    """List all servers"""

    async def _list():
        client_id = get_client_id(ctx, client)
        async with db.session() as session:
            client_repo = ClientRepository(session)
            client_obj = await client_repo.get_by_id(client_id)
            if not client_obj:
                cli_output.print_error("Client not found")
                return

            token = decrypt_token(client_obj.api_token_encrypted)
            hetzner_client = await create_client(token)
            servers = await hetzner_client.list_servers()
            await close_client(hetzner_client)

        rows = [
            [str(s.id), s.name, s.status, str(s.server_type.get("cores", 0)), str(s.server_type.get("memory", 0))]
            for s in servers
        ]
        cli_output.print_table("Servers", ["ID", "Name", "Status", "Cores", "RAM (GB)"], rows)

    run_async(_list())


@server_app.command("get")
def server_get(
    ctx: typer.Context,
    server_id: int,
    client: int | None = typer.Option(None, "--client", "-c", help="Client ID"),
):
    """Get server details"""

    async def _get():
        client_id = get_client_id(ctx, client)
        async with db.session() as session:
            client_repo = ClientRepository(session)
            client_obj = await client_repo.get_by_id(client_id)
            if not client_obj:
                cli_output.print_error("Client not found")
                return

            token = decrypt_token(client_obj.api_token_encrypted)
            hetzner_client = await create_client(token)
            server = await hetzner_client.get_server(server_id)
            await close_client(hetzner_client)

        from bot.utils.formatters import format_server_info

        cli_output.print_panel(f"Server {server.name}", format_server_info(server))

    run_async(_get())


@server_app.command("create")
def server_create(
    ctx: typer.Context,
    name: str = typer.Option(..., "--name", "-n", help="Server name"),
    datacenter: str = typer.Option(..., "--datacenter", "-d", help="Datacenter ID"),
    type: str = typer.Option(..., "--type", "-t", help="Server type"),
    image: str = typer.Option(..., "--image", "-i", help="Image ID"),
    client: int | None = typer.Option(None, "--client", "-c", help="Client ID"),
):
    """Create a server"""

    async def _create():
        client_id = get_client_id(ctx, client)
        async with db.session() as session:
            client_repo = ClientRepository(session)
            client_obj = await client_repo.get_by_id(client_id)
            if not client_obj:
                cli_output.print_error("Client not found")
                return

            token = decrypt_token(client_obj.api_token_encrypted)
            hetzner_client = await create_client(token)

            try:
                request = ServerCreateRequest(
                    name=name,
                    server_type=type,
                    image=image,
                    datacenter=datacenter,
                    start_after_create=True,
                )
                response = await hetzner_client.create_server(request)
                await close_client(hetzner_client)

                cli_output.print_success(f"Server created: {response.server.name} (ID: {response.server.id})")
            except Exception as e:
                await close_client(hetzner_client)
                cli_output.print_error(f"Creation failed: {e}")

    run_async(_create())


@server_app.command("delete")
def server_delete(
    ctx: typer.Context,
    server_id: int,
    client: int | None = typer.Option(None, "--client", "-c", help="Client ID"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
):
    """Delete a server"""

    async def _delete():
        client_id = get_client_id(ctx, client)

        if not yes and not cli_output.confirm(f"Delete server {server_id}?"):
            cli_output.print_warning("Cancelled")
            return

        async with db.session() as session:
            client_repo = ClientRepository(session)
            client_obj = await client_repo.get_by_id(client_id)
            if not client_obj:
                cli_output.print_error("Client not found")
                return

            token = decrypt_token(client_obj.api_token_encrypted)
            hetzner_client = await create_client(token)

            try:
                await hetzner_client.delete_server(server_id)
                await close_client(hetzner_client)
                cli_output.print_success(f"Server {server_id} deleted")
            except Exception as e:
                await close_client(hetzner_client)
                cli_output.print_error(f"Deletion failed: {e}")

    run_async(_delete())


@server_app.command("power-on")
def server_power_on(
    ctx: typer.Context,
    server_id: int,
    client: int | None = typer.Option(None, "--client", "-c", help="Client ID"),
):
    """Power on a server"""

    async def _power_on():
        client_id = get_client_id(ctx, client)
        async with db.session() as session:
            client_repo = ClientRepository(session)
            client_obj = await client_repo.get_by_id(client_id)
            token = decrypt_token(client_obj.api_token_encrypted)
            hetzner_client = await create_client(token)

            try:
                await hetzner_client.power_on(server_id)
                await close_client(hetzner_client)
                cli_output.print_success(f"Server {server_id} powered on")
            except Exception as e:
                await close_client(hetzner_client)
                cli_output.print_error(f"Failed: {e}")

    run_async(_power_on())


@server_app.command("power-off")
def server_power_off(
    ctx: typer.Context,
    server_id: int,
    client: int | None = typer.Option(None, "--client", "-c", help="Client ID"),
):
    """Power off a server"""

    async def _power_off():
        client_id = get_client_id(ctx, client)
        async with db.session() as session:
            client_repo = ClientRepository(session)
            client_obj = await client_repo.get_by_id(client_id)
            token = decrypt_token(client_obj.api_token_encrypted)
            hetzner_client = await create_client(token)

            try:
                await hetzner_client.power_off(server_id)
                await close_client(hetzner_client)
                cli_output.print_success(f"Server {server_id} powered off")
            except Exception as e:
                await close_client(hetzner_client)
                cli_output.print_error(f"Failed: {e}")

    run_async(_power_off())


@server_app.command("reboot")
def server_reboot(
    ctx: typer.Context,
    server_id: int,
    client: int | None = typer.Option(None, "--client", "-c", help="Client ID"),
):
    """Reboot a server"""

    async def _reboot():
        client_id = get_client_id(ctx, client)
        async with db.session() as session:
            client_repo = ClientRepository(session)
            client_obj = await client_repo.get_by_id(client_id)
            token = decrypt_token(client_obj.api_token_encrypted)
            hetzner_client = await create_client(token)

            try:
                await hetzner_client.reboot(server_id)
                await close_client(hetzner_client)
                cli_output.print_success(f"Server {server_id} rebooted")
            except Exception as e:
                await close_client(hetzner_client)
                cli_output.print_error(f"Failed: {e}")

    run_async(_reboot())


@server_app.command("reset")
def server_reset(
    ctx: typer.Context,
    server_id: int,
    client: int | None = typer.Option(None, "--client", "-c", help="Client ID"),
):
    """Reset a server"""

    async def _reset():
        client_id = get_client_id(ctx, client)
        async with db.session() as session:
            client_repo = ClientRepository(session)
            client_obj = await client_repo.get_by_id(client_id)
            token = decrypt_token(client_obj.api_token_encrypted)
            hetzner_client = await create_client(token)

            try:
                await hetzner_client.reset(server_id)
                await close_client(hetzner_client)
                cli_output.print_success(f"Server {server_id} reset")
            except Exception as e:
                await close_client(hetzner_client)
                cli_output.print_error(f"Failed: {e}")

    run_async(_reset())


@server_app.command("rebuild")
def server_rebuild(
    ctx: typer.Context,
    server_id: int,
    image: str = typer.Option(..., "--image", "-i", help="Image ID"),
    client: int | None = typer.Option(None, "--client", "-c", help="Client ID"),
):
    """Rebuild a server with a new image"""

    async def _rebuild():
        client_id = get_client_id(ctx, client)
        async with db.session() as session:
            client_repo = ClientRepository(session)
            client_obj = await client_repo.get_by_id(client_id)
            token = decrypt_token(client_obj.api_token_encrypted)
            hetzner_client = await create_client(token)

            try:
                await hetzner_client.rebuild(server_id, image)
                await close_client(hetzner_client)
                cli_output.print_success(f"Server {server_id} rebuild initiated")
            except Exception as e:
                await close_client(hetzner_client)
                cli_output.print_error(f"Failed: {e}")

    run_async(_rebuild())


@server_app.command("reset-password")
def server_reset_password(
    ctx: typer.Context,
    server_id: int,
    client: int | None = typer.Option(None, "--client", "-c", help="Client ID"),
):
    """Reset server root password"""

    async def _reset_password():
        client_id = get_client_id(ctx, client)
        async with db.session() as session:
            client_repo = ClientRepository(session)
            client_obj = await client_repo.get_by_id(client_id)
            token = decrypt_token(client_obj.api_token_encrypted)
            hetzner_client = await create_client(token)

            try:
                result = await hetzner_client.reset_password(server_id)
                await close_client(hetzner_client)
                password = result.get("root_password", "N/A")
                cli_output.print_success(f"New root password: {password}")
            except Exception as e:
                await close_client(hetzner_client)
                cli_output.print_error(f"Failed: {e}")

    run_async(_reset_password())


@server_app.command("upgrade")
def server_upgrade(
    ctx: typer.Context,
    server_id: int,
    type: str = typer.Option(..., "--type", "-t", help="New server type"),
    client: int | None = typer.Option(None, "--client", "-c", help="Client ID"),
):
    """Upgrade a server"""

    async def _upgrade():
        client_id = get_client_id(ctx, client)
        async with db.session() as session:
            client_repo = ClientRepository(session)
            client_obj = await client_repo.get_by_id(client_id)
            token = decrypt_token(client_obj.api_token_encrypted)
            hetzner_client = await create_client(token)

            try:
                await hetzner_client.upgrade(server_id, type)
                await close_client(hetzner_client)
                cli_output.print_success(f"Server {server_id} upgrade initiated")
            except Exception as e:
                await close_client(hetzner_client)
                cli_output.print_error(f"Failed: {e}")

    run_async(_upgrade())


@server_app.command("rename")
def server_rename(
    ctx: typer.Context,
    server_id: int,
    name: str = typer.Option(..., "--name", "-n", help="New name"),
    client: int | None = typer.Option(None, "--client", "-c", help="Client ID"),
):
    """Rename a server"""

    async def _rename():
        client_id = get_client_id(ctx, client)
        async with db.session() as session:
            client_repo = ClientRepository(session)
            client_obj = await client_repo.get_by_id(client_id)
            token = decrypt_token(client_obj.api_token_encrypted)
            hetzner_client = await create_client(token)

            try:
                await hetzner_client.change_server_alias(server_id, name)
                await close_client(hetzner_client)
                cli_output.print_success(f"Server {server_id} renamed to {name}")
            except Exception as e:
                await close_client(hetzner_client)
                cli_output.print_error(f"Failed: {e}")

    run_async(_rename())


@server_app.command("snapshots")
def server_snapshots(
    ctx: typer.Context,
    server_id: int,
    client: int | None = typer.Option(None, "--client", "-c", help="Client ID"),
):
    """List snapshots for a server"""

    async def _snapshots():
        client_id = get_client_id(ctx, client)
        async with db.session() as session:
            client_repo = ClientRepository(session)
            client_obj = await client_repo.get_by_id(client_id)
            token = decrypt_token(client_obj.api_token_encrypted)
            hetzner_client = await create_client(token)

            try:
                snapshots = await hetzner_client.list_snapshots()
                server_snapshots = [s for s in snapshots if s.server and s.server.get("id") == server_id]
                await close_client(hetzner_client)

                rows = [
                    [str(s.id), s.name or s.description, s.status, f"{s.size / (1024**3):.1f} GB"]
                    for s in server_snapshots
                ]
                cli_output.print_table(f"Snapshots for Server {server_id}", ["ID", "Name", "Status", "Size"], rows)
            except Exception as e:
                await close_client(hetzner_client)
                cli_output.print_error(f"Failed: {e}")

    run_async(_snapshots())


@server_app.command("console")
def server_console(
    ctx: typer.Context,
    server_id: int,
    client: int | None = typer.Option(None, "--client", "-c", help="Client ID"),
):
    """Open web console URL"""

    async def _console():
        client_id = get_client_id(ctx, client)
        async with db.session() as session:
            client_repo = ClientRepository(session)
            client_obj = await client_repo.get_by_id(client_id)
            token = decrypt_token(client_obj.api_token_encrypted)
            hetzner_client = await create_client(token)

            try:
                console = await hetzner_client.get_server_console(server_id)
                await close_client(hetzner_client)
                cli_output.print_success(f"Console URL: {console.url}")
            except Exception as e:
                await close_client(hetzner_client)
                cli_output.print_error(f"Failed: {e}")

    run_async(_console())
