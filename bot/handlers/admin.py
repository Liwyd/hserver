from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.config import get_settings
from bot.database.base import db
from bot.database.repositories import (
    AuditLogRepository,
    BotAdminRepository,
    UserRepository,
)
from bot.states import AdminAddStates
from bot.utils.callbacks import (
    CallbackAreas,
    CallbackSteps,
    CallbackTasks,
    create_callback,
    parse_callback,
)
from bot.utils.validators import validate_chat_id

router = Router()


@router.callback_query(F.data.startswith(f"{CallbackAreas.ADMIN}:{CallbackTasks.LIST}"))
async def admin_list(callback: CallbackQuery):
    async with db.session() as session:
        admin_repo = BotAdminRepository(session)
        user_repo = UserRepository(session)
        settings = get_settings()

        admins = await admin_repo.list_admins()
        env_admins = settings.admin_ids

        text = "👑 Admin List\n\n"

        for admin in admins:
            user = await user_repo.get_by_id(admin.user_id)
            if user:
                text += f"• {user.telegram_id} — {user.first_name or ''} {user.last_name or ''} [bot]\n"

        for admin_id in env_admins:
            user = await user_repo.get_by_telegram_id(admin_id)
            if user:
                text += f"• {user.telegram_id} — {user.first_name or ''} {user.last_name or ''} [env]\n"
            else:
                text += f"• {admin_id} — Unknown [env]\n"

        builder = InlineKeyboardBuilder()

        for admin in admins:
            user = await user_repo.get_by_id(admin.user_id)
            if user:
                builder.button(
                    text=f"❌ {user.telegram_id}",
                    callback_data=create_callback(
                        CallbackAreas.ADMIN, CallbackTasks.DELETE, CallbackSteps.CONFIRMATION, 0, 0, admin.user_id
                    ),
                )

        builder.adjust(1)
        builder.row(
            InlineKeyboardButton(
                text="+ Add Admin",
                callback_data=create_callback(CallbackAreas.ADMIN, CallbackTasks.CREATE, CallbackSteps.CHAT_ID),
            ),
        )
        builder.row(
            InlineKeyboardButton(text="🔙 Back", callback_data="home:back"),
        )

        await callback.message.edit_text(text, reply_markup=builder.as_markup())
        await callback.answer()


@router.callback_query(F.data.startswith(f"{CallbackAreas.ADMIN}:{CallbackTasks.CREATE}:{CallbackSteps.CHAT_ID}"))
async def admin_add(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AdminAddStates.waiting_user_id)
    await callback.message.edit_text("✏️ Send the Telegram User ID to add as admin:")
    await callback.answer()


@router.message(AdminAddStates.waiting_user_id)
async def admin_add_received(message: Message, state: FSMContext):
    valid, error, user_id = validate_chat_id(message.text)
    if not valid:
        await message.answer(f"⚠️❌ {error}")
        return

    if user_id == message.from_user.id:
        await message.answer("⚠️❌ You cannot add yourself as admin.")
        return

    settings = get_settings()
    if user_id in settings.admin_ids:
        await message.answer("⚠️❌ This user is already an environment admin.")
        return

    async with db.session() as session:
        admin_repo = BotAdminRepository(session)
        user_repo = UserRepository(session)

        existing = await admin_repo.is_admin(user_id)
        if existing:
            await message.answer("⚠️❌ This user is already a bot admin.")
            return

        target_user = await user_repo.get_by_telegram_id(user_id)
        if not target_user:
            await message.answer("🔍❌ User not found. They must have started the bot first.")
            return

        await admin_repo.add_admin(target_user.id, message.from_user.id)

        audit_repo = AuditLogRepository(session)
        await audit_repo.log(
            action="admin_add",
            success=True,
            user_id=message.from_user.id,
            resource_type="admin",
            resource_id=target_user.id,
        )

        await message.answer("🎉✅ Admin added successfully.")

    await state.clear()
    await admin_list_message(message)


async def admin_list_message(message: Message):
    async with db.session() as session:
        admin_repo = BotAdminRepository(session)
        user_repo = UserRepository(session)
        settings = get_settings()

        admins = await admin_repo.list_admins()
        env_admins = settings.admin_ids

        text = "👑 Admin List\n\n"

        for admin in admins:
            user = await user_repo.get_by_id(admin.user_id)
            if user:
                text += f"• {user.telegram_id} — {user.first_name or ''} {user.last_name or ''} [bot]\n"

        for admin_id in env_admins:
            user = await user_repo.get_by_telegram_id(admin_id)
            if user:
                text += f"• {user.telegram_id} — {user.first_name or ''} {user.last_name or ''} [env]\n"
            else:
                text += f"• {admin_id} — Unknown [env]\n"

        builder = InlineKeyboardBuilder()
        for admin in admins:
            user = await user_repo.get_by_id(admin.user_id)
            if user:
                builder.button(
                    text=f"❌ {user.telegram_id}",
                    callback_data=create_callback(
                        CallbackAreas.ADMIN, CallbackTasks.DELETE, CallbackSteps.CONFIRMATION, 0, 0, admin.user_id
                    ),
                )
        builder.adjust(1)
        builder.row(
            InlineKeyboardButton(
                text="+ Add Admin",
                callback_data=create_callback(CallbackAreas.ADMIN, CallbackTasks.CREATE, CallbackSteps.CHAT_ID),
            ),
        )
        builder.row(InlineKeyboardButton(text="🔙 Back", callback_data="home:back"))

        await message.answer(text, reply_markup=builder.as_markup())


@router.callback_query(F.data.startswith(f"{CallbackAreas.ADMIN}:{CallbackTasks.DELETE}:{CallbackSteps.CONFIRMATION}"))
async def admin_delete_confirm(callback: CallbackQuery):
    cb = parse_callback(callback.data)
    target_user_id = cb.target_id

    if cb.approve == 1:
        async with db.session() as session:
            admin_repo = BotAdminRepository(session)
            user_repo = UserRepository(session)

            target_user = await user_repo.get_by_id(target_user_id)
            if target_user:
                settings = get_settings()
                if target_user.telegram_id in settings.admin_ids:
                    await callback.answer("⚠️❌ Cannot remove environment admin.", show_alert=True)
                    return

                success = await admin_repo.remove_admin(target_user.id)
                if success:
                    audit_repo = AuditLogRepository(session)
                    await audit_repo.log(
                        action="admin_remove",
                        success=True,
                        user_id=callback.from_user.id,
                        resource_type="admin",
                        resource_id=target_user.id,
                    )
                    await callback.message.edit_text("🎉✅ Admin removed successfully.")
                else:
                    await callback.message.edit_text("⚠️❌ Admin not found.")
            else:
                await callback.message.edit_text("🔍❌ User not found.")
    else:
        await callback.message.edit_text("🚫❌ Action cancelled. ↩️ Go back to the previous menu.")

    await callback.answer()
    await admin_list(callback)
