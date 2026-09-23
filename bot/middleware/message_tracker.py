from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.repositories import UserMessageRepository


class MessageTrackerMiddleware(BaseMiddleware):
    MESSAGE_TYPES_TO_CLEAN = [
        "menu",
        "info",
        "list",
        "create_step",
        "edit_step",
    ]

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        result = await handler(event, data)

        if isinstance(event, (Message, CallbackQuery)):
            session = data.get("session")
            user = data.get("user")

            if session and user:
                msg_repo = UserMessageRepository(session)
                chat_id = event.chat.id if isinstance(event, Message) else event.message.chat.id

                if isinstance(event, CallbackQuery):
                    await msg_repo.delete_by_types(user.id, chat_id, self.MESSAGE_TYPES_TO_CLEAN)

        return result


class MessageTrackingHelper:
    def __init__(self, session: AsyncSession, user_id: int, chat_id: int):
        self.msg_repo = UserMessageRepository(session)
        self.user_id = user_id
        self.chat_id = chat_id

    async def track(self, message: Message, msg_type: str = "menu"):
        await self.msg_repo.track(self.user_id, self.chat_id, message.message_id, msg_type)

    async def cleanup(self, keep_types: list[str] | None = None):
        if keep_types:
            await self.msg_repo.delete_by_types(self.user_id, self.chat_id, keep_types)
        else:
            await self.msg_repo.delete_by_types(self.user_id, self.chat_id, self.MESSAGE_TYPES_TO_CLEAN)

    async def get_last(self, msg_type: str) -> Message | None:
        messages = await self.msg_repo.get_messages(self.user_id, self.chat_id, [msg_type])
        return messages[0] if messages else None
