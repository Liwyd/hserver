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
from bot.states import SSHKeyCreateStates
from bot.utils.callbacks import (
    CallbackAreas,
    CallbackSteps,
    CallbackTasks,
    create_callback,
    parse_callback,
)
from bot.utils.formatters import format_ssh_key_info
from bot.utils.validators import validate_remark, validate_ssh_public_key

router = Router()


@router.callback_query(F.data.startswith(f"{CallbackAreas.SSHKEY}:{CallbackTasks.LIST}"))
async def sshkey_list(callback: CallbackQuery):
    cb = parse_callback(callback.data)
    client_id = cb.target_id
    await show_sshkey_list(callback, client_id)


async def show_sshkey_list(callback: CallbackQuery, client_id: int):
    async with db.session() as session:
        client_repo = ClientRepository(session)
        client = await client_repo.get_by_id(client_id)
        if not client:
            await callback.answer("🔍❌ Not found [client].", show_alert=True)
            return

        token = decrypt_token(client.api_token_encrypted)
        hetzner_client = await create_client(token)
        keys = await hetzner_client.list_ssh_keys()
        await close_client(hetzner_client)

    builder = InlineKeyboardBuilder()
    for key in keys:
        builder.button(
            text=key.name,
            callback_data=create_callback(CallbackAreas.SSHKEY, CallbackTasks.INFO, "", 0, 0, key.id, str(client_id)),
        )
    builder.adjust(1)

    builder.row(
        InlineKeyboardButton(
            text="➕ Add SSH Key",
            callback_data=create_callback(
                CallbackAreas.SSHKEY, CallbackTasks.CREATE, CallbackSteps.NAME, 0, 0, client_id
            ),
        ),
        InlineKeyboardButton(text="🔙 Back", callback_data=create_callback(CallbackAreas.CLIENT, CallbackTasks.LIST)),
    )

    text = "🔐 SSH Keys Menu\n👇 Select an action from the menu below."
    await callback.message.edit_text(text, reply_markup=builder.as_markup())
    await callback.answer()


@router.callback_query(F.data.startswith(f"{CallbackAreas.SSHKEY}:{CallbackTasks.INFO}"))
async def sshkey_info(callback: CallbackQuery):
    cb = parse_callback(callback.data)
    key_id = cb.target_id
    client_id = int(cb.extra) if cb.extra else 0

    async with db.session() as session:
        client_repo = ClientRepository(session)
        client = await client_repo.get_by_id(client_id)
        if not client:
            await callback.answer("🔍❌ Not found [client].", show_alert=True)
            return

        token = decrypt_token(client.api_token_encrypted)
        hetzner_client = await create_client(token)
        key = await hetzner_client.get_ssh_key(key_id)
        await close_client(hetzner_client)

    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="✏️ Change Remark",
            callback_data=create_callback(
                CallbackAreas.SSHKEY, CallbackTasks.EDIT, CallbackSteps.REMARK, 0, 0, key_id, str(client_id)
            ),
        ),
        InlineKeyboardButton(
            text="🗑 Delete SSH Key",
            callback_data=create_callback(
                CallbackAreas.SSHKEY, CallbackTasks.DELETE, CallbackSteps.CONFIRMATION, 0, 0, key_id, str(client_id)
            ),
        ),
    )
    builder.row(
        InlineKeyboardButton(
            text="🔙 Back", callback_data=create_callback(CallbackAreas.SSHKEY, CallbackTasks.LIST, "", 0, 0, client_id)
        ),
    )

    text = format_ssh_key_info(key)
    await callback.message.edit_text(text, reply_markup=builder.as_markup())
    await callback.answer()


@router.callback_query(F.data.startswith(f"{CallbackAreas.SSHKEY}:{CallbackTasks.CREATE}:{CallbackSteps.NAME}"))
async def sshkey_create_name(callback: CallbackQuery, state: FSMContext):
    cb = parse_callback(callback.data)
    await state.set_state(SSHKeyCreateStates.waiting_name)
    await state.update_data(client_id=cb.target_id)
    await callback.message.edit_text("✏️ Enter a name for the SSH key:")
    await callback.answer()


@router.message(SSHKeyCreateStates.waiting_name)
async def sshkey_create_name_received(message: Message, state: FSMContext):
    valid, error = validate_remark(message.text)
    if not valid:
        await message.answer(
            "⚠️❌ Invalid name format. 🔍 Please enter a valid name without special characters and space."
        )
        return

    await state.update_data(name=message.text)
    await state.set_state(SSHKeyCreateStates.waiting_public_key)
    await message.answer("🔑 Paste the public key (or path to .pub file):")


