from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.models import (
    AuditLog,
    BotAdmin,
    BotFSMState,
    Client,
    ServerAccess,
    TrafficAlertConfig,
    User,
    UserClientAccess,
    UserMessage,
)


class UserRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_telegram_id(self, telegram_id: int) -> User | None:
        result = await self.session.execute(select(User).where(User.telegram_id == telegram_id))
        return result.scalar_one_or_none()

    async def get_by_id(self, user_id: int) -> User | None:
        result = await self.session.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()

    async def create_or_update(
        self,
        telegram_id: int,
        username: str | None = None,
        first_name: str | None = None,
        last_name: str | None = None,
    ) -> User:
        user = await self.get_by_telegram_id(telegram_id)
        if user:
            user.username = username
            user.first_name = first_name
            user.last_name = last_name
        else:
            user = User(
                telegram_id=telegram_id,
                username=username,
                first_name=first_name,
                last_name=last_name,
            )
            self.session.add(user)
        await self.session.flush()
        return user

    async def set_role(self, user_id: int, role: str) -> User | None:
        user = await self.get_by_id(user_id)
        if user:
            user.role = role
        return user

    async def set_bot_admin(self, user_id: int, is_admin: bool) -> User | None:
        user = await self.get_by_id(user_id)
        if user:
            user.is_bot_admin = is_admin
        return user


class ClientRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, client_id: int) -> Client | None:
        result = await self.session.execute(select(Client).where(Client.id == client_id))
        return result.scalar_one_or_none()

    async def get_by_remark(self, remark: str) -> Client | None:
        result = await self.session.execute(select(Client).where(Client.remark == remark))
        return result.scalar_one_or_none()

    async def get_by_token_hash(self, token_hash: str) -> Client | None:
        result = await self.session.execute(select(Client).where(Client.token_hash == token_hash))
        return result.scalar_one_or_none()

    async def list_all(self, active_only: bool = True) -> list[Client]:
        query = select(Client)
        if active_only:
            query = query.where(Client.is_active)
        query = query.order_by(Client.remark)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def list_for_user(self, user: User) -> list[Client]:
        if user.role in ("owner", "admin") or user.is_bot_admin:
            return await self.list_all()
        query = (
            select(Client)
            .join(UserClientAccess, UserClientAccess.client_id == Client.id)
            .where(UserClientAccess.user_id == user.id, Client.is_active)
            .order_by(Client.remark)
        )
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def create(
        self,
        remark: str,
        api_token_encrypted: bytes,
        token_hash: str,
        owner_id: int | None = None,
    ) -> Client:
        client = Client(
            remark=remark,
            api_token_encrypted=api_token_encrypted,
            token_hash=token_hash,
            owner_id=owner_id,
        )
        self.session.add(client)
        await self.session.flush()
        return client

    async def update_remark(self, client_id: int, remark: str) -> Client | None:
        client = await self.get_by_id(client_id)
        if client:
            client.remark = remark
        return client

    async def update_token(self, client_id: int, api_token_encrypted: bytes, token_hash: str) -> Client | None:
        client = await self.get_by_id(client_id)
        if client:
            client.api_token_encrypted = api_token_encrypted
            client.token_hash = token_hash
        return client

    async def delete(self, client_id: int) -> bool:
        client = await self.get_by_id(client_id)
        if client:
            await self.session.delete(client)
            return True
        return False


class UserClientAccessRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def grant(self, user_id: int, client_id: int, granted_by: int) -> UserClientAccess:
        access = UserClientAccess(user_id=user_id, client_id=client_id, granted_by=granted_by)
        self.session.add(access)
        await self.session.flush()
        return access

    async def revoke(self, user_id: int, client_id: int) -> bool:
        result = await self.session.execute(
            select(UserClientAccess).where(
                UserClientAccess.user_id == user_id,
                UserClientAccess.client_id == client_id,
            )
        )
        access = result.scalar_one_or_none()
        if access:
            await self.session.delete(access)
            return True
        return False

    async def list_for_user(self, user_id: int) -> list[UserClientAccess]:
        result = await self.session.execute(select(UserClientAccess).where(UserClientAccess.user_id == user_id))
        return list(result.scalars().all())

    async def list_for_client(self, client_id: int) -> list[UserClientAccess]:
        result = await self.session.execute(select(UserClientAccess).where(UserClientAccess.client_id == client_id))
        return list(result.scalars().all())


class ServerAccessRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def grant(self, client_id: int, server_id: int, user_id: int, granted_by: int) -> ServerAccess:
        access = ServerAccess(client_id=client_id, server_id=server_id, user_id=user_id, granted_by=granted_by)
        self.session.add(access)
        await self.session.flush()
        return access

    async def revoke(self, client_id: int, server_id: int, user_id: int) -> bool:
        result = await self.session.execute(
            select(ServerAccess).where(
                ServerAccess.client_id == client_id,
                ServerAccess.server_id == server_id,
                ServerAccess.user_id == user_id,
            )
        )
        access = result.scalar_one_or_none()
        if access:
            await self.session.delete(access)
            return True
        return False

    async def list_for_server(self, client_id: int, server_id: int) -> list[ServerAccess]:
        result = await self.session.execute(
            select(ServerAccess).where(ServerAccess.client_id == client_id, ServerAccess.server_id == server_id)
        )
        return list(result.scalars().all())

    async def list_for_user(self, user_id: int) -> list[ServerAccess]:
        result = await self.session.execute(select(ServerAccess).where(ServerAccess.user_id == user_id))
        return list(result.scalars().all())

    async def has_access(self, user_id: int, client_id: int, server_id: int) -> bool:
        result = await self.session.execute(
            select(func.count(ServerAccess.id)).where(
                ServerAccess.client_id == client_id,
                ServerAccess.server_id == server_id,
                ServerAccess.user_id == user_id,
            )
        )
        return result.scalar() > 0


class AuditLogRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def log(
        self,
        action: str,
        success: bool,
        user_id: int | None = None,
        client_id: int | None = None,
        resource_type: str | None = None,
        resource_id: int | None = None,
        details: dict | None = None,
        ip_address: str | None = None,
    ) -> AuditLog:
        log = AuditLog(
            user_id=user_id,
            client_id=client_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            details=details,
            ip_address=ip_address,
            success=success,
        )
        self.session.add(log)
        await self.session.flush()
        return log


class FSMStateRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_state(self, user_id: int) -> dict | None:
        result = await self.session.execute(select(BotFSMState).where(BotFSMState.user_id == user_id))
        state = result.scalar_one_or_none()
        return state.state_data if state else None

    async def set_state(self, user_id: int, chat_id: int, state_data: dict) -> BotFSMState:
        result = await self.session.execute(select(BotFSMState).where(BotFSMState.user_id == user_id))
        state = result.scalar_one_or_none()
        if state:
            state.chat_id = chat_id
            state.state_data = state_data
        else:
            state = BotFSMState(user_id=user_id, chat_id=chat_id, state_data=state_data)
            self.session.add(state)
        await self.session.flush()
        return state

    async def clear_state(self, user_id: int) -> bool:
        result = await self.session.execute(select(BotFSMState).where(BotFSMState.user_id == user_id))
        state = result.scalar_one_or_none()
        if state:
            await self.session.delete(state)
            return True
        return False


class UserMessageRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def track(self, user_id: int, chat_id: int, message_id: int, message_type: str | None = None):
        msg = UserMessage(user_id=user_id, chat_id=chat_id, message_id=message_id, message_type=message_type)
        self.session.add(msg)
        await self.session.flush()

    async def get_messages(
        self, user_id: int, chat_id: int, message_types: list[str] | None = None
    ) -> list[UserMessage]:
        query = select(UserMessage).where(UserMessage.user_id == user_id, UserMessage.chat_id == chat_id)
        if message_types:
            query = query.where(UserMessage.message_type.in_(message_types))
        query = query.order_by(UserMessage.created_at.desc())
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def delete_messages(self, user_id: int, chat_id: int, message_ids: list[int]) -> int:
        result = await self.session.execute(
            select(UserMessage).where(
                UserMessage.user_id == user_id,
                UserMessage.chat_id == chat_id,
                UserMessage.message_id.in_(message_ids),
            )
        )
        messages = list(result.scalars().all())
        for msg in messages:
            await self.session.delete(msg)
        return len(messages)

    async def delete_by_types(self, user_id: int, chat_id: int, message_types: list[str]) -> int:
        result = await self.session.execute(
            select(UserMessage).where(
                UserMessage.user_id == user_id,
                UserMessage.chat_id == chat_id,
                UserMessage.message_type.in_(message_types),
            )
        )
        messages = list(result.scalars().all())
        for msg in messages:
            await self.session.delete(msg)
        return len(messages)


class TrafficAlertConfigRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_or_create(self, client_id: int) -> TrafficAlertConfig:
        result = await self.session.execute(select(TrafficAlertConfig).where(TrafficAlertConfig.client_id == client_id))
        config = result.scalar_one_or_none()
        if not config:
            config = TrafficAlertConfig(client_id=client_id)
            self.session.add(config)
            await self.session.flush()
        return config

    async def update(
        self, client_id: int, enabled: bool | None = None, alert_percent: int | None = None
    ) -> TrafficAlertConfig | None:
        config = await self.get_or_create(client_id)
        if enabled is not None:
            config.enabled = enabled
        if alert_percent is not None:
            config.alert_percent = alert_percent
        return config


class BotAdminRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def is_admin(self, user_id: int) -> bool:
        result = await self.session.execute(select(BotAdmin).where(BotAdmin.user_id == user_id))
        return result.scalar_one_or_none() is not None

    async def add_admin(self, user_id: int, added_by: int) -> BotAdmin:
        admin = BotAdmin(user_id=user_id, added_by=added_by)
        self.session.add(admin)
        await self.session.flush()
        return admin

    async def remove_admin(self, user_id: int) -> bool:
        result = await self.session.execute(select(BotAdmin).where(BotAdmin.user_id == user_id))
        admin = result.scalar_one_or_none()
        if admin:
            await self.session.delete(admin)
            return True
        return False

    async def list_admins(self) -> list[BotAdmin]:
        result = await self.session.execute(select(BotAdmin))
        return list(result.scalars().all())
