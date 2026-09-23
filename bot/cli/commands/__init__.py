from bot.cli.commands.bot import bot_app
from bot.cli.commands.certificate import certificate_app
from bot.cli.commands.client import client_app
from bot.cli.commands.firewall import firewall_app
from bot.cli.commands.ip import floating_ip_app, primary_ip_app
from bot.cli.commands.loadbalancer import loadbalancer_app
from bot.cli.commands.network import network_app
from bot.cli.commands.placementgroup import placementgroup_app
from bot.cli.commands.server import server_app
from bot.cli.commands.snapshot import snapshot_app
from bot.cli.commands.sshkey import sshkey_app
from bot.cli.commands.volume import volume_app

CLIENT_ID_REQUIRED = "Client ID required. Use --client or set default."

__all__ = [
    "bot_app",
    "certificate_app",
    "client_app",
    "firewall_app",
    "floating_ip_app",
    "loadbalancer_app",
    "network_app",
    "placementgroup_app",
    "primary_ip_app",
    "server_app",
    "snapshot_app",
    "sshkey_app",
    "volume_app",
]
