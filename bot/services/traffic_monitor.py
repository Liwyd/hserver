import asyncio

from bot.config import get_settings
from bot.database.base import db
from bot.database.repositories import ClientRepository
from bot.encryption import decrypt_token
from bot.hetzner.client import close_client, create_client


class TrafficMonitor:
    def __init__(self):
        self._running = False
        self._task = None

    async def run(self):
        self._running = True
        settings = get_settings()

        if not settings.traffic_monitor_enabled:
            return

        interval = settings.traffic_monitor_interval_minutes * 60

        while self._running:
            try:
                await self.check_all_clients()
            except Exception as e:
                print(f"Traffic monitor error: {e}")

            await asyncio.sleep(interval)

    async def check_all_clients(self):
        settings = get_settings()
        alert_percent = settings.traffic_monitor_alert_percent

        async with db.session() as session:
            client_repo = ClientRepository(session)
            clients = await client_repo.list_all(active_only=True)

            for client in clients:
                token = decrypt_token(client.api_token_encrypted)
                hetzner_client = await create_client(token)

                try:
                    servers = await hetzner_client.list_servers()

                    for server in servers:
                        traffic = await hetzner_client.get_server_traffic(server.id)

                        outgoing_gb = traffic.get("outgoing", 0) / (1024**3)
                        included_gb = traffic.get("included", 0) / (1024**3)

                        if included_gb > 0:
                            used_percent = (outgoing_gb / included_gb) * 100
                            if used_percent >= alert_percent:
                                await self.send_alert(client, server, traffic, used_percent)

                except Exception as e:
                    print(f"Error checking traffic for client {client.remark}: {e}")
                finally:
                    await close_client(hetzner_client)

    async def send_alert(self, client, server, traffic, used_percent):
        outgoing_gb = traffic.get("outgoing", 0) / (1024**3)
        included_gb = traffic.get("included", 0) / (1024**3)
        billable_gb = max(0, outgoing_gb - included_gb)

        message = (
            f"⚠️ Traffic Alert\n"
            f"Client: {client.remark}\n"
            f"Server: {server.name} [{server.id}]\n"
            f"Outgoing: {outgoing_gb:.1f} GB of {included_gb:.1f} GB\n"
            f"Used: {used_percent:.1f}%\n"
            f"Billable: {billable_gb:.1f} GB"
        )

        settings = get_settings()
        for admin_id in settings.admin_ids:
            try:
                from bot.main import bot

                await bot.send_message(admin_id, message)
            except Exception as e:
                print(f"Failed to send alert to admin {admin_id}: {e}")


traffic_monitor = TrafficMonitor()