@router.message(SSHKeyCreateStates.waiting_public_key)
async def sshkey_create_key_received(message: Message, state: FSMContext):
    valid, error = validate_ssh_public_key(message.text)
    if not valid:
        await message.answer(f"⚠️❌ {error}")
        return

    data = await state.get_data()
    client_id = data["client_id"]

    async with db.session() as session:
        client_repo = ClientRepository(session)
        client = await client_repo.get_by_id(client_id)
        token = decrypt_token(client.api_token_encrypted)
        hetzner_client = await create_client(token)

        try:
            key = await hetzner_client.create_ssh_key(data["name"], message.text.strip())
            await close_client(hetzner_client)

            audit_repo = AuditLogRepository(session)
            await audit_repo.log(
                action="sshkey_create",
                success=True,
                client_id=client_id,
                resource_type="sshkey",
                resource_id=key.id,
                details={"name": data["name"]},
            )

            await message.answer("🎉✅ SSH Key added successfully.")
        except Exception as e:
            await close_client(hetzner_client)
            await message.answer(f"⚠️❌ SSH Key creation failed: {e!s}")

    await state.clear()


@router.callback_query(F.data.startswith(f"{CallbackAreas.SSHKEY}:{CallbackTasks.DELETE}:{CallbackSteps.CONFIRMATION}"))
async def sshkey_delete_confirm(callback: CallbackQuery):
    cb = parse_callback(callback.data)
    key_id = cb.target_id
    client_id = int(cb.extra) if cb.extra else 0

    if cb.approve == 1:
        async with db.session() as session:
            client_repo = ClientRepository(session)
            client = await client_repo.get_by_id(client_id)
            token = decrypt_token(client.api_token_encrypted)
            hetzner_client = await create_client(token)

            try:
                await hetzner_client.delete_ssh_key(key_id)
                await close_client(hetzner_client)

                audit_repo = AuditLogRepository(session)
                await audit_repo.log(
                    action="sshkey_delete",
                    success=True,
                    client_id=client_id,
                    resource_type="sshkey",
                    resource_id=key_id,
                )

                await callback.message.edit_text("🎉✅ SSH Key deleted successfully.")
            except Exception as e:
                await close_client(hetzner_client)
                await callback.message.edit_text(f"⚠️❌ Deletion failed: {e!s}")
    else:
        await callback.message.edit_text("🚫❌ Action cancelled. ↩️ Go back to the previous menu.")

    await callback.answer()
    await show_sshkey_list(callback, client_id)


@router.callback_query(F.data.startswith(f"{CallbackAreas.SSHKEY}:{CallbackTasks.EDIT}:{CallbackSteps.REMARK}"))
async def sshkey_edit_remark(callback: CallbackQuery, state: FSMContext):
    cb = parse_callback(callback.data)
    await state.set_state(SSHKeyCreateStates.waiting_name)
    await state.update_data(key_id=cb.target_id, client_id=int(cb.extra) if cb.extra else 0, editing=True)
    await callback.message.edit_text("✏️ Enter new remark for the SSH key:")
    await callback.answer()


@router.message(SSHKeyCreateStates.waiting_name)
async def sshkey_edit_remark_received(message: Message, state: FSMContext):
    data = await state.get_data()
    if not data.get("editing"):
        return

    valid, error = validate_remark(message.text)
    if not valid:
        await message.answer(
            "⚠️❌ Invalid remark format. 🔍 Please enter a valid remark without special characters and space."
        )
        return

    key_id = data["key_id"]
    client_id = data["client_id"]

    async with db.session() as session:
        client_repo = ClientRepository(session)
        client = await client_repo.get_by_id(client_id)
        token = decrypt_token(client.api_token_encrypted)
        hetzner_client = await create_client(token)

        try:
            await hetzner_client.update_ssh_key(key_id, name=message.text)
            await close_client(hetzner_client)

            audit_repo = AuditLogRepository(session)
            await audit_repo.log(
                action="sshkey_rename",
                success=True,
                client_id=client_id,
                resource_type="sshkey",
                resource_id=key_id,
                details={"new_name": message.text},
            )

            await message.answer("🎉✅ SSH Key remark updated successfully.")
        except Exception as e:
            await close_client(hetzner_client)
            await message.answer(f"⚠️❌ Failed to update remark: {e!s}")

    await state.clear()
