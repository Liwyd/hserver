
import typer

from bot.cli.main import cli_output, run_async
from bot.database.base import db
from bot.database.repositories import ClientRepository
from bot.encryption import decrypt_token, encrypt_token
from bot.hetzner.client import close_client, create_client

CLIENT_ID_REQUIRED = "Client ID required. Use --client or set default."

client_app = typer.Typer(name="clients", help="Client management commands")


@client_app.command("list")
def client_list():
    async def _list():
        async with db.session() as session:
            client_repo = ClientRepository(session)
            clients = await client_repo.list_all()

        rows = [[str(c.id), c.remark, cli_output.mask_token(decrypt_token(c.api_token_encrypted))] for c in clients]
        cli_output.print_table("Clients", ["ID", "Remark", "Token"], rows)

    run_async(_list())


@client_app.command("get")
def client_get(client_id: int):
    async def _get():
        async with db.session() as session:
            client_repo = ClientRepository(session)
            client = await client_repo.get_by_id(client_id)
            if not client:
                cli_output.print_error("Client not found")
                return

        cli_output.print_panel(
            f"Client {client.remark}",
            f"ID: {client.id}\nRemark: {client.remark}\n"
            f"Token: {cli_output.mask_token(decrypt_token(client.api_token_encrypted))}\n"
            f"Active: {client.is_active}",
        )

    run_async(_get())


@client_app.command("add")
def client_add(
    remark: str = typer.Option(..., "--remark", "-r", help="Client remark"),
    token: str = typer.Option(..., "--token", "-t", help="Hetzner API token"),
):
    async def _add():
        async with db.session() as session:
            client_repo = ClientRepository(session)
            existing = await client_repo.get_by_remark(remark)
            if existing:
                cli_output.print_error("Client with this remark already exists")
                return

            try:
                hetzner_client = await create_client(token)
                await hetzner_client.list_servers()
                await close_client(hetzner_client)
            except Exception:
                cli_output.print_error("Invalid API token")
                return

            token_encrypted = encrypt_token(token)
            import hashlib

            token_hash = hashlib.sha256(token.encode()).hexdigest()

            client = await client_repo.create(remark, token_encrypted, token_hash)
            cli_output.print_success(f"Client added: {client.remark} (ID: {client.id})")

    run_async(_add())


@client_app.command("delete")
def client_delete(
    client_id: int,
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
):
    async def _delete():
        if not yes and not cli_output.confirm(f"Delete client {client_id}?"):
            cli_output.print_warning("Cancelled")
            return

        async with db.session() as session:
            client_repo = ClientRepository(session)
            success = await client_repo.delete(client_id)
            if success:
                cli_output.print_success(f"Client {client_id} deleted")
            else:
                cli_output.print_error("Client not found")

    run_async(_delete())


@client_app.command("rename")
def client_rename(
    client_id: int,
    name: str = typer.Option(..., "--name", "-n", help="New name"),
):
    async def _rename():
        async with db.session() as session:
            client_repo = ClientRepository(session)
            client = await client_repo.update_remark(client_id, name)
            if client:
                cli_output.print_success(f"Client {client_id} renamed to {name}")
            else:
                cli_output.print_error("Client not found")

    run_async(_rename())


@client_app.command("change-token")
def client_change_token(
    client_id: int,
    token: str = typer.Option(..., "--token", "-t", help="New Hetzner API token"),
):
    async def _change_token():
        async with db.session() as session:
            client_repo = ClientRepository(session)
            client = await client_repo.get_by_id(client_id)
            if not client:
                cli_output.print_error("Client not found")
                return

            try:
                hetzner_client = await create_client(token)
                await hetzner_client.list_servers()
                await close_client(hetzner_client)
            except Exception:
                cli_output.print_error("Invalid API token")
                return

            token_encrypted = encrypt_token(token)
            import hashlib

            token_hash = hashlib.sha256(token.encode()).hexdigest()

            await client_repo.update_token(client_id, token_encrypted, token_hash)
            cli_output.print_success(f"Client {client_id} token updated")

    run_async(_change_token())


@client_app.command("test")
def client_test(client_id: int):
    async def _test():
        async with db.session() as session:
            client_repo = ClientRepository(session)
            client = await client_repo.get_by_id(client_id)
            if not client:
                cli_output.print_error("Client not found")
                return

            token = decrypt_token(client.api_token_encrypted)
            try:
                hetzner_client = await create_client(token)
                await hetzner_client.list_servers()
                await close_client(hetzner_client)
                cli_output.print_success(f"Client {client_id} token is valid")
            except Exception as e:
                cli_output.print_error(f"Client {client_id} token is invalid: {e}")

    run_async(_test())
