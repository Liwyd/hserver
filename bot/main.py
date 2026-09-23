import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from bot.config import get_settings
from bot.database.base import db
from bot.handlers import register_handlers
from bot.middleware import (
    AuthMiddleware,
    LoggingMiddleware,
    MessageTrackerMiddleware,
    RateLimitMiddleware,
)
from bot.services.traffic_monitor import TrafficMonitor

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


async def on_startup():
    logger.info("Starting bot...")
    await db.create_tables()

    settings = get_settings()
    traffic_monitor = TrafficMonitor()
    asyncio.create_task(traffic_monitor.run())
    logger.info("Traffic monitor started")


async def on_shutdown():
    logger.info("Shutting down...")
    await db.close()


async def main():
    settings = get_settings()

    bot = Bot(
        token=settings.telegram_api_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )

    storage = MemoryStorage()
    dp = Dispatcher(storage=storage)

    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    dp.message.middleware(LoggingMiddleware())
    dp.message.middleware(RateLimitMiddleware())
    dp.message.middleware(AuthMiddleware())
    dp.message.middleware(MessageTrackerMiddleware())

    dp.callback_query.middleware(LoggingMiddleware())
    dp.callback_query.middleware(RateLimitMiddleware())
    dp.callback_query.middleware(AuthMiddleware())
    dp.callback_query.middleware(MessageTrackerMiddleware())

    register_handlers(dp)

    logger.info("Bot started polling")
    await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped")
