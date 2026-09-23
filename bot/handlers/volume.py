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
from bot.states import VolumeActionStates, VolumeCreateStates
from bot.utils.callbacks import (
    CallbackAreas,
    CallbackSteps,
    CallbackTasks,
    create_callback,
    parse_callback,
)
from bot.utils.formatters import format_volume_info
from bot.utils.validators import validate_remark, validate_size_gb

router = Router()


@router.callback_query(F.data.startswith(f"{CallbackAreas.VOLUME}:{CallbackTasks.LIST}"))
async def volume_list(callback: CallbackQuery):
    cb = parse_callback(callback.data)
    client_id = cb.target_id
    await show_volume_list(callback, client_id)


async def show_volume_list(callback: CallbackQuery, client_id: int):
    async with db.session() as session:
        client_repo = ClientRepository(session)
        client = await client_repo.get_by_id(client_id)
        if not client:
            await callback.answer("🔍❌ Not found [client].", show_alert=True)
            return

        token = decrypt_token(client.api_token_encrypted)
        hetzner_client = await create_client(token)
        volumes = await hetzner_client.list_volumes()
        await close_client(hetzner_client)

    builder = InlineKeyboardBuilder()
    for vol in volumes:
        builder.button(
            text=f"{vol.name} [{vol.size} GB]",
            callback_data=create_callback(CallbackAreas.VOLUME, CallbackTasks.INFO, "", 0, 0, vol.id, str(client_id)),
        )
    builder.adjust(1)

    builder.row(
        InlineKeyboardButton(
            text="+ Create Volume",
            callback_data=create_callback(
                CallbackAreas.VOLUME, CallbackTasks.CREATE, CallbackSteps.REMARK, 0, 0, client_id
            ),
        ),
        InlineKeyboardButton(text="🔙 Back", callback_data=create_callback(CallbackAreas.CLIENT, CallbackTasks.LIST)),
    )

    text = "💾 Volumes Menu\n👇 Select an action from the menu below."
    await callback.message.edit_text(text, reply_markup=builder.as_markup())
    await callback.answer()


@router.callback_query(F.data.startswith(f"{CallbackAreas.VOLUME}:{CallbackTasks.INFO}"))
async def volume_info(callback: CallbackQuery):
    cb = parse_callback(callback.data)
    volume_id = cb.target_id
    client_id = int(cb.extra) if cb.extra else 0

    async with db.session() as session:
        client_repo = ClientRepository(session)
        client = await client_repo.get_by_id(client_id)
        if not client:
            await callback.answer("🔍❌ Not found [client].", show_alert=True)
            return

        token = decrypt_token(client.api_token_encrypted)
        hetzner_client = await create_client(token)
        volume = await hetzner_client.get_volume(volume_id)
        await close_client(hetzner_client)

    is_attached = volume.server is not None

    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="✏️ Change Remark",
            callback_data=create_callback(
                CallbackAreas.VOLUME, CallbackTasks.EDIT, CallbackSteps.REMARK, 0, 0, volume_id, str(client_id)
            ),
        ),
    )
    builder.row(
        InlineKeyboardButton(
            text="⬆️ Resize Volume",
            callback_data=create_callback(
                CallbackAreas.VOLUME, CallbackTasks.ACTION, "resize", 0, 0, volume_id, str(client_id)
            ),
        ),
    )
    if is_attached:
        builder.row(
            InlineKeyboardButton(
                text="❌ Detach from Server",
                callback_data=create_callback(
                    CallbackAreas.VOLUME, CallbackTasks.ACTION, "detach", 0, 0, volume_id, str(client_id)
                ),
            ),
        )
    else:
        builder.row(
            InlineKeyboardButton(
                text="🔗 Attach to Server",
                callback_data=create_callback(
                    CallbackAreas.VOLUME, CallbackTasks.ACTION, "attach", 0, 0, volume_id, str(client_id)
                ),
            ),
        )
    builder.row(
        InlineKeyboardButton(
            text="🗑 Delete Volume",
            callback_data=create_callback(
                CallbackAreas.VOLUME, CallbackTasks.DELETE, CallbackSteps.CONFIRMATION, 0, 0, volume_id, str(client_id)
            ),
        ),
    )
    builder.row(
        InlineKeyboardButton(
            text="🔙 Back", callback_data=create_callback(CallbackAreas.VOLUME, CallbackTasks.LIST, "", 0, 0, client_id)
        ),
    )

    text = format_volume_info(volume)
    await callback.message.edit_text(text, reply_markup=builder.as_markup())
    await callback.answer()


