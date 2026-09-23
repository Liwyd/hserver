
import typer

from bot.cli.main import cli_output, run_async
from bot.database.base import db
from bot.database.repositories import ClientRepository
from bot.encryption import decrypt_token
from bot.hetzner.client import close_client, create_client

sshkey_app = typer.Typer(name="ssh-keys", help="SSH Key management commands")


def get_client_id(ctx: typer.Context, client: int | None) -> int:
    if client:
        return client
    if ctx.obj.get("client_id"):
        return ctx.obj["client_id"]
    raise typer.BadParameter("Client ID required. Use --client or set default.")


@sshkey_app.command("list")
def sshkey_list(
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
            keys = await hetzner_client.list_ssh_keys()
            await close_client(hetzner_client)

        rows = [[str(k.id), k.name, k.fingerprint] for k in keys]
        cli_output.print_table("SSH Keys", ["ID", "Name", "Fingerprint"], rows)

    run_async(_list())


@sshkey_app.command("get")
def sshkey_get(
    ctx: typer.Context,
    key_id: int,
    client: int | None = typer.Option(None, "--client", "-c", help="Client ID"),
):
    async def _get():
        client_id = get_client_id(ctx, client)
        async with db.session() as session:
            client_repo = ClientRepository(session)
            client_obj = await client_repo.get_by_id(client_id)
            token = decrypt_token(client_obj.api_token_encrypted)
            hetzner_client = await create_client(token)
            key = await hetzner_client.get_ssh_key(key_id)
            await close_client(hetzner_client)

        from bot.utils.formatters import format_ssh_key_info

        cli_output.print_panel(f"SSH Key {key.name}", format_ssh_key_info(key))

    run_async(_get())


@sshkey_app.command("create")
def sshkey_create(
    ctx: typer.Context,
    name: str = typer.Option(..., "--name", "-n", help="Key name"),
    key: str = typer.Option(..., "--key", "-k", help="Public key or path to .pub file"),
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
                ssh_key = await hetzner_client.create_ssh_key(name, key)
                await close_client(hetzner_client)
                cli_output.print_success(f"SSH Key created: {ssh_key.name} (ID: {ssh_key.id})")
            except Exception as e:
                await close_client(hetzner_client)
                cli_output.print_error(f"Creation failed: {e}")

    run_async(_create())


@sshkey_app.command("delete")
def sshkey_delete(
    ctx: typer.Context,
    key_id: int,
    client: int | None = typer.Option(None, "--client", "-c", help="Client ID"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
):
    async def _delete():
        client_id = get_client_id(ctx, client)
        if not yes and not cli_output.confirm(f"Delete SSH key {key_id}?"):
            cli_output.print_warning("Cancelled")
            return

        async with db.session() as session:
            client_repo = ClientRepository(session)
            client_obj = await client_repo.get_by_id(client_id)
            token = decrypt_token(client_obj.api_token_encrypted)
            hetzner_client = await create_client(token)

            try:
                await hetzner_client.delete_ssh_key(key_id)
                await close_client(hetzner_client)
                cli_output.print_success(f"SSH Key {key_id} deleted")
            except Exception as e:
                await close_client(hetzner_client)
                cli_output.print_error(f"Deletion failed: {e}")

    run_async(_delete())


@sshkey_app.command("rename")
def sshkey_rename(
    ctx: typer.Context,
    key_id: int,
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
                await hetzner_client.update_ssh_key(key_id, name=name)
                await close_client(hetzner_client)
                cli_output.print_success(f"SSH Key {key_id} renamed to {name}")
            except Exception as e:
                await close_client(hetzner_client)
                cli_output.print_error(f"Failed: {e}")

    run_async(_rename())
