from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.database.base import db
from bot.database.repositories import (
    AuditLogRepository,
    ClientRepository,
)
from bot.encryption import decrypt_token
from bot.hetzner.client import close_client, create_client
from bot.states import SnapshotCreateStates
from bot.utils.callbacks import (
    CallbackAreas,
    CallbackSteps,
    CallbackTasks,
    create_callback,
    parse_callback,
)
from bot.utils.formatters import format_snapshot_info
from bot.utils.validators import validate_remark

router = Router()


@router.callback_query(F.data.startswith(f"{CallbackAreas.SNAPSHOT}:{CallbackTasks.LIST}"))
async def snapshot_list(callback: CallbackQuery):
    cb = parse_callback(callback.data)
    client_id = cb.target_id
    await show_snapshot_list(callback, client_id)


async def show_snapshot_list(callback: CallbackQuery, client_id: int):
    async with db.session() as session:
        client_repo = ClientRepository(session)
        client = await client_repo.get_by_id(client_id)
        if not client:
            await callback.answer("🔍❌ Not found [client].", show_alert=True)
            return

        token = decrypt_token(client.api_token_encrypted)
        hetzner_client = await create_client(token)
        snapshots = await hetzner_client.list_snapshots()
        await close_client(hetzner_client)

    builder = InlineKeyboardBuilder()
    for snap in snapshots:
        builder.button(
            text=snap.name or snap.description,
            callback_data=create_callback(
                CallbackAreas.SNAPSHOT, CallbackTasks.INFO, "", 0, 0, snap.id, str(client_id)
            ),
        )
    builder.adjust(1)

    builder.row(
        InlineKeyboardButton(
            text="+ Create Snapshot",
            callback_data=create_callback(
                CallbackAreas.SNAPSHOT, CallbackTasks.CREATE, CallbackSteps.REMARK, 0, 0, client_id
            ),
        ),
        InlineKeyboardButton(text="🔙 Back", callback_data=create_callback(CallbackAreas.CLIENT, CallbackTasks.LIST)),
    )

    text = "📸 Snapshots Menu\n👇 Select an action from the menu below."
    await callback.message.edit_text(text, reply_markup=builder.as_markup())
    await callback.answer()


@router.callback_query(F.data.startswith(f"{CallbackAreas.SNAPSHOT}:{CallbackTasks.INFO}"))
async def snapshot_info(callback: CallbackQuery):
    cb = parse_callback(callback.data)
    snapshot_id = cb.target_id
    client_id = int(cb.extra) if cb.extra else 0

    async with db.session() as session:
        client_repo = ClientRepository(session)
        client = await client_repo.get_by_id(client_id)
        if not client:
            await callback.answer("🔍❌ Not found [client].", show_alert=True)
            return

        token = decrypt_token(client.api_token_encrypted)
        hetzner_client = await create_client(token)
        snapshot = await hetzner_client.get_snapshot(snapshot_id)
        await close_client(hetzner_client)

    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="✏️ Change Remark",
            callback_data=create_callback(
                CallbackAreas.SNAPSHOT, CallbackTasks.EDIT, CallbackSteps.REMARK, 0, 0, snapshot_id, str(client_id)
            ),
        ),
        InlineKeyboardButton(
            text="🗑 Delete Snapshot",
            callback_data=create_callback(
                CallbackAreas.SNAPSHOT,
                CallbackTasks.DELETE,
                CallbackSteps.CONFIRMATION,
                0,
                0,
                snapshot_id,
                str(client_id),
            ),
        ),
    )
    builder.row(
        InlineKeyboardButton(
            text="🔙 Back",
            callback_data=create_callback(CallbackAreas.SNAPSHOT, CallbackTasks.LIST, "", 0, 0, client_id),
        ),
    )

    text = format_snapshot_info(snapshot)
    await callback.message.edit_text(text, reply_markup=builder.as_markup())
    await callback.answer()


@router.callback_query(F.data.startswith(f"{CallbackAreas.SNAPSHOT}:{CallbackTasks.CREATE}:{CallbackSteps.REMARK}"))
async def snapshot_create_remark(callback: CallbackQuery, state: FSMContext):
    cb = parse_callback(callback.data)
    await state.set_state(SnapshotCreateStates.waiting_remark)
    await state.update_data(client_id=cb.target_id)
    await callback.message.edit_text("✏️ Enter a remark for the snapshot:")
    await callback.answer()


@router.message(SnapshotCreateStates.waiting_remark)
async def snapshot_create_remark_received(message: Message, state: FSMContext):
    valid, _ = validate_remark(message.text)
    if not valid:
        await message.answer(
            "⚠️❌ Invalid remark format. 🔍 Please enter a valid remark without special characters and space."
        )
        return

    await state.update_data(remark=message.text)
    await state.set_state(SnapshotCreateStates.waiting_server)

    data = await state.get_data()
    client_id = data["client_id"]

    async with db.session() as session:
        client_repo = ClientRepository(session)
        client = await client_repo.get_by_id(client_id)
        token = decrypt_token(client.api_token_encrypted)
        hetzner_client = await create_client(token)
        servers = await hetzner_client.list_servers()
        await close_client(hetzner_client)

    builder = InlineKeyboardBuilder()
    for server in servers:
        builder.button(
            text=f"{server.name} [{server.status}]",
            callback_data=create_callback(
                CallbackAreas.SNAPSHOT, CallbackTasks.CREATE, CallbackSteps.SERVER, 0, 0, server.id, str(client_id)
            ),
        )
    builder.adjust(1)
    builder.row(
        InlineKeyboardButton(
            text="🔙 Back",
            callback_data=create_callback(CallbackAreas.SNAPSHOT, CallbackTasks.LIST, "", 0, 0, client_id),
        )
    )

    await message.answer("🖥 Select a server to create snapshot from:", reply_markup=builder.as_markup())


