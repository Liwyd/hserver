from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from bot.config import get_settings
from bot.database.models import Base


class Database:
    def __init__(self):
        self._engine = None
        self._session_factory = None

    def init(self):
        settings = get_settings()
        self._engine = create_async_engine(
            settings.database_url,
            echo=False,
            poolclass=NullPool,
        )
        self._session_factory = async_sessionmaker(
            self._engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )

    @asynccontextmanager
    async def session(self) -> AsyncSession:
        if self._session_factory is None:
            self.init()
        async with self._session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    async def create_tables(self):
        if self._engine is None:
            self.init()
        async with self._engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async def close(self):
        if self._engine:
            await self._engine.dispose()
            self._engine = None
            self._session_factory = None


db = Database()
