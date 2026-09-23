from aiogram import F, Router
from aiogram.types import CallbackQuery

router = Router()


@router.callback_query(F.data == "home:back")
async def callback_home_back(callback: CallbackQuery):
    from bot.handlers.start import show_home_screen

    await callback.message.edit_text("🌟 Welcome! I'm your Server Management Assistant")
    await show_home_screen(callback.message)
    await callback.answer()


@router.callback_query()
async def callback_fallback(callback: CallbackQuery):
    await callback.answer("This action is no longer available.", show_alert=True)
