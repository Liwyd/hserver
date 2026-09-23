import hashlib

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.database.base import db
from bot.database.repositories import (
    AuditLogRepository,
    ClientRepository,
    UserRepository,
)
from bot.encryption import encrypt_token
from bot.hetzner.client import close_client, create_client
from bot.states import ClientCreateStates, ClientSettingsStates
from bot.utils.callbacks import (
    CallbackAreas,
    CallbackSteps,
    CallbackTasks,
    create_callback,
    parse_callback,
)
from bot.utils.formatters import format_client_button
from bot.utils.validators import validate_remark

router = Router()


@router.callback_query(F.data.startswith(f"{CallbackAreas.CLIENT}:{CallbackTasks.LIST}"))
async def client_list(callback: CallbackQuery):
    await show_client_menu(callback)


async def show_client_menu(callback: CallbackQuery):
    user = callback.data.get("user") if hasattr(callback.data, "get") else None

    async with db.session() as session:
        client_repo = ClientRepository(session)
        user_repo = UserRepository(session)

        user = await user_repo.get_by_telegram_id(callback.from_user.id)
        clients = await client_repo.list_for_user(user)

        builder = InlineKeyboardBuilder()

        for client in clients:
            builder.button(
                text=format_client_button(client),
                callback_data=create_callback(CallbackAreas.CLIENT, CallbackTasks.INFO, "", 0, 0, client.id),
            )

        builder.adjust(2)

        builder.row(InlineKeyboardButton(text="🔙 Back", callback_data="home:back"))

        text = "👥 Clients Menu\n👇 Select an action from the menu below."
        await callback.message.edit_text(text, reply_markup=builder.as_markup())
        await callback.answer()


@router.callback_query(F.data.startswith(f"{CallbackAreas.CLIENT}:{CallbackTasks.INFO}"))
async def client_info(callback: CallbackQuery):
    cb = parse_callback(callback.data)
    client_id = cb.target_id

    async with db.session() as session:
        client_repo = ClientRepository(session)
        client = await client_repo.get_by_id(client_id)

        if not client:
            await callback.answer("🔍❌ Not found [client].", show_alert=True)
            return

        token_preview = "••••••••"  # Spoiler text

        builder = InlineKeyboardBuilder()
        builder.row(
            InlineKeyboardButton(
                text="✏️ Change Remark",
                callback_data=create_callback(
                    CallbackAreas.CLIENT, CallbackTasks.EDIT, CallbackSteps.REMARK, 0, 0, client_id
                ),
            ),
            InlineKeyboardButton(
                text="🔑 Change Secret",
                callback_data=create_callback(
                    CallbackAreas.CLIENT, CallbackTasks.EDIT, CallbackSteps.TOKEN, 0, 0, client_id
                ),
            ),
        )
        builder.row(
            InlineKeyboardButton(
                text="❌ Remove Client",
                callback_data=create_callback(
                    CallbackAreas.CLIENT, CallbackTasks.DELETE, CallbackSteps.CONFIRMATION, 0, 0, client_id
                ),
            ),
        )
        builder.row(
            InlineKeyboardButton(
                text="🔙 Back", callback_data=create_callback(CallbackAreas.CLIENT, CallbackTasks.LIST)
            ),
        )

        text = f"👤 Client Setting\n\n🔑 API Key: <tg-spoiler>{token_preview}</tg-spoiler>"
        await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
        await callback.answer()


@router.callback_query(F.data.startswith(f"{CallbackAreas.CLIENT}:{CallbackTasks.CREATE}:{CallbackSteps.REMARK}"))
async def client_create_remark(callback: CallbackQuery, state: FSMContext):
    await state.set_state(ClientCreateStates.waiting_remark)
    await callback.message.edit_text("✏️ Enter a remark for the client:")
    await callback.answer()


@router.message(ClientCreateStates.waiting_remark)
async def client_create_remark_received(message: Message, state: FSMContext):
    valid, _ = validate_remark(message.text)
    if not valid:
        await message.answer(
            "⚠️❌ Invalid remark format. 🔍 Please enter a valid remark without special characters and space."
        )
        return

    async with db.session() as session:
        client_repo = ClientRepository(session)
        existing = await client_repo.get_by_remark(message.text)
        if existing:
            await message.answer("⚠️❌ A item with this remark already exists. 🔄 Please choose a different remark.")
            return

    await state.update_data(remark=message.text)
    await state.set_state(ClientCreateStates.waiting_token)
    await message.answer("🔑 Enter the Hetzner API token:")


