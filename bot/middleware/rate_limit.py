import time
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject


class RateLimitMiddleware(BaseMiddleware):
    def __init__(self, max_requests: int = 30, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._requests: dict[int, list[float]] = {}

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user_id = None
        if isinstance(event, Message) or isinstance(event, CallbackQuery):
            user_id = event.from_user.id if event.from_user else None

        if user_id:
            now = time.time()
            if user_id not in self._requests:
                self._requests[user_id] = []

            self._requests[user_id] = [t for t in self._requests[user_id] if now - t < self.window_seconds]

            if len(self._requests[user_id]) >= self.max_requests:
                if isinstance(event, CallbackQuery):
                    await event.answer("⚠️ Too many requests. Please wait.", show_alert=True)
                elif isinstance(event, Message):
                    await event.reply("⚠️ Too many requests. Please wait.")
                return

            self._requests[user_id].append(now)

        return await handler(event, data)
