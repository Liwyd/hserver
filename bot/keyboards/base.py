from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.utils.callbacks import CallbackSteps, CallbackTasks, create_callback


class KeyboardBuilder:
    @staticmethod
    def back_button(area: str, task: str = CallbackTasks.LIST, target_id: int = 0) -> InlineKeyboardButton:
        return InlineKeyboardButton(
            text="🔙 Back",
            callback_data=create_callback(area, task, CallbackSteps.CONFIRMATION, 0, 0, target_id),
        )

    @staticmethod
    def confirmation_keyboard(
        area: str,
        task: str,
        target_id: int = 0,
        step: str = CallbackSteps.CONFIRMATION,
        extra: str = "",
    ) -> InlineKeyboardMarkup:
        builder = InlineKeyboardBuilder()
        builder.row(
            InlineKeyboardButton(
                text="✅ Yes",
                callback_data=create_callback(area, task, step, 0, 1, target_id, extra),
            ),
            InlineKeyboardButton(
                text="❌ No",
                callback_data=create_callback(area, task, step, 0, 0, target_id, extra),
            ),
        )
        return builder.as_markup()

    @staticmethod
    def paginated_keyboard(
        items: list,
        area: str,
        task: str,
        page: int,
        total_pages: int,
        target_id: int = 0,
        back_area: str = "",
        back_task: str = CallbackTasks.LIST,
        back_target_id: int = 0,
        item_formatter=None,
        item_callback_area: str = "",
        item_callback_task: str = CallbackTasks.INFO,
        item_callback_step: str = "",
    ) -> InlineKeyboardMarkup:
        builder = InlineKeyboardBuilder()

        for item in items:
            if item_formatter:
                text = item_formatter(item)
            else:
                text = str(item)

            if item_callback_area:
                item_id = getattr(item, "id", target_id)
                callback = create_callback(
                    item_callback_area,
                    item_callback_task,
                    item_callback_step,
                    0,
                    0,
                    item_id,
                )
            else:
                callback = create_callback(area, task, "", 0, 0, target_id)

            builder.button(text=text, callback_data=callback)

        builder.adjust(2)

        nav_buttons = []
        if page > 0:
            nav_buttons.append(
                InlineKeyboardButton(
                    text="⬅️ Prev",
                    callback_data=create_callback(area, task, "", page - 1, 0, target_id),
                )
            )
        if page < total_pages - 1:
            nav_buttons.append(
                InlineKeyboardButton(
                    text="Next ➡️",
                    callback_data=create_callback(area, task, "", page + 1, 0, target_id),
                )
            )
        if nav_buttons:
            builder.row(*nav_buttons)

        if back_area:
            builder.row(
                InlineKeyboardButton(
                    text="🔙 Back",
                    callback_data=create_callback(back_area, back_task, "", 0, 0, back_target_id),
                )
            )

        return builder.as_markup()

    @staticmethod
    def simple_list_keyboard(
        items: list,
        area: str,
        task: str,
        target_id: int = 0,
        back_area: str = "",
        back_task: str = CallbackTasks.LIST,
        back_target_id: int = 0,
        item_formatter=None,
        item_callback_area: str = "",
        item_callback_task: str = CallbackTasks.INFO,
        item_callback_step: str = "",
        columns: int = 1,
        extra_buttons: list[InlineKeyboardButton] | None = None,
    ) -> InlineKeyboardMarkup:
        builder = InlineKeyboardBuilder()

        for item in items:
            if item_formatter:
                text = item_formatter(item)
            else:
                text = str(item)

            if item_callback_area:
                item_id = getattr(item, "id", target_id)
                callback = create_callback(
                    item_callback_area,
                    item_callback_task,
                    item_callback_step,
                    0,
                    0,
                    item_id,
                )
            else:
                callback = create_callback(area, task, "", 0, 0, target_id)

            builder.button(text=text, callback_data=callback)

        builder.adjust(columns)

        if extra_buttons:
            for btn in extra_buttons:
                builder.row(btn)

        if back_area:
            builder.row(
                InlineKeyboardButton(
                    text="🔙 Back",
                    callback_data=create_callback(back_area, back_task, "", 0, 0, back_target_id),
                )
            )

        return builder.as_markup()

    @staticmethod
    def grid_keyboard(
        buttons: list[tuple[str, str]],
        columns: int = 2,
        back_area: str = "",
        back_task: str = CallbackTasks.LIST,
        back_target_id: int = 0,
    ) -> InlineKeyboardMarkup:
        builder = InlineKeyboardBuilder()

        for text, callback in buttons:
            builder.button(text=text, callback_data=callback)

        builder.adjust(columns)

        if back_area:
            builder.row(
                InlineKeyboardButton(
                    text="🔙 Back",
                    callback_data=create_callback(back_area, back_task, "", 0, 0, back_target_id),
                )
            )

        return builder.as_markup()

    @staticmethod
    def url_button(text: str, url: str) -> InlineKeyboardButton:
        return InlineKeyboardButton(text=text, url=url)
