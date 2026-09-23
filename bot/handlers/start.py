from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.database.repositories import BotAdminRepository, ClientRepository
from bot.utils.callbacks import CallbackAreas, CallbackSteps, CallbackTasks, create_callback
from bot.utils.formatters import format_client_button

router = Router()


async def show_home_screen(message: Message):
    from bot.config import get_settings
    from bot.database.base import db

    settings = get_settings()
    user_id = message.from_user.id

    async with db.session() as session:
        client_repo = ClientRepository(session)
        admin_repo = BotAdminRepository(session)

        user = await UserRepository(session).get_by_telegram_id(user_id)
        is_env_admin = user_id in settings.admin_ids
        is_bot_admin = await admin_repo.is_admin(user_id) if user else False
        is_admin = is_env_admin or is_bot_admin or (user and user.role in ("owner", "admin"))

        clients = await client_repo.list_all(active_only=True) if is_admin else await client_repo.list_for_user(user)

        builder = InlineKeyboardBuilder()

        for client in clients:
            builder.button(
                text=format_client_button(client),
                callback_data=create_callback(CallbackAreas.CLIENT, CallbackTasks.LIST, "", 0, 0, client.id),
            )

        builder.adjust(2)

        if is_admin:
            builder.row(
                InlineKeyboardButton(
                    text="🆕 Create Client",
                    callback_data=create_callback(CallbackAreas.CLIENT, CallbackTasks.CREATE, CallbackSteps.REMARK),
                ),
                InlineKeyboardButton(
                    text="👑 Admins",
                    callback_data=create_callback(CallbackAreas.ADMIN, CallbackTasks.LIST),
                ),
            )

        builder.row(
            InlineKeyboardButton(
                text="🌚 Owner",
                url="https://t.me/your_channel",
            )
        )

        text = "🌟 Welcome! I'm your Server Management Assistant"
        await message.answer(text, reply_markup=builder.as_markup())


@router.callback_query(F.data.startswith("home"))
async def callback_home(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("🌟 Welcome! I'm your Server Management Assistant")
    await show_home_screen(callback.message)
    await callback.answer()


from bot.database.repositories import UserRepository
