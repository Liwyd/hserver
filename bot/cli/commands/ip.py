
import typer

from bot.cli.main import cli_output, run_async
from bot.database.base import db
from bot.database.repositories import ClientRepository
from bot.encryption import decrypt_token
from bot.hetzner.client import close_client, create_client

primary_ip_app = typer.Typer(name="primary-ips", help="Primary IP management commands")
floating_ip_app = typer.Typer(name="floating-ips", help="Floating IP management commands")


def get_client_id(ctx: typer.Context, client: int | None) -> int:
    if client:
        return client
    if ctx.obj.get("client_id"):
        return ctx.obj["client_id"]
    raise typer.BadParameter("Client ID required. Use --client or set default.")


# Primary IPs
@primary_ip_app.command("list")
def primary_ip_list(
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
            ips = await hetzner_client.list_primary_ips()
            await close_client(hetzner_client)

        rows = [[str(ip.id), ip.name, ip.ip, ip.type, ip.assignee_type or "N/A", ip.assignee_id or "N/A"] for ip in ips]
        cli_output.print_table("Primary IPs", ["ID", "Name", "IP", "Type", "Assignee", "Assignee ID"], rows)

    run_async(_list())


@primary_ip_app.command("get")
def primary_ip_get(
    ctx: typer.Context,
    ip_id: int,
    client: int | None = typer.Option(None, "--client", "-c", help="Client ID"),
):
    async def _get():
        client_id = get_client_id(ctx, client)
        async with db.session() as session:
            client_repo = ClientRepository(session)
            client_obj = await client_repo.get_by_id(client_id)
            token = decrypt_token(client_obj.api_token_encrypted)
            hetzner_client = await create_client(token)
            ip = await hetzner_client.get_primary_ip(ip_id)
            await close_client(hetzner_client)

        from bot.utils.formatters import format_primary_ip_info

        cli_output.print_panel(f"Primary IP {ip.name}", format_primary_ip_info(ip))

    run_async(_get())


@primary_ip_app.command("create")
def primary_ip_create(
    ctx: typer.Context,
    name: str | None = typer.Option(None, "--name", "-n", help="IP name"),
    type: str = typer.Option("ipv4", "--type", "-t", help="IP type (ipv4/ipv6)"),
    location: str | None = typer.Option(None, "--location", "-l", help="Location"),
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
                ip = await hetzner_client.create_primary_ip(type, location, name=name)
                await close_client(hetzner_client)
                cli_output.print_success(f"Primary IP created: {ip.ip} (ID: {ip.id})")
            except Exception as e:
                await close_client(hetzner_client)
                cli_output.print_error(f"Creation failed: {e}")

    run_async(_create())


@primary_ip_app.command("delete")
def primary_ip_delete(
    ctx: typer.Context,
    ip_id: int,
    client: int | None = typer.Option(None, "--client", "-c", help="Client ID"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
):
    async def _delete():
        client_id = get_client_id(ctx, client)
        if not yes and not cli_output.confirm(f"Delete primary IP {ip_id}?"):
            cli_output.print_warning("Cancelled")
            return

        async with db.session() as session:
            client_repo = ClientRepository(session)
            client_obj = await client_repo.get_by_id(client_id)
            token = decrypt_token(client_obj.api_token_encrypted)
            hetzner_client = await create_client(token)

            try:
                await hetzner_client.delete_primary_ip(ip_id)
                await close_client(hetzner_client)
                cli_output.print_success(f"Primary IP {ip_id} deleted")
            except Exception as e:
                await close_client(hetzner_client)
                cli_output.print_error(f"Deletion failed: {e}")

    run_async(_delete())


@primary_ip_app.command("assign")
def primary_ip_assign(
    ctx: typer.Context,
    ip_id: int,
    server_id: int,
    client: int | None = typer.Option(None, "--client", "-c", help="Client ID"),
):
    async def _assign():
        client_id = get_client_id(ctx, client)
        async with db.session() as session:
            client_repo = ClientRepository(session)
            client_obj = await client_repo.get_by_id(client_id)
            token = decrypt_token(client_obj.api_token_encrypted)
            hetzner_client = await create_client(token)

            try:
                await hetzner_client.assign_primary_ip_to_server(ip_id, server_id)
                await close_client(hetzner_client)
                cli_output.print_success(f"Primary IP {ip_id} assigned to server {server_id}")
            except Exception as e:
                await close_client(hetzner_client)
                cli_output.print_error(f"Assign failed: {e}")

    run_async(_assign())


@primary_ip_app.command("unassign")
def primary_ip_unassign(
    ctx: typer.Context,
    ip_id: int,
    client: int | None = typer.Option(None, "--client", "-c", help="Client ID"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
):
    async def _unassign():
        client_id = get_client_id(ctx, client)
        if not yes and not cli_output.confirm(f"Unassign primary IP {ip_id}?"):
            cli_output.print_warning("Cancelled")
            return

        async with db.session() as session:
            client_repo = ClientRepository(session)
            client_obj = await client_repo.get_by_id(client_id)
            token = decrypt_token(client_obj.api_token_encrypted)
            hetzner_client = await create_client(token)

            try:
                await hetzner_client.unassign_primary_ip_from_server(ip_id)
                await close_client(hetzner_client)
                cli_output.print_success(f"Primary IP {ip_id} unassigned")
            except Exception as e:
                await close_client(hetzner_client)
                cli_output.print_error(f"Unassign failed: {e}")

    run_async(_unassign())


@primary_ip_app.command("rename")
def primary_ip_rename(
    ctx: typer.Context,
    ip_id: int,
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
                await hetzner_client.update_primary_ip(ip_id, name=name)
                await close_client(hetzner_client)
                cli_output.print_success(f"Primary IP {ip_id} renamed to {name}")
            except Exception as e:
                await close_client(hetzner_client)
                cli_output.print_error(f"Failed: {e}")

    run_async(_rename())


@primary_ip_app.command("set-dns")
def primary_ip_set_dns(
    ctx: typer.Context,
    ip_id: int,
    ip: str = typer.Option(..., "--ip", help="IP address"),
    dns: str = typer.Option(..., "--dns", help="DNS PTR record"),
    client: int | None = typer.Option(None, "--client", "-c", help="Client ID"),
):
    async def _set_dns():
        client_id = get_client_id(ctx, client)
        async with db.session() as session:
            client_repo = ClientRepository(session)
            client_obj = await client_repo.get_by_id(client_id)
            token = decrypt_token(client_obj.api_token_encrypted)
            hetzner_client = await create_client(token)

            try:
                await hetzner_client.update_primary_ip(ip_id, dns_ptr={"ip": ip, "dns_ptr": dns})
                await close_client(hetzner_client)
                cli_output.print_success(f"DNS set for {ip}: {dns}")
            except Exception as e:
                await close_client(hetzner_client)
                cli_output.print_error(f"Failed: {e}")

    run_async(_set_dns())


# Floating IPs
@floating_ip_app.command("list")
def floating_ip_list(
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
            ips = await hetzner_client.list_floating_ips()
            await close_client(hetzner_client)

        rows = [
            [
                str(ip.id),
                ip.description or "N/A",
                ip.ip,
                ip.type,
                ip.server.get("name", "N/A") if ip.server else "Not assigned",
            ]
            for ip in ips
        ]
        cli_output.print_table("Floating IPs", ["ID", "Description", "IP", "Type", "Server"], rows)

    run_async(_list())


@floating_ip_app.command("get")
def floating_ip_get(
    ctx: typer.Context,
    ip_id: int,
    client: int | None = typer.Option(None, "--client", "-c", help="Client ID"),
):
    async def _get():
        client_id = get_client_id(ctx, client)
        async with db.session() as session:
            client_repo = ClientRepository(session)
            client_obj = await client_repo.get_by_id(client_id)
            token = decrypt_token(client_obj.api_token_encrypted)
            hetzner_client = await create_client(token)
            ip = await hetzner_client.get_floating_ip(ip_id)
            await close_client(hetzner_client)

        from bot.utils.formatters import format_floating_ip_info

        cli_output.print_panel(f"Floating IP {ip.description or 'N/A'}", format_floating_ip_info(ip))

    run_async(_get())


@floating_ip_app.command("create")
def floating_ip_create(
    ctx: typer.Context,
    type: str = typer.Option("ipv4", "--type", "-t", help="IP type (ipv4/ipv6)"),
    location: str | None = typer.Option(None, "--location", "-l", help="Location"),
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
                ip = await hetzner_client.create_floating_ip(type, location)
                await close_client(hetzner_client)
                cli_output.print_success(f"Floating IP created: {ip.ip} (ID: {ip.id})")
            except Exception as e:
                await close_client(hetzner_client)
                cli_output.print_error(f"Creation failed: {e}")

    run_async(_create())


@floating_ip_app.command("delete")
def floating_ip_delete(
    ctx: typer.Context,
    ip_id: int,
    client: int | None = typer.Option(None, "--client", "-c", help="Client ID"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
):
    async def _delete():
        client_id = get_client_id(ctx, client)
        if not yes and not cli_output.confirm(f"Delete floating IP {ip_id}?"):
            cli_output.print_warning("Cancelled")
            return

        async with db.session() as session:
            client_repo = ClientRepository(session)
            client_obj = await client_repo.get_by_id(client_id)
            token = decrypt_token(client_obj.api_token_encrypted)
            hetzner_client = await create_client(token)

            try:
                await hetzner_client.delete_floating_ip(ip_id)
                await close_client(hetzner_client)
                cli_output.print_success(f"Floating IP {ip_id} deleted")
            except Exception as e:
                await close_client(hetzner_client)
                cli_output.print_error(f"Deletion failed: {e}")

    run_async(_delete())


@floating_ip_app.command("assign")
def floating_ip_assign(
    ctx: typer.Context,
    ip_id: int,
    server: int = typer.Option(..., "--server", "-s", help="Server ID"),
    client: int | None = typer.Option(None, "--client", "-c", help="Client ID"),
):
    async def _assign():
        client_id = get_client_id(ctx, client)
        async with db.session() as session:
            client_repo = ClientRepository(session)
            client_obj = await client_repo.get_by_id(client_id)
            token = decrypt_token(client_obj.api_token_encrypted)
            hetzner_client = await create_client(token)

            try:
                await hetzner_client.assign_floating_ip(ip_id, server)
                await close_client(hetzner_client)
                cli_output.print_success(f"Floating IP {ip_id} assigned to server {server}")
            except Exception as e:
                await close_client(hetzner_client)
                cli_output.print_error(f"Assign failed: {e}")

    run_async(_assign())


@floating_ip_app.command("unassign")
def floating_ip_unassign(
    ctx: typer.Context,
    ip_id: int,
    client: int | None = typer.Option(None, "--client", "-c", help="Client ID"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
):
    async def _unassign():
        client_id = get_client_id(ctx, client)
        if not yes and not cli_output.confirm(f"Unassign floating IP {ip_id}?"):
            cli_output.print_warning("Cancelled")
            return

        async with db.session() as session:
            client_repo = ClientRepository(session)
            client_obj = await client_repo.get_by_id(client_id)
            token = decrypt_token(client_obj.api_token_encrypted)
            hetzner_client = await create_client(token)

            try:
                await hetzner_client.unassign_floating_ip(ip_id)
                await close_client(hetzner_client)
                cli_output.print_success(f"Floating IP {ip_id} unassigned")
            except Exception as e:
                await close_client(hetzner_client)
                cli_output.print_error(f"Unassign failed: {e}")

    run_async(_unassign())


@floating_ip_app.command("rename")
def floating_ip_rename(
    ctx: typer.Context,
    ip_id: int,
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
                await hetzner_client.update_floating_ip(ip_id, description=name)
                await close_client(hetzner_client)
                cli_output.print_success(f"Floating IP {ip_id} renamed to {name}")
            except Exception as e:
                await close_client(hetzner_client)
                cli_output.print_error(f"Failed: {e}")

    run_async(_rename())


@floating_ip_app.command("set-dns")
def floating_ip_set_dns(
    ctx: typer.Context,
    ip_id: int,
    ip: str = typer.Option(..., "--ip", help="IP address"),
    dns: str = typer.Option(..., "--dns", help="DNS PTR record"),
    client: int | None = typer.Option(None, "--client", "-c", help="Client ID"),
):
    async def _set_dns():
        client_id = get_client_id(ctx, client)
        async with db.session() as session:
            client_repo = ClientRepository(session)
            client_obj = await client_repo.get_by_id(client_id)
            token = decrypt_token(client_obj.api_token_encrypted)
            hetzner_client = await create_client(token)

            try:
                await hetzner_client.change_floating_ip_dns(ip_id, ip, dns)
                await close_client(hetzner_client)
                cli_output.print_success(f"DNS set for {ip}: {dns}")
            except Exception as e:
                await close_client(hetzner_client)
                cli_output.print_error(f"Failed: {e}")

    run_async(_set_dns())
