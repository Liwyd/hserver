import logging
import time
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

logger = logging.getLogger(__name__)


class LoggingMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        start_time = time.time()
        user = data.get("user")
        user_id = user.telegram_id if user else "unknown"

        event_type = (
            "message" if isinstance(event, Message) else "callback" if isinstance(event, CallbackQuery) else "other"
        )
        event_data = (
            event.text if isinstance(event, Message) else event.data if isinstance(event, CallbackQuery) else str(event)
        )

        try:
            result = await handler(event, data)
            duration = time.time() - start_time
            logger.info(f"user={user_id} type={event_type} data={event_data[:100]} duration={duration:.3f}s status=ok")
            return result
        except Exception as e:
            duration = time.time() - start_time
            logger.error(
                f"user={user_id} type={event_type} data={event_data[:100]} duration={duration:.3f}s status=error error={e}"
            )
            raise