@router.callback_query(F.data.startswith(f"{CallbackAreas.VOLUME}:{CallbackTasks.CREATE}:{CallbackSteps.REMARK}"))
async def volume_create_remark(callback: CallbackQuery, state: FSMContext):
    cb = parse_callback(callback.data)
    await state.set_state(VolumeCreateStates.waiting_remark)
    await state.update_data(client_id=cb.target_id)
    await callback.message.edit_text("✏️ Enter a remark for the volume:")
    await callback.answer()


@router.message(VolumeCreateStates.waiting_remark)
async def volume_create_remark_received(message: Message, state: FSMContext):
    valid, _ = validate_remark(message.text)
    if not valid:
        await message.answer(
            "⚠️❌ Invalid remark format. 🔍 Please enter a valid remark without special characters and space."
        )
        return

    await state.update_data(remark=message.text)
    await state.set_state(VolumeCreateStates.waiting_size)
    await message.answer("📏 Enter size in GB (minimum 10, multiple of 10):")


@router.message(VolumeCreateStates.waiting_size)
async def volume_create_size_received(message: Message, state: FSMContext):
    valid, error, size = validate_size_gb(message.text)
    if not valid:
        await message.answer(f"⚠️❌ {error}")
        return

    await state.update_data(size=size)
    await state.set_state(VolumeCreateStates.waiting_location)

    data = await state.get_data()
    client_id = data["client_id"]

    async with db.session() as session:
        client_repo = ClientRepository(session)
        client = await client_repo.get_by_id(client_id)
        token = decrypt_token(client.api_token_encrypted)
        hetzner_client = await create_client(token)
        datacenters = await hetzner_client.list_datacenters()
        await close_client(hetzner_client)

    builder = InlineKeyboardBuilder()
    for dc in datacenters:
        builder.button(
            text=f"{dc.name} [{dc.location}]",
            callback_data=create_callback(
                CallbackAreas.VOLUME, CallbackTasks.CREATE, CallbackSteps.LOCATION, 0, 0, dc.id, str(client_id)
            ),
        )
    builder.adjust(1)
    builder.row(
        InlineKeyboardButton(
            text="🔙 Back", callback_data=create_callback(CallbackAreas.VOLUME, CallbackTasks.LIST, "", 0, 0, client_id)
        )
    )

    await message.answer("🌍 Select a location for the volume:", reply_markup=builder.as_markup())


@router.callback_query(F.data.startswith(f"{CallbackAreas.VOLUME}:{CallbackTasks.CREATE}:{CallbackSteps.LOCATION}"))
async def volume_create_location(callback: CallbackQuery, state: FSMContext):
    cb = parse_callback(callback.data)
    datacenter_id = cb.target_id
    client_id = int(cb.extra) if cb.extra else 0

    data = await state.get_data()

    await state.set_state(VolumeCreateStates.waiting_server)
    await state.update_data(datacenter_id=datacenter_id)

    async with db.session() as session:
        client_repo = ClientRepository(session)
        client = await client_repo.get_by_id(client_id)
        token = decrypt_token(client.api_token_encrypted)
        hetzner_client = await create_client(token)
        servers = await hetzner_client.list_servers()
        await close_client(hetzner_client)

    builder = InlineKeyboardBuilder()
    builder.button(
        text="Skip (create without attachment)",
        callback_data=create_callback(
            CallbackAreas.VOLUME, CallbackTasks.CREATE, CallbackSteps.SERVER, 0, 0, 0, str(client_id)
        ),
    )
    for server in servers:
        builder.button(
            text=f"{server.name} [{server.status}]",
            callback_data=create_callback(
                CallbackAreas.VOLUME, CallbackTasks.CREATE, CallbackSteps.SERVER, 0, 0, server.id, str(client_id)
            ),
        )
    builder.adjust(1)
    builder.row(
        InlineKeyboardButton(
            text="🔙 Back", callback_data=create_callback(CallbackAreas.VOLUME, CallbackTasks.LIST, "", 0, 0, client_id)
        )
    )

    await callback.message.edit_text("🖥 Select server to attach (optional):", reply_markup=builder.as_markup())
    await callback.answer()


