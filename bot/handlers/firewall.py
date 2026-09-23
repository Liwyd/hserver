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
from bot.states import FirewallCreateStates
from bot.utils.callbacks import (
    CallbackAreas,
    CallbackSteps,
    CallbackTasks,
    create_callback,
    parse_callback,
)
from bot.utils.formatters import format_firewall_info
from bot.utils.validators import validate_remark

router = Router()


@router.callback_query(F.data.startswith(f"{CallbackAreas.FIREWALL}:{CallbackTasks.LIST}"))
async def firewall_list(callback: CallbackQuery):
    cb = parse_callback(callback.data)
    client_id = cb.target_id
    await show_firewall_list(callback, client_id)


async def show_firewall_list(callback: CallbackQuery, client_id: int):
    async with db.session() as session:
        client_repo = ClientRepository(session)
        client = await client_repo.get_by_id(client_id)
        if not client:
            await callback.answer("🔍❌ Not found [client].", show_alert=True)
            return

        token = decrypt_token(client.api_token_encrypted)
        hetzner_client = await create_client(token)
        firewalls = await hetzner_client.list_firewalls()
        await close_client(hetzner_client)

    builder = InlineKeyboardBuilder()
    for fw in firewalls:
        builder.button(
            text=fw.name,
            callback_data=create_callback(CallbackAreas.FIREWALL, CallbackTasks.INFO, "", 0, 0, fw.id, str(client_id)),
        )
    builder.adjust(1)

    builder.row(
        InlineKeyboardButton(
            text="+ Create Firewall",
            callback_data=create_callback(
                CallbackAreas.FIREWALL, CallbackTasks.CREATE, CallbackSteps.REMARK, 0, 0, client_id
            ),
        ),
        InlineKeyboardButton(text="🔙 Back", callback_data=create_callback(CallbackAreas.CLIENT, CallbackTasks.LIST)),
    )

    text = "🛡 Firewalls Menu\n👇 Select an action from the menu below."
    await callback.message.edit_text(text, reply_markup=builder.as_markup())
    await callback.answer()


@router.callback_query(F.data.startswith(f"{CallbackAreas.FIREWALL}:{CallbackTasks.INFO}"))
async def firewall_info(callback: CallbackQuery):
    cb = parse_callback(callback.data)
    firewall_id = cb.target_id
    client_id = int(cb.extra) if cb.extra else 0

    async with db.session() as session:
        client_repo = ClientRepository(session)
        client = await client_repo.get_by_id(client_id)
        if not client:
            await callback.answer("🔍❌ Not found [client].", show_alert=True)
            return

        token = decrypt_token(client.api_token_encrypted)
        hetzner_client = await create_client(token)
        firewall = await hetzner_client.get_firewall(firewall_id)
        await close_client(hetzner_client)

    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="✏️ Change Remark",
            callback_data=create_callback(
                CallbackAreas.FIREWALL, CallbackTasks.EDIT, CallbackSteps.REMARK, 0, 0, firewall_id, str(client_id)
            ),
        ),
    )
    builder.row(
        InlineKeyboardButton(
            text="🔗 Apply to Servers",
            callback_data=create_callback(
                CallbackAreas.FIREWALL, CallbackTasks.ACTION, "apply", 0, 0, firewall_id, str(client_id)
            ),
        ),
        InlineKeyboardButton(
            text="❌ Remove from Servers",
            callback_data=create_callback(
                CallbackAreas.FIREWALL, CallbackTasks.ACTION, "remove", 0, 0, firewall_id, str(client_id)
            ),
        ),
    )
    builder.row(
        InlineKeyboardButton(
            text="🗑 Delete Firewall",
            callback_data=create_callback(
                CallbackAreas.FIREWALL,
                CallbackTasks.DELETE,
                CallbackSteps.CONFIRMATION,
                0,
                0,
                firewall_id,
                str(client_id),
            ),
        ),
    )
    builder.row(
        InlineKeyboardButton(
            text="🔙 Back",
            callback_data=create_callback(CallbackAreas.FIREWALL, CallbackTasks.LIST, "", 0, 0, client_id),
        ),
    )

    text = format_firewall_info(firewall)
    await callback.message.edit_text(text, reply_markup=builder.as_markup())
    await callback.answer()


