"""Initial migration

Revision ID: 001
Revises:
Create Date: 2024-01-01 00:00:00.000000

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("telegram_id", sa.BigInteger(), nullable=False),
        sa.Column("username", sa.String(length=255), nullable=True),
        sa.Column("first_name", sa.String(length=255), nullable=True),
        sa.Column("last_name", sa.String(length=255), nullable=True),
        sa.Column("role", sa.String(length=50), nullable=False, server_default="user"),
        sa.Column("is_bot_admin", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_users_telegram_id"), "users", ["telegram_id"], unique=True)
    op.create_index(op.f("ix_users_role"), "users", ["role"], unique=False)

    op.create_table(
        "clients",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("remark", sa.String(length=255), nullable=False),
        sa.Column("api_token_encrypted", postgresql.BYTEA(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("owner_id", sa.BigInteger(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("remark"),
    )
    op.create_index(op.f("ix_clients_owner"), "clients", ["owner_id"], unique=False)

    op.create_table(
        "user_client_access",
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("client_id", sa.BigInteger(), nullable=False),
        sa.Column("granted_by", sa.BigInteger(), nullable=True),
        sa.Column("granted_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["client_id"], ["clients.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["granted_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id", "client_id"),
    )
    op.create_index(op.f("ix_user_client_access_user"), "user_client_access", ["user_id"], unique=False)

    op.create_table(
        "server_access",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("client_id", sa.BigInteger(), nullable=False),
        sa.Column("server_id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("granted_by", sa.BigInteger(), nullable=True),
        sa.Column("granted_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["client_id"], ["clients.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["granted_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("client_id", "server_id", "user_id", name="uq_server_access"),
    )
    op.create_index(op.f("ix_server_access_user"), "server_access", ["user_id"], unique=False)
    op.create_index(op.f("ix_server_access_server"), "server_access", ["server_id"], unique=False)

    op.create_table(
        "audit_logs",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=True),
        sa.Column("client_id", sa.BigInteger(), nullable=True),
        sa.Column("action", sa.String(length=100), nullable=False),
        sa.Column("resource_type", sa.String(length=50), nullable=True),
        sa.Column("resource_id", sa.BigInteger(), nullable=True),
        sa.Column("details", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("ip_address", postgresql.INET(), nullable=True),
        sa.Column("success", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["client_id"], ["clients.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_audit_logs_user"), "audit_logs", ["user_id"], unique=False)
    op.create_index(op.f("ix_audit_logs_client"), "audit_logs", ["client_id"], unique=False)
    op.create_index(op.f("ix_audit_logs_created"), "audit_logs", ["created_at"], unique=False)

    op.create_table(
        "bot_fsm_state",
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("chat_id", sa.BigInteger(), nullable=False),
        sa.Column("state_data", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id"),
    )

    op.create_table(
        "user_messages",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("chat_id", sa.BigInteger(), nullable=False),
        sa.Column("message_id", sa.BigInteger(), nullable=False),
        sa.Column("message_type", sa.String(length=50), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_user_messages_user"), "user_messages", ["user_id"], unique=False)

    op.create_table(
        "traffic_alert_config",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("client_id", sa.BigInteger(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("alert_percent", sa.Integer(), nullable=False, server_default="80"),
        sa.Column("last_check", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["client_id"], ["clients.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("client_id"),
    )

    op.create_table(
        "bot_admins",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("added_by", sa.BigInteger(), nullable=True),
        sa.Column("added_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["added_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id"),
    )


def downgrade() -> None:
    op.drop_table("bot_admins")
    op.drop_table("traffic_alert_config")
    op.drop_index(op.f("ix_user_messages_user"), table_name="user_messages")
    op.drop_table("user_messages")
    op.drop_table("bot_fsm_state")
    op.drop_index(op.f("ix_audit_logs_created"), table_name="audit_logs")
    op.drop_index(op.f("ix_audit_logs_client"), table_name="audit_logs")
    op.drop_index(op.f("ix_audit_logs_user"), table_name="audit_logs")
    op.drop_table("audit_logs")
    op.drop_index(op.f("ix_server_access_server"), table_name="server_access")
    op.drop_index(op.f("ix_server_access_user"), table_name="server_access")
    op.drop_table("server_access")
    op.drop_index(op.f("ix_user_client_access_user"), table_name="user_client_access")
    op.drop_table("user_client_access")
    op.drop_index(op.f("ix_clients_owner"), table_name="clients")
    op.drop_table("clients")
    op.drop_index(op.f("ix_users_role"), table_name="users")
    op.drop_index(op.f("ix_users_telegram_id"), table_name="users")
    op.drop_table("users")