@router.callback_query(F.data.startswith(f"{CallbackAreas.SNAPSHOT}:{CallbackTasks.CREATE}:{CallbackSteps.SERVER}"))
async def snapshot_create_server(callback: CallbackQuery, state: FSMContext):
    cb = parse_callback(callback.data)
    server_id = cb.target_id
    client_id = int(cb.extra) if cb.extra else 0

    data = await state.get_data()
    remark = data["remark"]

    async with db.session() as session:
        client_repo = ClientRepository(session)
        client = await client_repo.get_by_id(client_id)
        token = decrypt_token(client.api_token_encrypted)
        hetzner_client = await create_client(token)

        try:
            await hetzner_client.create_snapshot(server_id, remark)
            await close_client(hetzner_client)

            audit_repo = AuditLogRepository(session)
            await audit_repo.log(
                action="snapshot_create",
                success=True,
                client_id=client_id,
                resource_type="snapshot",
                resource_id=server_id,
                details={"remark": remark, "server_id": server_id},
            )

            await callback.message.edit_text("🎉✅ Snapshot created successfully.")
        except Exception as e:
            await close_client(hetzner_client)
            await callback.message.edit_text(f"⚠️❌ Snapshot creation failed: {e!s}")

    await state.clear()
    await callback.answer()
    await show_snapshot_list(callback, client_id)


@router.callback_query(F.data.startswith(f"{CallbackAreas.SNAPSHOT}:{CallbackTasks.EDIT}:{CallbackSteps.REMARK}"))
async def snapshot_edit_remark(callback: CallbackQuery, state: FSMContext):
    cb = parse_callback(callback.data)
    await state.set_state(SnapshotCreateStates.waiting_remark)
    await state.update_data(snapshot_id=cb.target_id, client_id=int(cb.extra) if cb.extra else 0, editing=True)
    await callback.message.edit_text("✏️ Enter new remark for the snapshot:")
    await callback.answer()


@router.message(SnapshotCreateStates.waiting_remark)
async def snapshot_edit_remark_received(message: Message, state: FSMContext):
    data = await state.get_data()
    if not data.get("editing"):
        return

    valid, _ = validate_remark(message.text)
    if not valid:
        await message.answer(
            "⚠️❌ Invalid remark format. 🔍 Please enter a valid remark without special characters and space."
        )
        return

    snapshot_id = data["snapshot_id"]
    client_id = data["client_id"]

    async with db.session() as session:
        client_repo = ClientRepository(session)
        client = await client_repo.get_by_id(client_id)
        token = decrypt_token(client.api_token_encrypted)
        hetzner_client = await create_client(token)

        try:
            await hetzner_client.change_snapshot_description(snapshot_id, message.text)
            await close_client(hetzner_client)

            audit_repo = AuditLogRepository(session)
            await audit_repo.log(
                action="snapshot_rename",
                success=True,
                client_id=client_id,
                resource_type="snapshot",
                resource_id=snapshot_id,
                details={"new_name": message.text},
            )

            await message.answer("🎉✅ Snapshot remark updated successfully.")
        except Exception as e:
            await close_client(hetzner_client)
            await message.answer(f"⚠️❌ Failed to update remark: {e!s}")

    await state.clear()


@router.callback_query(
    F.data.startswith(f"{CallbackAreas.SNAPSHOT}:{CallbackTasks.DELETE}:{CallbackSteps.CONFIRMATION}")
)
async def snapshot_delete_confirm(callback: CallbackQuery):
    cb = parse_callback(callback.data)
    snapshot_id = cb.target_id
    client_id = int(cb.extra) if cb.extra else 0

    if cb.approve == 1:
        async with db.session() as session:
            client_repo = ClientRepository(session)
            client = await client_repo.get_by_id(client_id)
            token = decrypt_token(client.api_token_encrypted)
            hetzner_client = await create_client(token)

            try:
                await hetzner_client.delete_snapshot(snapshot_id)
                await close_client(hetzner_client)

                audit_repo = AuditLogRepository(session)
                await audit_repo.log(
                    action="snapshot_delete",
                    success=True,
                    client_id=client_id,
                    resource_type="snapshot",
                    resource_id=snapshot_id,
                )

                await callback.message.edit_text("🎉✅ Snapshot deleted successfully.")
            except Exception as e:
                await close_client(hetzner_client)
                await callback.message.edit_text(f"⚠️❌ Snapshot deletion failed: {e!s}")
    else:
        await callback.message.edit_text("🚫❌ Action cancelled. ↩️ Go back to the previous menu.")

    await callback.answer()
    await show_snapshot_list(callback, client_id)
