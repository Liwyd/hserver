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
from bot.states import PlacementGroupCreateStates
from bot.utils.callbacks import (
    CallbackAreas,
    CallbackSteps,
    CallbackTasks,
    create_callback,
    parse_callback,
)
from bot.utils.formatters import format_placement_group_info
from bot.utils.validators import validate_remark

router = Router()


@router.callback_query(F.data.startswith(f"{CallbackAreas.PLACEMENTGROUP}:{CallbackTasks.LIST}"))
async def placementgroup_list(callback: CallbackQuery):
    cb = parse_callback(callback.data)
    client_id = cb.target_id
    await show_placementgroup_list(callback, client_id)


async def show_placementgroup_list(callback: CallbackQuery, client_id: int):
    async with db.session() as session:
        client_repo = ClientRepository(session)
        client = await client_repo.get_by_id(client_id)
        if not client:
            await callback.answer("🔍❌ Not found [client].", show_alert=True)
            return

        token = decrypt_token(client.api_token_encrypted)
        hetzner_client = await create_client(token)
        pgs = await hetzner_client.list_placement_groups()
        await close_client(hetzner_client)

    builder = InlineKeyboardBuilder()
    for pg in pgs:
        builder.button(
            text=pg.name,
            callback_data=create_callback(
                CallbackAreas.PLACEMENTGROUP, CallbackTasks.INFO, "", 0, 0, pg.id, str(client_id)
            ),
        )
    builder.adjust(1)

    builder.row(
        InlineKeyboardButton(
            text="+ Create Placement Group",
            callback_data=create_callback(
                CallbackAreas.PLACEMENTGROUP, CallbackTasks.CREATE, CallbackSteps.NAME, 0, 0, client_id
            ),
        ),
        InlineKeyboardButton(text="🔙 Back", callback_data=create_callback(CallbackAreas.CLIENT, CallbackTasks.LIST)),
    )

    text = "📍 Placement Groups Menu\n👇 Select an action from the menu below."
    await callback.message.edit_text(text, reply_markup=builder.as_markup())
    await callback.answer()


@router.callback_query(F.data.startswith(f"{CallbackAreas.PLACEMENTGROUP}:{CallbackTasks.INFO}"))
async def placementgroup_info(callback: CallbackQuery):
    cb = parse_callback(callback.data)
    pg_id = cb.target_id
    client_id = int(cb.extra) if cb.extra else 0

    async with db.session() as session:
        client_repo = ClientRepository(session)
        client = await client_repo.get_by_id(client_id)
        if not client:
            await callback.answer("🔍❌ Not found [client].", show_alert=True)
            return

        token = decrypt_token(client.api_token_encrypted)
        hetzner_client = await create_client(token)
        pg = await hetzner_client.get_placement_group(pg_id)
        await close_client(hetzner_client)

    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="✏️ Change Remark",
            callback_data=create_callback(
                CallbackAreas.PLACEMENTGROUP, CallbackTasks.EDIT, CallbackSteps.REMARK, 0, 0, pg_id, str(client_id)
            ),
        ),
        InlineKeyboardButton(
            text="🗑 Delete Placement Group",
            callback_data=create_callback(
                CallbackAreas.PLACEMENTGROUP,
                CallbackTasks.DELETE,
                CallbackSteps.CONFIRMATION,
                0,
                0,
                pg_id,
                str(client_id),
            ),
        ),
    )
    builder.row(
        InlineKeyboardButton(
            text="🔙 Back",
            callback_data=create_callback(CallbackAreas.PLACEMENTGROUP, CallbackTasks.LIST, "", 0, 0, client_id),
        ),
    )

    text = format_placement_group_info(pg)
    await callback.message.edit_text(text, reply_markup=builder.as_markup())
    await callback.answer()


@router.callback_query(F.data.startswith(f"{CallbackAreas.PLACEMENTGROUP}:{CallbackTasks.CREATE}:{CallbackSteps.NAME}"))
async def placementgroup_create_name(callback: CallbackQuery, state: FSMContext):
    cb = parse_callback(callback.data)
    await state.set_state(PlacementGroupCreateStates.waiting_name)
    await state.update_data(client_id=cb.target_id)
    await callback.message.edit_text("✏️ Enter a name for the placement group:")
    await callback.answer()


@router.message(PlacementGroupCreateStates.waiting_name)
async def placementgroup_create_name_received(message: Message, state: FSMContext):
    valid, _ = validate_remark(message.text)
    if not valid:
        await message.answer(
            "⚠️❌ Invalid name format. 🔍 Please enter a valid name without special characters and space."
        )
        return

    await state.update_data(name=message.text)
    await state.set_state(PlacementGroupCreateStates.waiting_type)

    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="spread", callback_data="placementgroup:type:spread"),
    )
    await message.answer("🔗 Select type:", reply_markup=builder.as_markup())


