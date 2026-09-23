from typing import Generic, TypeVar

T = TypeVar("T")


class Paginator(Generic[T]):
    def __init__(self, items: list[T], page_size: int = 10):
        self.items = items
        self.page_size = page_size

    def get_page(self, page: int) -> tuple[list[T], int, int]:
        total = len(self.items)
        total_pages = (total + self.page_size - 1) // self.page_size
        page = max(0, min(page, total_pages - 1))
        start = page * self.page_size
        end = start + self.page_size
        return self.items[start:end], page, total_pages


def chunk_list(lst: list, chunk_size: int) -> list[list]:
    return [lst[i : i + chunk_size] for i in range(0, len(lst), chunk_size)]


def mask_token(token: str) -> str:
    if len(token) <= 12:
        return "*" * len(token)
    return token[:8] + "..." + token[-4:]


def truncate(text: str, max_len: int = 4096) -> str:
    if len(text) <= max_len:
        return text
    return text[: max_len - 3] + "..."


async def safe_edit_message(message, text: str, reply_markup=None, parse_mode: str = "HTML") -> bool:
    try:
        await message.edit_text(text, reply_markup=reply_markup, parse_mode=parse_mode)
        return True
    except Exception:
        return False


async def safe_delete_message(message) -> bool:
    try:
        await message.delete()
        return True
    except Exception:
        return False