@router.callback_query(F.data.startswith(f"{CallbackAreas.VOLUME}:{CallbackTasks.CREATE}:{CallbackSteps.SERVER}"))
async def volume_create_server(callback: CallbackQuery, state: FSMContext):
    cb = parse_callback(callback.data)
    server_id = cb.target_id
    client_id = int(cb.extra) if cb.extra else 0

    data = await state.get_data()

    async with db.session() as session:
        client_repo = ClientRepository(session)
        client = await client_repo.get_by_id(client_id)
        token = decrypt_token(client.api_token_encrypted)
        hetzner_client = await create_client(token)

        try:
            server = server_id if server_id > 0 else None
            volume = await hetzner_client.create_volume(
                name=data["remark"],
                size=data["size"],
                location=str(data["datacenter_id"]),
                server=server,
            )
            await close_client(hetzner_client)

            audit_repo = AuditLogRepository(session)
            await audit_repo.log(
                action="volume_create",
                success=True,
                client_id=client_id,
                resource_type="volume",
                resource_id=volume.id,
                details={
                    "name": data["remark"],
                    "size": data["size"],
                    "location": data["datacenter_id"],
                    "server": server,
                },
            )

            await callback.message.edit_text("🎉✅ Volume created successfully.")
        except Exception as e:
            await close_client(hetzner_client)
            await callback.message.edit_text(f"⚠️❌ Volume creation failed: {e!s}")

    await state.clear()
    await callback.answer()
    await show_volume_list(callback, client_id)


@router.callback_query(F.data.startswith(f"{CallbackAreas.VOLUME}:{CallbackTasks.ACTION}:resize"))
async def volume_resize(callback: CallbackQuery, state: FSMContext):
    cb = parse_callback(callback.data)
    volume_id = cb.target_id
    client_id = int(cb.extra) if cb.extra else 0

    await state.set_state(VolumeActionStates.waiting_size)
    await state.update_data(volume_id=volume_id, client_id=client_id)
    await callback.message.edit_text("📏 Enter new size in GB (must be larger than current):")
    await callback.answer()


@router.message(VolumeActionStates.waiting_size)
async def volume_resize_received(message: Message, state: FSMContext):
    valid, error, size = validate_size_gb(message.text)
    if not valid:
        await message.answer(f"⚠️❌ {error}")
        return

    data = await state.get_data()
    volume_id = data["volume_id"]
    client_id = data["client_id"]

    async with db.session() as session:
        client_repo = ClientRepository(session)
        client = await client_repo.get_by_id(client_id)
        token = decrypt_token(client.api_token_encrypted)
        hetzner_client = await create_client(token)

        try:
            await hetzner_client.resize_volume(volume_id, size)
            await close_client(hetzner_client)

            audit_repo = AuditLogRepository(session)
            await audit_repo.log(
                action="volume_resize",
                success=True,
                client_id=client_id,
                resource_type="volume",
                resource_id=volume_id,
                details={"new_size": size},
            )

            await message.answer("🎉✅ Volume resized successfully.")
        except Exception as e:
            await close_client(hetzner_client)
            await message.answer(f"⚠️❌ Resize failed: {e!s}")

    await state.clear()


