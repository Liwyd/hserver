from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import BYTEA, INET, JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False, index=True)
    username: Mapped[str | None] = mapped_column(String(255))
    first_name: Mapped[str | None] = mapped_column(String(255))
    last_name: Mapped[str | None] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(50), default="user", nullable=False, index=True)
    is_bot_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    owned_clients: Mapped[list["Client"]] = relationship(back_populates="owner")
    client_access: Mapped[list["UserClientAccess"]] = relationship(back_populates="user")
    server_access: Mapped[list["ServerAccess"]] = relationship(back_populates="user")
    granted_access: Mapped[list["UserClientAccess"]] = relationship(back_populates="granted_by_user")
    granted_server_access: Mapped[list["ServerAccess"]] = relationship(back_populates="granted_by_user")
    added_admins: Mapped[list["BotAdmin"]] = relationship(back_populates="added_by_user")


class Client(Base):
    __tablename__ = "clients"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    remark: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    api_token_encrypted: Mapped[bytes] = mapped_column(BYTEA, nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    owner: Mapped["User"] = relationship(back_populates="owned_clients")
    user_access: Mapped[list["UserClientAccess"]] = relationship(back_populates="client")
    server_access: Mapped[list["ServerAccess"]] = relationship(back_populates="client")
    traffic_config: Mapped["TrafficAlertConfig | None"] = relationship(back_populates="client", uselist=False)


class UserClientAccess(Base):
    __tablename__ = "user_client_access"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id", ondelete="CASCADE"), primary_key=True)
    granted_by: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    granted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped["User"] = relationship(foreign_keys=[user_id], back_populates="client_access")
    client: Mapped["Client"] = relationship(back_populates="user_access")
    granted_by_user: Mapped["User"] = relationship(foreign_keys=[granted_by], back_populates="granted_access")


class ServerAccess(Base):
    __tablename__ = "server_access"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id", ondelete="CASCADE"))
    server_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    granted_by: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    granted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("client_id", "server_id", "user_id", name="uq_server_access"),
        Index("ix_server_access_user", "user_id"),
        Index("ix_server_access_server", "server_id"),
    )

    client: Mapped["Client"] = relationship(back_populates="server_access")
    user: Mapped["User"] = relationship(foreign_keys=[user_id], back_populates="server_access")
    granted_by_user: Mapped["User"] = relationship(foreign_keys=[granted_by], back_populates="granted_server_access")


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    client_id: Mapped[int | None] = mapped_column(ForeignKey("clients.id", ondelete="SET NULL"), index=True)
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    resource_type: Mapped[str | None] = mapped_column(String(50))
    resource_id: Mapped[int | None] = mapped_column(BigInteger)
    details: Mapped[dict | None] = mapped_column(JSONB)
    ip_address: Mapped[str | None] = mapped_column(INET)
    success: Mapped[bool] = mapped_column(Boolean, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)


class BotFSMState(Base):
    __tablename__ = "bot_fsm_state"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    chat_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    state_data: Mapped[dict] = mapped_column(JSONB, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class UserMessage(Base):
    __tablename__ = "user_messages"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    chat_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    message_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    message_type: Mapped[str | None] = mapped_column(String(50))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TrafficAlertConfig(Base):
    __tablename__ = "traffic_alert_config"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id", ondelete="CASCADE"), unique=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    alert_percent: Mapped[int] = mapped_column(Integer, default=80, nullable=False)
    last_check: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    client: Mapped["Client"] = relationship(back_populates="traffic_config")


class BotAdmin(Base):
    __tablename__ = "bot_admins"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True)
    added_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped["User"] = relationship(foreign_keys=[user_id])
    added_by_user: Mapped["User"] = relationship(foreign_keys=[added_by], back_populates="added_admins")
