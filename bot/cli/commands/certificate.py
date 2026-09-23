# ruff: noqa: I001
import typer
from pathlib import Path

from bot.cli.main import cli_output, run_async
from bot.database.base import db
from bot.database.repositories import ClientRepository
from bot.encryption import decrypt_token
from bot.hetzner.client import close_client, create_client

certificate_app = typer.Typer(name="certificates", help="Certificate management commands")

CLIENT_ID_REQUIRED = "Client ID required. Use --client or set default."


def get_client_id(ctx: typer.Context, client: int | None) -> int:
    if client:
        return client
    if ctx.obj.get("client_id"):
        return ctx.obj["client_id"]
    raise typer.BadParameter(CLIENT_ID_REQUIRED)


@certificate_app.command("list")
def certificate_list(
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
            certs = await hetzner_client.list_certificates()
            await close_client(hetzner_client)

        rows = [[str(c.id), c.name, c.type, ", ".join(c.domain_names)] for c in certs]
        cli_output.print_table("Certificates", ["ID", "Name", "Type", "Domains"], rows)

    run_async(_list())


@certificate_app.command("get")
def certificate_get(
    ctx: typer.Context,
    cert_id: int,
    client: int | None = typer.Option(None, "--client", "-c", help="Client ID"),
):
    async def _get():
        client_id = get_client_id(ctx, client)
        async with db.session() as session:
            client_repo = ClientRepository(session)
            client_obj = await client_repo.get_by_id(client_id)
            token = decrypt_token(client_obj.api_token_encrypted)
            hetzner_client = await create_client(token)
            cert = await hetzner_client.get_certificate(cert_id)
            await close_client(hetzner_client)

        from bot.utils.formatters import format_certificate_info

        cli_output.print_panel(f"Certificate {cert.name}", format_certificate_info(cert))

    run_async(_get())


@certificate_app.command("create")
def certificate_create(
    ctx: typer.Context,
    name: str = typer.Option(..., "--name", "-n", help="Certificate name"),
    cert_file: str = typer.Option(..., "--cert-file", help="Path to certificate PEM file"),
    key_file: str = typer.Option(..., "--key-file", help="Path to private key PEM file"),
    client: int | None = typer.Option(None, "--client", "-c", help="Client ID"),
):
    async def _create():
        client_id = get_client_id(ctx, client)

        cert_pem = Path(cert_file).read_text()
        key_pem = Path(key_file).read_text()

        async with db.session() as session:
            client_repo = ClientRepository(session)
            client_obj = await client_repo.get_by_id(client_id)
            token = decrypt_token(client_obj.api_token_encrypted)
            hetzner_client = await create_client(token)

            try:
                cert = await hetzner_client.create_certificate(name, cert_pem, key_pem)
                await close_client(hetzner_client)
                cli_output.print_success(f"Certificate created: {cert.name} (ID: {cert.id})")
            except Exception as e:
                await close_client(hetzner_client)
                cli_output.print_error(f"Creation failed: {e}")

    run_async(_create())


@certificate_app.command("create-managed")
def certificate_create_managed(
    ctx: typer.Context,
    name: str = typer.Option(..., "--name", "-n", help="Certificate name"),
    domain: str = typer.Option(..., "--domain", "-d", help="Domain names (comma separated)"),
    client: int | None = typer.Option(None, "--client", "-c", help="Client ID"),
):
    async def _create_managed():
        client_id = get_client_id(ctx, client)
        domains = [d.strip() for d in domain.split(",") if d.strip()]

        async with db.session() as session:
            client_repo = ClientRepository(session)
            client_obj = await client_repo.get_by_id(client_id)
            token = decrypt_token(client_obj.api_token_encrypted)
            hetzner_client = await create_client(token)

            try:
                cert = await hetzner_client.create_managed_certificate(name, domains)
                await close_client(hetzner_client)
                cli_output.print_success(f"Managed certificate created: {cert.name} (ID: {cert.id})")
            except Exception as e:
                await close_client(hetzner_client)
                cli_output.print_error(f"Creation failed: {e}")

    run_async(_create_managed())


@certificate_app.command("delete")
def certificate_delete(
    ctx: typer.Context,
    cert_id: int,
    client: int | None = typer.Option(None, "--client", "-c", help="Client ID"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
):
    async def _delete():
        client_id = get_client_id(ctx, client)
        if not yes and not cli_output.confirm(f"Delete certificate {cert_id}?"):
            cli_output.print_info("Cancelled")
            return

        async with db.session() as session:
            client_repo = ClientRepository(session)
            client_obj = await client_repo.get_by_id(client_id)
            token = decrypt_token(client_obj.api_token_encrypted)
            hetzner_client = await create_client(token)

            try:
                await hetzner_client.delete_certificate(cert_id)
                await close_client(hetzner_client)
                cli_output.print_success(f"Certificate {cert_id} deleted")
            except Exception as e:
                await close_client(hetzner_client)
                cli_output.print_error(f"Deletion failed: {e}")

    run_async(_delete())


@certificate_app.command("rename")
def certificate_rename(
    ctx: typer.Context,
    cert_id: int,
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
                await hetzner_client.update_certificate(cert_id, name=name)
                await close_client(hetzner_client)
                cli_output.print_success(f"Certificate {cert_id} renamed to {name}")
            except Exception as e:
                await close_client(hetzner_client)
                cli_output.print_error(f"Failed: {e}")

    run_async(_rename())