@router.callback_query(F.data.startswith(f"{CallbackAreas.VOLUME}:{CallbackTasks.ACTION}:attach"))
async def volume_attach(callback: CallbackQuery):
    cb = parse_callback(callback.data)
    volume_id = cb.target_id
    client_id = int(cb.extra) if cb.extra else 0

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
                CallbackAreas.VOLUME, CallbackTasks.ACTION, "attach_select", 0, 0, server.id, f"{volume_id}:{client_id}"
            ),
        )
    builder.adjust(1)
    builder.row(
        InlineKeyboardButton(
            text="🔙 Back",
            callback_data=create_callback(
                CallbackAreas.VOLUME, CallbackTasks.INFO, "", 0, 0, volume_id, str(client_id)
            ),
        )
    )

    await callback.message.edit_text("🖥 Select server to attach:", reply_markup=builder.as_markup())
    await callback.answer()


@router.callback_query(F.data.startswith(f"{CallbackAreas.VOLUME}:{CallbackTasks.ACTION}:attach_select"))
async def volume_attach_select(callback: CallbackQuery):
    cb = parse_callback(callback.data)
    server_id = cb.target_id
    volume_id, client_id = map(int, cb.extra.split(":"))

    async with db.session() as session:
        client_repo = ClientRepository(session)
        client = await client_repo.get_by_id(client_id)
        token = decrypt_token(client.api_token_encrypted)
        hetzner_client = await create_client(token)

        try:
            await hetzner_client.attach_volume(volume_id, server_id)
            await close_client(hetzner_client)

            audit_repo = AuditLogRepository(session)
            await audit_repo.log(
                action="volume_attach",
                success=True,
                client_id=client_id,
                resource_type="volume",
                resource_id=volume_id,
                details={"server_id": server_id},
            )

            await callback.message.edit_text("🎉✅ Volume attached successfully.")
        except Exception as e:
            await close_client(hetzner_client)
            await callback.message.edit_text(f"⚠️❌ Attach failed: {e!s}")

    await callback.answer()
    await show_volume_info(callback, client_id, volume_id)


async def show_volume_info(callback: CallbackQuery, client_id: int, volume_id: int):
    async with db.session() as session:
        client_repo = ClientRepository(session)
        client = await client_repo.get_by_id(client_id)
        if not client:
            await callback.answer("🔍❌ Not found [client].", show_alert=True)
            return

        token = decrypt_token(client.api_token_encrypted)
        hetzner_client = await create_client(token)
        volume = await hetzner_client.get_volume(volume_id)
        await close_client(hetzner_client)

    is_attached = volume.server is not None

    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="✏️ Change Remark",
            callback_data=create_callback(
                CallbackAreas.VOLUME, CallbackTasks.EDIT, CallbackSteps.REMARK, 0, 0, volume_id, str(client_id)
            ),
        ),
    )
    builder.row(
        InlineKeyboardButton(
            text="⬆️ Resize Volume",
            callback_data=create_callback(
                CallbackAreas.VOLUME, CallbackTasks.ACTION, "resize", 0, 0, volume_id, str(client_id)
            ),
        ),
    )
    if is_attached:
        builder.row(
            InlineKeyboardButton(
                text="❌ Detach from Server",
                callback_data=create_callback(
                    CallbackAreas.VOLUME, CallbackTasks.ACTION, "detach", 0, 0, volume_id, str(client_id)
                ),
            ),
        )
    else:
        builder.row(
            InlineKeyboardButton(
                text="🔗 Attach to Server",
                callback_data=create_callback(
                    CallbackAreas.VOLUME, CallbackTasks.ACTION, "attach", 0, 0, volume_id, str(client_id)
                ),
            ),
        )
    builder.row(
        InlineKeyboardButton(
            text="🗑 Delete Volume",
            callback_data=create_callback(
                CallbackAreas.VOLUME, CallbackTasks.DELETE, CallbackSteps.CONFIRMATION, 0, 0, volume_id, str(client_id)
            ),
        ),
    )
    builder.row(
        InlineKeyboardButton(
            text="🔙 Back", callback_data=create_callback(CallbackAreas.VOLUME, CallbackTasks.LIST, "", 0, 0, client_id)
        ),
    )

    text = format_volume_info(volume)
    await callback.message.edit_text(text, reply_markup=builder.as_markup())