@router.callback_query(F.data.startswith("placementgroup:type:"))
async def placementgroup_create_type(callback: CallbackQuery, state: FSMContext):
    pg_type = callback.data.split(":")[-1]
    data = await state.get_data()
    client_id = data["client_id"]

    async with db.session() as session:
        client_repo = ClientRepository(session)
        client = await client_repo.get_by_id(client_id)
        token = decrypt_token(client.api_token_encrypted)
        hetzner_client = await create_client(token)

        try:
            pg = await hetzner_client.create_placement_group(data["name"], pg_type)
            await close_client(hetzner_client)

            audit_repo = AuditLogRepository(session)
            await audit_repo.log(
                action="placementgroup_create",
                success=True,
                client_id=client_id,
                resource_type="placementgroup",
                resource_id=pg.id,
                details={"name": data["name"], "type": pg_type},
            )

            await callback.message.edit_text("🎉✅ Placement Group created successfully.")
        except Exception as e:
            await close_client(hetzner_client)
            await callback.message.edit_text(f"⚠️❌ Placement Group creation failed: {e!s}")

    await state.clear()
    await callback.answer()
    await show_placementgroup_list(callback, client_id)


@router.callback_query(
    F.data.startswith(f"{CallbackAreas.PLACEMENTGROUP}:{CallbackTasks.DELETE}:{CallbackSteps.CONFIRMATION}")
)
async def placementgroup_delete_confirm(callback: CallbackQuery):
    cb = parse_callback(callback.data)
    pg_id = cb.target_id
    client_id = int(cb.extra) if cb.extra else 0

    if cb.approve == 1:
        async with db.session() as session:
            client_repo = ClientRepository(session)
            client = await client_repo.get_by_id(client_id)
            token = decrypt_token(client.api_token_encrypted)
            hetzner_client = await create_client(token)

            try:
                await hetzner_client.delete_placement_group(pg_id)
                await close_client(hetzner_client)

                audit_repo = AuditLogRepository(session)
                await audit_repo.log(
                    action="placementgroup_delete",
                    success=True,
                    client_id=client_id,
                    resource_type="placementgroup",
                    resource_id=pg_id,
                )

                await callback.message.edit_text("🎉✅ Placement Group deleted successfully.")
            except Exception as e:
                await close_client(hetzner_client)
                await callback.message.edit_text(f"⚠️❌ Deletion failed: {e!s}")
    else:
        await callback.message.edit_text("🚫❌ Action cancelled. ↩️ Go back to the previous menu.")

    await callback.answer()
    await show_placementgroup_list(callback, client_id)


@router.callback_query(F.data.startswith(f"{CallbackAreas.PLACEMENTGROUP}:{CallbackTasks.EDIT}:{CallbackSteps.REMARK}"))
async def placementgroup_edit_remark(callback: CallbackQuery, state: FSMContext):
    cb = parse_callback(callback.data)
    await state.set_state(PlacementGroupCreateStates.waiting_name)
    await state.update_data(pg_id=cb.target_id, client_id=int(cb.extra) if cb.extra else 0, editing=True)
    await callback.message.edit_text("✏️ Enter new remark for the placement group:")
    await callback.answer()


@router.message(PlacementGroupCreateStates.waiting_name)
async def placementgroup_edit_remark_received(message: Message, state: FSMContext):
    data = await state.get_data()
    if not data.get("editing"):
        return

    valid, _ = validate_remark(message.text)
    if not valid:
        await message.answer(
            "⚠️❌ Invalid remark format. 🔍 Please enter a valid remark without special characters and space."
        )
        return

    pg_id = data["pg_id"]
    client_id = data["client_id"]

    async with db.session() as session:
        client_repo = ClientRepository(session)
        client = await client_repo.get_by_id(client_id)
        token = decrypt_token(client.api_token_encrypted)
        hetzner_client = await create_client(token)

        try:
            await hetzner_client.update_placement_group(pg_id, name=message.text)
            await close_client(hetzner_client)

            audit_repo = AuditLogRepository(session)
            await audit_repo.log(
                action="placementgroup_rename",
                success=True,
                client_id=client_id,
                resource_type="placementgroup",
                resource_id=pg_id,
                details={"new_name": message.text},
            )

            await message.answer("🎉✅ Placement Group remark updated successfully.")
        except Exception as e:
            await close_client(hetzner_client)
            await message.answer(f"⚠️❌ Failed to update remark: {e!s}")

    await state.clear()
