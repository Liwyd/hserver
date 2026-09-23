import asyncio

import typer

from bot.cli.commands import (
    bot_app,
    certificate_app,
    client_app,
    firewall_app,
    floating_ip_app,
    loadbalancer_app,
    network_app,
    placementgroup_app,
    primary_ip_app,
    server_app,
    snapshot_app,
    sshkey_app,
    volume_app,
)
from bot.cli.output import CLIOutput

app = typer.Typer(
    name="hserver",
    help="Hetzner Cloud Server Management CLI",
    no_args_is_help=True,
    rich_markup_mode="rich",
)

cli_output = CLIOutput()

app.add_typer(bot_app, name="bot")
app.add_typer(server_app, name="servers")
app.add_typer(volume_app, name="volumes")
app.add_typer(primary_ip_app, name="primary-ips")
app.add_typer(floating_ip_app, name="floating-ips")
app.add_typer(network_app, name="networks")
app.add_typer(firewall_app, name="firewalls")
app.add_typer(loadbalancer_app, name="load-balancers")
app.add_typer(sshkey_app, name="ssh-keys")
app.add_typer(certificate_app, name="certificates")
app.add_typer(placementgroup_app, name="placement-groups")
app.add_typer(snapshot_app, name="snapshots")
app.add_typer(client_app, name="clients")


@app.callback()
def main(
    ctx: typer.Context,
    client: int | None = typer.Option(None, "--client", "-c", help="Client ID to use"),
):
    ctx.ensure_object(dict)
    ctx.obj["client_id"] = client


def run_async(coro):
    return asyncio.run(coro)


if __name__ == "__main__":
    app()