@router.callback_query(F.data.startswith(f"{CallbackAreas.VOLUME}:{CallbackTasks.ACTION}:detach"))
async def volume_detach(callback: CallbackQuery):
    cb = parse_callback(callback.data)
    volume_id = cb.target_id
    client_id = int(cb.extra) if cb.extra else 0

    async with db.session() as session:
        client_repo = ClientRepository(session)
        client = await client_repo.get_by_id(client_id)
        token = decrypt_token(client.api_token_encrypted)
        hetzner_client = await create_client(token)

        try:
            await hetzner_client.detach_volume(volume_id)
            await close_client(hetzner_client)

            audit_repo = AuditLogRepository(session)
            await audit_repo.log(
                action="volume_detach",
                success=True,
                client_id=client_id,
                resource_type="volume",
                resource_id=volume_id,
            )

            await callback.message.edit_text("🎉✅ Volume detached successfully.")
        except Exception as e:
            await close_client(hetzner_client)
            await callback.message.edit_text(f"⚠️❌ Detach failed: {e!s}")

    await callback.answer()
    await show_volume_info(callback, client_id, volume_id)


@router.callback_query(F.data.startswith(f"{CallbackAreas.VOLUME}:{CallbackTasks.DELETE}:{CallbackSteps.CONFIRMATION}"))
async def volume_delete_confirm(callback: CallbackQuery):
    cb = parse_callback(callback.data)
    volume_id = cb.target_id
    client_id = int(cb.extra) if cb.extra else 0

    if cb.approve == 1:
        async with db.session() as session:
            client_repo = ClientRepository(session)
            client = await client_repo.get_by_id(client_id)
            token = decrypt_token(client.api_token_encrypted)
            hetzner_client = await create_client(token)

            try:
                await hetzner_client.delete_volume(volume_id)
                await close_client(hetzner_client)

                audit_repo = AuditLogRepository(session)
                await audit_repo.log(
                    action="volume_delete",
                    success=True,
                    client_id=client_id,
                    resource_type="volume",
                    resource_id=volume_id,
                )

                await callback.message.edit_text("🎉✅ Volume deleted successfully.")
            except Exception as e:
                await close_client(hetzner_client)
                await callback.message.edit_text(f"⚠️❌ Deletion failed: {e!s}")
    else:
        await callback.message.edit_text("🚫❌ Action cancelled. ↩️ Go back to the previous menu.")

    await callback.answer()
    await show_volume_list(callback, client_id)


@router.callback_query(F.data.startswith(f"{CallbackAreas.VOLUME}:{CallbackTasks.EDIT}:{CallbackSteps.REMARK}"))
async def volume_edit_remark(callback: CallbackQuery, state: FSMContext):
    cb = parse_callback(callback.data)
    await state.set_state(VolumeCreateStates.waiting_remark)
    await state.update_data(volume_id=cb.target_id, client_id=int(cb.extra) if cb.extra else 0, editing=True)
    await callback.message.edit_text("✏️ Enter new remark for the volume:")
    await callback.answer()


@router.message(VolumeCreateStates.waiting_remark)
async def volume_edit_remark_received(message: Message, state: FSMContext):
    data = await state.get_data()
    if not data.get("editing"):
        return

    valid, _ = validate_remark(message.text)
    if not valid:
        await message.answer(
            "⚠️❌ Invalid remark format. 🔍 Please enter a valid remark without special characters and space."
        )
        return

    volume_id = data["volume_id"]
    client_id = data["client_id"]

    async with db.session() as session:
        client_repo = ClientRepository(session)
        client = await client_repo.get_by_id(client_id)
        token = decrypt_token(client.api_token_encrypted)
        hetzner_client = await create_client(token)

        try:
            await hetzner_client.update_volume(volume_id, name=message.text)
            await close_client(hetzner_client)

            audit_repo = AuditLogRepository(session)
            await audit_repo.log(
                action="volume_rename",
                success=True,
                client_id=client_id,
                resource_type="volume",
                resource_id=volume_id,
                details={"new_name": message.text},
            )

            await message.answer("🎉✅ Volume remark updated successfully.")
        except Exception as e:
            await close_client(hetzner_client)
            await message.answer(f"⚠️❌ Failed to update remark: {e!s}")

    await state.clear()