@router.message(ClientCreateStates.waiting_token)
async def client_create_token_received(message: Message, state: FSMContext):
    token = message.text.strip()

    async with db.session() as session:
        try:
            hetzner_client, _ = await create_client(token)
            await hetzner_client.list_servers()
            await close_client(hetzner_client)
        except Exception:
            await message.answer("⚠️❌ Invalid API token. Please check and try again.")
            return

    data = await state.get_data()
    remark = data["remark"]

    token_encrypted = encrypt_token(token)
    token_hash = hashlib.sha256(token.encode()).hexdigest()

    async with db.session() as session:
        client_repo = ClientRepository(session)
        user_repo = UserRepository(session)
        user = await user_repo.get_by_telegram_id(message.from_user.id)

        client = await client_repo.create(
            remark=remark,
            api_token_encrypted=token_encrypted,
            token_hash=token_hash,
            owner_id=user.id if user else None,
        )

        audit_repo = AuditLogRepository(session)
        await audit_repo.log(
            action="client_create",
            success=True,
            user_id=user.id if user else None,
            client_id=client.id,
            details={"remark": remark},
        )

    await state.clear()
    await message.answer("🎉✅ Client created successfully. ⚙️ You can now manage the client.")
    await show_client_list(message)


async def show_client_list(message: Message):
    async with db.session() as session:
        client_repo = ClientRepository(session)
        user_repo = UserRepository(session)
        user = await user_repo.get_by_telegram_id(message.from_user.id)
        clients = await client_repo.list_for_user(user)

        builder = InlineKeyboardBuilder()
        for client in clients:
            builder.button(
                text=format_client_button(client),
                callback_data=create_callback(CallbackAreas.CLIENT, CallbackTasks.INFO, "", 0, 0, client.id),
            )
        builder.adjust(2)
        builder.row(InlineKeyboardButton(text="🔙 Back", callback_data="home:back"))

        await message.answer(
            "👥 Clients Menu\n👇 Select an action from the menu below.", reply_markup=builder.as_markup()
        )


@router.callback_query(F.data.startswith(f"{CallbackAreas.CLIENT}:{CallbackTasks.EDIT}:{CallbackSteps.REMARK}"))
async def client_edit_remark(callback: CallbackQuery, state: FSMContext):
    cb = parse_callback(callback.data)
    await state.set_state(ClientSettingsStates.waiting_new_remark)
    await state.update_data(client_id=cb.target_id)
    await callback.message.edit_text("✏️ Enter new remark:")
    await callback.answer()


@router.message(ClientSettingsStates.waiting_new_remark)
async def client_edit_remark_received(message: Message, state: FSMContext):
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
        existing = await client_repo.get_by_remark(message.text)
        if existing and existing.id != client_id:
            await message.answer("⚠️❌ A item with this remark already exists. 🔄 Please choose a different remark.")
            return

        client = await client_repo.update_remark(client_id, message.text)
        if client:
            audit_repo = AuditLogRepository(session)
            await audit_repo.log(
                action="client_update_remark",
                success=True,
                client_id=client_id,
                details={"new_remark": message.text},
            )
            await message.answer("🎉✅ Client remark updated successfully.")
        else:
            await message.answer("⚠️❌ Client not found.")

    await state.clear()


@router.callback_query(F.data.startswith(f"{CallbackAreas.CLIENT}:{CallbackTasks.EDIT}:{CallbackSteps.TOKEN}"))
async def client_edit_token(callback: CallbackQuery, state: FSMContext):
    cb = parse_callback(callback.data)
    await state.set_state(ClientSettingsStates.waiting_new_token)
    await state.update_data(client_id=cb.target_id)
    await callback.message.edit_text("🔑 Enter new Hetzner API token:")
    await callback.answer()


@router.message(ClientSettingsStates.waiting_new_token)
async def client_edit_token_received(message: Message, state: FSMContext):
    token = message.text.strip()

    async with db.session() as session:
        try:
            hetzner_client, _ = await create_client(token)
            await hetzner_client.list_servers()
            await close_client(hetzner_client)
        except Exception:
            await message.answer("⚠️❌ Invalid API token. Please check and try again.")
            return

    data = await state.get_data()
    client_id = data["client_id"]

    token_encrypted = encrypt_token(token)
    token_hash = hashlib.sha256(token.encode()).hexdigest()

    async with db.session() as session:
        client_repo = ClientRepository(session)
        client = await client_repo.update_token(client_id, token_encrypted, token_hash)
        if client:
            audit_repo = AuditLogRepository(session)
            await audit_repo.log(
                action="client_update_token",
                success=True,
                client_id=client_id,
            )
            await message.answer("🎉✅ Client API token updated successfully.")
        else:
            await message.answer("⚠️❌ Client not found.")

    await state.clear()


@router.callback_query(F.data.startswith(f"{CallbackAreas.CLIENT}:{CallbackTasks.DELETE}:{CallbackSteps.CONFIRMATION}"))
async def client_delete_confirm(callback: CallbackQuery):
    cb = parse_callback(callback.data)
    client_id = cb.target_id

    if cb.approve == 1:
        async with db.session() as session:
            client_repo = ClientRepository(session)
            success = await client_repo.delete(client_id)
            if success:
                audit_repo = AuditLogRepository(session)
                await audit_repo.log(
                    action="client_delete",
                    success=True,
                    client_id=client_id,
                )
                await callback.message.edit_text("🎉✅ Client deleted successfully.")
            else:
                await callback.message.edit_text("⚠️❌ Client not found.")
    else:
        await callback.message.edit_text("🚫❌ Action cancelled. ↩️ Go back to the previous menu.")

    await callback.answer()
    await show_client_menu(callback)

