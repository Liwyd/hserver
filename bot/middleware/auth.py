from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject
from aiogram.types import User as TgUser

from bot.config import get_settings
from bot.database.base import db
from bot.database.repositories import ClientRepository, UserRepository


class AuthMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        tg_user: TgUser | None = None
        if isinstance(event, Message) or isinstance(event, CallbackQuery):
            tg_user = event.from_user

        if not tg_user:
            return await handler(event, data)

        settings = get_settings()
        is_env_admin = tg_user.id in settings.admin_ids

        async with db.session() as session:
            user_repo = UserRepository(session)
            user = await user_repo.get_by_telegram_id(tg_user.id)

            if not user:
                user = await user_repo.create_or_update(
                    telegram_id=tg_user.id,
                    username=tg_user.username,
                    first_name=tg_user.first_name,
                    last_name=tg_user.last_name,
                )

            if is_env_admin and not user.is_bot_admin:
                user.is_bot_admin = True

            if user.role == "user" and is_env_admin:
                user.role = "admin"

            client_repo = ClientRepository(session)
            clients = await client_repo.list_for_user(user)

            data["user"] = user
            data["clients"] = clients
            data["is_owner"] = False
            data["is_admin"] = user.role in ("owner", "admin") or user.is_bot_admin
            data["session"] = session

            if isinstance(event, CallbackQuery):
                await self._resolve_client_from_callback(event, data, client_repo)

        return await handler(event, data)

    async def _resolve_client_from_callback(
        self, callback: CallbackQuery, data: dict[str, Any], client_repo: ClientRepository
    ):
        cb_data = callback.data
        if not cb_data or cb_data.startswith("home"):
            return

        parts = cb_data.split(":")
        if len(parts) >= 6:
            try:
                target_id = int(parts[5])
                if target_id > 0:
                    client = await client_repo.get_by_id(target_id)
                    if client:
                        data["current_client"] = client
                        data["is_owner"] = client.owner_id == data["user"].id
            except (ValueError, IndexError):
                pass
