from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from bot.database.repositories import ClientRepository
from bot.encryption import decrypt_token
from bot.hetzner.client import create_client


class BaseHandler:
    def __init__(self):
        self.router = Router()

    def register(self, dp):
        dp.include_router(self.router)


class StartHandler(BaseHandler):
    def __init__(self):
        super().__init__()
        self.router.message(Command("start"))(self.cmd_start)

    async def cmd_start(self, message: Message):
        from bot.handlers.start import show_home_screen

        await show_home_screen(message)


async def get_user_client(session, user, client_id: int):
    from bot.database.repositories import ServerAccessRepository, UserClientAccessRepository

    client_repo = ClientRepository(session)
    user_client_repo = UserClientAccessRepository(session)
    server_access_repo = ServerAccessRepository(session)

    client = await client_repo.get_by_id(client_id)
    if not client:
        return None, None, None, None

    is_owner = client.owner_id == user.id
    is_admin = user.role in ("owner", "admin") or user.is_bot_admin

    if not is_owner and not is_admin:
        access = await user_client_repo.list_for_user(user.id)
        client_ids = [a.client_id for a in access]
        if client_id not in client_ids:
            return None, None, None, None

    return client, is_owner, is_admin, server_access_repo


async def get_hetzner_client(session, client_id: int):

    client_repo = ClientRepository(session)
    client = await client_repo.get_by_id(client_id)
    if not client:
        return None
    token = decrypt_token(client.api_token_encrypted)
    return await create_client(token), client