@router.callback_query(F.data.startswith(f"{CallbackAreas.FIREWALL}:{CallbackTasks.CREATE}:{CallbackSteps.REMARK}"))
async def firewall_create_remark(callback: CallbackQuery, state: FSMContext):
    cb = parse_callback(callback.data)
    await state.set_state(FirewallCreateStates.waiting_remark)
    await state.update_data(client_id=cb.target_id)
    await callback.message.edit_text("✏️ Enter a remark for the firewall:")
    await callback.answer()


@router.message(FirewallCreateStates.waiting_remark)
async def firewall_create_remark_received(message: Message, state: FSMContext):
    valid, _ = validate_remark(message.text)
    if not valid:
        await message.answer(
            "⚠️❌ Invalid remark format. 🔍 Please enter a valid remark without special characters and space."
        )
        return

    data = await state.get_data()
    client_id = data["client_id"]

    async with db.session() as session:
        client_repo = ClientRepository(session)
        client = await client_repo.get_by_id(client_id)
        token = decrypt_token(client.api_token_encrypted)
        hetzner_client = await create_client(token)

        try:
            firewall = await hetzner_client.create_firewall(message.text)
            await close_client(hetzner_client)

            audit_repo = AuditLogRepository(session)
            await audit_repo.log(
                action="firewall_create",
                success=True,
                client_id=client_id,
                resource_type="firewall",
                resource_id=firewall.id,
                details={"name": message.text},
            )

            await message.answer("🎉✅ Firewall created successfully.")
        except Exception as e:
            await close_client(hetzner_client)
            await message.answer(f"⚠️❌ Firewall creation failed: {e!s}")

    await state.clear()


@router.callback_query(F.data.startswith(f"{CallbackAreas.FIREWALL}:{CallbackTasks.ACTION}:apply"))
async def firewall_apply(callback: CallbackQuery):
    cb = parse_callback(callback.data)
    firewall_id = cb.target_id
    client_id = int(cb.extra) if cb.extra else 0

    async with db.session() as session:
        client_repo = ClientRepository(session)
        client = await client_repo.get_by_id(client_id)
        token = decrypt_token(client.api_token_encrypted)
        hetzner_client = await create_client(token)
        servers = await hetzner_client.list_servers()
        firewall = await hetzner_client.get_firewall(firewall_id)
        await close_client(hetzner_client)

    applied_server_ids = {r.get("server", {}).get("id") for r in firewall.applied_to if r.get("server")}

    builder = InlineKeyboardBuilder()
    for server in servers:
        is_applied = server.id in applied_server_ids
        prefix = "✅ " if is_applied else "+ "
        builder.button(
            text=f"{prefix}{server.name} [{server.status}]",
            callback_data=create_callback(
                CallbackAreas.FIREWALL,
                CallbackTasks.ACTION,
                "apply_toggle",
                0,
                1 if is_applied else 0,
                server.id,
                f"{firewall_id}:{client_id}",
            ),
        )
    builder.adjust(1)
    builder.row(
        InlineKeyboardButton(
            text="🔙 Back",
            callback_data=create_callback(
                CallbackAreas.FIREWALL, CallbackTasks.INFO, "", 0, 0, firewall_id, str(client_id)
            ),
        )
    )

    await callback.message.edit_text("🔗 Select servers to apply/remove firewall:", reply_markup=builder.as_markup())
    await callback.answer()


@router.callback_query(F.data.startswith(f"{CallbackAreas.FIREWALL}:{CallbackTasks.ACTION}:apply_toggle"))
async def firewall_apply_toggle(callback: CallbackQuery):
    cb = parse_callback(callback.data)
    server_id = cb.target_id
    firewall_id, client_id = map(int, cb.extra.split(":"))

    async with db.session() as session:
        client_repo = ClientRepository(session)
        client = await client_repo.get_by_id(client_id)
        token = decrypt_token(client.api_token_encrypted)
        hetzner_client = await create_client(token)

        try:
            if cb.approve == 1:
                await hetzner_client.remove_firewall_from_resources(firewall_id, [{"server": {"id": server_id}}])
                action = "firewall_remove_from_server"
            else:
                await hetzner_client.apply_firewall_to_resources(firewall_id, [{"server": {"id": server_id}}])
                action = "firewall_apply_to_server"
            await close_client(hetzner_client)

            audit_repo = AuditLogRepository(session)
            await audit_repo.log(
                action=action,
                success=True,
                client_id=client_id,
                resource_type="firewall",
                resource_id=firewall_id,
                details={"server_id": server_id},
            )

            await callback.answer("🎉✅ Updated successfully.")
        except Exception as e:
            await close_client(hetzner_client)
            await callback.answer(f"⚠️❌ Failed: {e!s}", show_alert=True)

    await firewall_apply(callback)


@router.callback_query(F.data.startswith(f"{CallbackAreas.FIREWALL}:{CallbackTasks.ACTION}:remove"))
async def firewall_remove(callback: CallbackQuery):
    await firewall_apply(callback)


@router.callback_query(
    F.data.startswith(f"{CallbackAreas.FIREWALL}:{CallbackTasks.DELETE}:{CallbackSteps.CONFIRMATION}")
)
async def firewall_delete_confirm(callback: CallbackQuery):
    cb = parse_callback(callback.data)
    firewall_id = cb.target_id
    client_id = int(cb.extra) if cb.extra else 0

    if cb.approve == 1:
        async with db.session() as session:
            client_repo = ClientRepository(session)
            client = await client_repo.get_by_id(client_id)
            token = decrypt_token(client.api_token_encrypted)
            hetzner_client = await create_client(token)

            try:
                await hetzner_client.delete_firewall(firewall_id)
                await close_client(hetzner_client)

                audit_repo = AuditLogRepository(session)
                await audit_repo.log(
                    action="firewall_delete",
                    success=True,
                    client_id=client_id,
                    resource_type="firewall",
                    resource_id=firewall_id,
                )

                await callback.message.edit_text("🎉✅ Firewall deleted successfully.")
            except Exception as e:
                await close_client(hetzner_client)
                await callback.message.edit_text(f"⚠️❌ Deletion failed: {e!s}")
    else:
        await callback.message.edit_text("🚫❌ Action cancelled. ↩️ Go back to the previous menu.")

    await callback.answer()
    await show_firewall_list(callback, client_id)


@router.callback_query(F.data.startswith(f"{CallbackAreas.FIREWALL}:{CallbackTasks.EDIT}:{CallbackSteps.REMARK}"))
async def firewall_edit_remark(callback: CallbackQuery, state: FSMContext):
    cb = parse_callback(callback.data)
    await state.set_state(FirewallCreateStates.waiting_remark)
    await state.update_data(firewall_id=cb.target_id, client_id=int(cb.extra) if cb.extra else 0, editing=True)
    await callback.message.edit_text("✏️ Enter new remark for the firewall:")
    await callback.answer()


@router.message(FirewallCreateStates.waiting_remark)
async def firewall_edit_remark_received(message: Message, state: FSMContext):
    data = await state.get_data()
    if not data.get("editing"):
        return

    valid, _ = validate_remark(message.text)
    if not valid:
        await message.answer(
            "⚠️❌ Invalid remark format. 🔍 Please enter a valid remark without special characters and space."
        )
        return

    firewall_id = data["firewall_id"]
    client_id = data["client_id"]

    async with db.session() as session:
        client_repo = ClientRepository(session)
        client = await client_repo.get_by_id(client_id)
        token = decrypt_token(client.api_token_encrypted)
        hetzner_client = await create_client(token)

        try:
            await hetzner_client.update_firewall(firewall_id, name=message.text)
            await close_client(hetzner_client)

            audit_repo = AuditLogRepository(session)
            await audit_repo.log(
                action="firewall_rename",
                success=True,
                client_id=client_id,
                resource_type="firewall",
                resource_id=firewall_id,
                details={"new_name": message.text},
            )

            await message.answer("🎉✅ Firewall remark updated successfully.")
        except Exception as e:
            await close_client(hetzner_client)
            await message.answer(f"⚠️❌ Failed to update remark: {e!s}")

    await state.clear()
