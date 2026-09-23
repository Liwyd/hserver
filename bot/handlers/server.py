from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.database.base import db
from bot.database.repositories import (
    AuditLogRepository,
    ClientRepository,
    ServerAccessRepository,
    UserRepository,
)
from bot.encryption import decrypt_token
from bot.hetzner.client import close_client, create_client
from bot.states import (
    ServerAccessStates,
    ServerActionStates,
    ServerCreateStates,
    ServerRebuildStates,
    ServerUpgradeStates,
)
from bot.utils.callbacks import (
    CallbackAreas,
    CallbackSteps,
    CallbackTasks,
    create_callback,
    parse_callback,
)
from bot.utils.formatters import format_server_button, format_server_info
from bot.utils.validators import validate_chat_id, validate_remark

router = Router()


@router.callback_query(F.data.startswith(f"{CallbackAreas.SERVER}:{CallbackTasks.LIST}"))
async def server_list(callback: CallbackQuery):
    cb = parse_callback(callback.data)
    client_id = cb.target_id
    await show_server_list(callback, client_id)


async def show_server_list(callback: CallbackQuery, client_id: int):
    async with db.session() as session:
        client_repo = ClientRepository(session)
        server_access_repo = ServerAccessRepository(session)
        user_repo = UserRepository(session)

        client = await client_repo.get_by_id(client_id)
        if not client:
            await callback.answer("🔍❌ Not found [client].", show_alert=True)
            return

        user = await user_repo.get_by_telegram_id(callback.from_user.id)
        is_owner = client.owner_id == user.id
        is_admin = user.role in ("owner", "admin") or user.is_bot_admin

        token = decrypt_token(client.api_token_encrypted)
        hetzner_client = await create_client(token)
        servers = await hetzner_client.list_servers()
        await close_client(hetzner_client)

        builder = InlineKeyboardBuilder()

        for server in servers:
            has_access = True
            if not is_owner and not is_admin:
                has_access = await server_access_repo.has_access(user.id, client_id, server.id)
            if not has_access:
                continue

            builder.button(
                text=format_server_button(server),
                callback_data=create_callback(
                    CallbackAreas.SERVER, CallbackTasks.INFO, "", 0, 0, server.id, str(client_id)
                ),
            )

        builder.adjust(2)

        if is_owner or is_admin:
            builder.row(
                InlineKeyboardButton(
                    text="🖥 Create Server",
                    callback_data=create_callback(
                        CallbackAreas.SERVER, CallbackTasks.CREATE, CallbackSteps.REMARK, 0, 0, client_id
                    ),
                ),
                InlineKeyboardButton(
                    text="🔙 Back", callback_data=create_callback(CallbackAreas.CLIENT, CallbackTasks.LIST)
                ),
            )
        else:
            builder.row(
                InlineKeyboardButton(
                    text="🔙 Back", callback_data=create_callback(CallbackAreas.CLIENT, CallbackTasks.LIST)
                ),
            )

        text = "🖥 Servers Menu\n👇 Select an action from the menu below."
        await callback.message.edit_text(text, reply_markup=builder.as_markup())
        await callback.answer()


@router.callback_query(F.data.startswith(f"{CallbackAreas.SERVER}:{CallbackTasks.INFO}"))
async def server_info(callback: CallbackQuery):
    cb = parse_callback(callback.data)
    server_id = cb.target_id
    client_id = int(cb.extra) if cb.extra else 0

    await show_server_info(callback, client_id, server_id)


async def show_server_info(callback: CallbackQuery, client_id: int, server_id: int):
    async with db.session() as session:
        client_repo = ClientRepository(session)
        server_access_repo = ServerAccessRepository(session)
        user_repo = UserRepository(session)

        client = await client_repo.get_by_id(client_id)
        if not client:
            await callback.answer("🔍❌ Not found [client].", show_alert=True)
            return

        user = await user_repo.get_by_telegram_id(callback.from_user.id)
        is_owner = client.owner_id == user.id
        is_admin = user.role in ("owner", "admin") or user.is_bot_admin

        has_access = True
        if not is_owner and not is_admin:
            has_access = await server_access_repo.has_access(user.id, client_id, server_id)
        if not has_access:
            await callback.answer("⚠️ Access denied.", show_alert=True)
            return

        token = decrypt_token(client.api_token_encrypted)
        hetzner_client = await create_client(token)
        server = await hetzner_client.get_server(server_id)
        await close_client(hetzner_client)

        builder = InlineKeyboardBuilder()

        if is_owner:
            builder.row(
                InlineKeyboardButton(
                    text="✏️ Change Remark",
                    callback_data=create_callback(
                        CallbackAreas.SERVER, CallbackTasks.EDIT, CallbackSteps.REMARK, 0, 0, server_id, str(client_id)
                    ),
                ),
                InlineKeyboardButton(
                    text="🔌 Power Off",
                    callback_data=create_callback(
                        CallbackAreas.SERVER, CallbackTasks.ACTION, "power_off", 0, 0, server_id, str(client_id)
                    ),
                ),
            )
            builder.row(
                InlineKeyboardButton(
                    text="⚡️ Power On",
                    callback_data=create_callback(
                        CallbackAreas.SERVER, CallbackTasks.ACTION, "power_on", 0, 0, server_id, str(client_id)
                    ),
                ),
                InlineKeyboardButton(
                    text="🔄 Reboot",
                    callback_data=create_callback(
                        CallbackAreas.SERVER, CallbackTasks.ACTION, "reboot", 0, 0, server_id, str(client_id)
                    ),
                ),
            )
            builder.row(
                InlineKeyboardButton(
                    text="🛠 Rebuild",
                    callback_data=create_callback(
                        CallbackAreas.SERVER, CallbackTasks.ACTION, "rebuild", 0, 0, server_id, str(client_id)
                    ),
                ),
                InlineKeyboardButton(
                    text="🔓 Reset Password",
                    callback_data=create_callback(
                        CallbackAreas.SERVER, CallbackTasks.ACTION, "reset_password", 0, 0, server_id, str(client_id)
                    ),
                ),
            )
            builder.row(
                InlineKeyboardButton(
                    text="🔄 Reset",
                    callback_data=create_callback(
                        CallbackAreas.SERVER, CallbackTasks.ACTION, "reset", 0, 0, server_id, str(client_id)
                    ),
                ),
                InlineKeyboardButton(
                    text="📷 Create Snapshot",
                    callback_data=create_callback(
                        CallbackAreas.SERVER, CallbackTasks.ACTION, "create_snapshot", 0, 0, server_id, str(client_id)
                    ),
                ),
            )
            builder.row(
                InlineKeyboardButton(
                    text="⬆️ Upgrade",
                    callback_data=create_callback(
                        CallbackAreas.SERVER, CallbackTasks.ACTION, "upgrade", 0, 0, server_id, str(client_id)
                    ),
                ),
                InlineKeyboardButton(
                    text="🗑 Delete Snapshot",
                    callback_data=create_callback(
                        CallbackAreas.SERVER, CallbackTasks.ACTION, "delete_snapshot", 0, 0, server_id, str(client_id)
                    ),
                ),
            )
            builder.row(
                InlineKeyboardButton(
                    text="❌ Unassign IPv4",
                    callback_data=create_callback(
                        CallbackAreas.SERVER, CallbackTasks.ACTION, "unassign_ipv4", 0, 0, server_id, str(client_id)
                    ),
                ),
                InlineKeyboardButton(
                    text="❌ Unassign IPv6",
                    callback_data=create_callback(
                        CallbackAreas.SERVER, CallbackTasks.ACTION, "unassign_ipv6", 0, 0, server_id, str(client_id)
                    ),
                ),
            )
            builder.row(
                InlineKeyboardButton(
                    text="🔗 Assign IPv4",
                    callback_data=create_callback(
                        CallbackAreas.SERVER, CallbackTasks.ACTION, "assign_ipv4", 0, 0, server_id, str(client_id)
                    ),
                ),
                InlineKeyboardButton(
                    text="🔗 Assign IPv6",
                    callback_data=create_callback(
                        CallbackAreas.SERVER, CallbackTasks.ACTION, "assign_ipv6", 0, 0, server_id, str(client_id)
                    ),
                ),
            )
            builder.row(
                InlineKeyboardButton(
                    text="➕ Grant Access",
                    callback_data=create_callback(
                        CallbackAreas.SERVER, CallbackTasks.ACTION, "grant_access", 0, 0, server_id, str(client_id)
                    ),
                ),
                InlineKeyboardButton(
                    text="📋 List Access",
                    callback_data=create_callback(
                        CallbackAreas.SERVER, CallbackTasks.ACTION, "list_access", 0, 0, server_id, str(client_id)
                    ),
                ),
            )
            builder.row(
                InlineKeyboardButton(
                    text="❌ Revoke Access",
                    callback_data=create_callback(
                        CallbackAreas.SERVER, CallbackTasks.ACTION, "revoke_access", 0, 0, server_id, str(client_id)
                    ),
                ),
                InlineKeyboardButton(
                    text="🗑 Remove Server",
                    callback_data=create_callback(
                        CallbackAreas.SERVER,
                        CallbackTasks.DELETE,
                        CallbackSteps.CONFIRMATION,
                        0,
                        0,
                        server_id,
                        str(client_id),
                    ),
                ),
            )
        else:
            builder.row(
                InlineKeyboardButton(
                    text="✏️ Change Remark",
                    callback_data=create_callback(
                        CallbackAreas.SERVER, CallbackTasks.EDIT, CallbackSteps.REMARK, 0, 0, server_id, str(client_id)
                    ),
                ),
                InlineKeyboardButton(
                    text="🔌 Power Off",
                    callback_data=create_callback(
                        CallbackAreas.SERVER, CallbackTasks.ACTION, "power_off", 0, 0, server_id, str(client_id)
                    ),
                ),
            )
            builder.row(
                InlineKeyboardButton(
                    text="⚡️ Power On",
                    callback_data=create_callback(
                        CallbackAreas.SERVER, CallbackTasks.ACTION, "power_on", 0, 0, server_id, str(client_id)
                    ),
                ),
                InlineKeyboardButton(
                    text="🔄 Reboot",
                    callback_data=create_callback(
                        CallbackAreas.SERVER, CallbackTasks.ACTION, "reboot", 0, 0, server_id, str(client_id)
                    ),
                ),
            )
            builder.row(
                InlineKeyboardButton(
                    text="🛠 Rebuild",
                    callback_data=create_callback(
                        CallbackAreas.SERVER, CallbackTasks.ACTION, "rebuild", 0, 0, server_id, str(client_id)
                    ),
                ),
                InlineKeyboardButton(
                    text="🔓 Reset Password",
                    callback_data=create_callback(
                        CallbackAreas.SERVER, CallbackTasks.ACTION, "reset_password", 0, 0, server_id, str(client_id)
                    ),
                ),
            )
            builder.row(
                InlineKeyboardButton(
                    text="🔄 Reset",
                    callback_data=create_callback(
                        CallbackAreas.SERVER, CallbackTasks.ACTION, "reset", 0, 0, server_id, str(client_id)
                    ),
                ),
            )

        builder.row(
            InlineKeyboardButton(
                text="🔄 Refresh",
                callback_data=create_callback(
                    CallbackAreas.SERVER, CallbackTasks.REFRESH, "", 0, 0, server_id, str(client_id)
                ),
            )
        )
        builder.row(
            InlineKeyboardButton(
                text="🔙 Back",
                callback_data=create_callback(CallbackAreas.SERVER, CallbackTasks.LIST, "", 0, 0, client_id),
            ),
        )

        text = format_server_info(server)
        await callback.message.edit_text(text, reply_markup=builder.as_markup())
        await callback.answer()


@router.callback_query(F.data.startswith(f"{CallbackAreas.SERVER}:{CallbackTasks.REFRESH}"))
async def server_refresh(callback: CallbackQuery):
    cb = parse_callback(callback.data)
    server_id = cb.target_id
    client_id = int(cb.extra) if cb.extra else 0
    await show_server_info(callback, client_id, server_id)


# Server Creation Flow
@router.callback_query(F.data.startswith(f"{CallbackAreas.SERVER}:{CallbackTasks.CREATE}:{CallbackSteps.REMARK}"))
async def server_create_remark(callback: CallbackQuery, state: FSMContext):
    cb = parse_callback(callback.data)
    await state.set_state(ServerCreateStates.waiting_remark)
    await state.update_data(client_id=cb.target_id)
    await callback.message.edit_text("✏️ Enter a remark for the server:")
    await callback.answer()


@router.message(ServerCreateStates.waiting_remark)
async def server_create_remark_received(message: Message, state: FSMContext):
    valid, error = validate_remark(message.text)
    if not valid:
        await message.answer(
            "⚠️❌ Invalid remark format. 🔍 Please enter a valid remark without special characters and space."
        )
        return

    await state.update_data(remark=message.text)
    await state.set_state(ServerCreateStates.waiting_datacenter)

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
                CallbackAreas.SERVER, CallbackTasks.CREATE, CallbackSteps.DATACENTER, 0, 0, dc.id, str(client_id)
            ),
        )
    builder.adjust(1)
    builder.row(
        InlineKeyboardButton(
            text="🔙 Back", callback_data=create_callback(CallbackAreas.SERVER, CallbackTasks.LIST, "", 0, 0, client_id)
        )
    )

    await message.answer("🌍 Select a datacenter for the server:", reply_markup=builder.as_markup())


@router.callback_query(F.data.startswith(f"{CallbackAreas.SERVER}:{CallbackTasks.CREATE}:{CallbackSteps.DATACENTER}"))
async def server_create_datacenter(callback: CallbackQuery, state: FSMContext):
    cb = parse_callback(callback.data)
    datacenter_id = cb.target_id
    client_id = int(cb.extra) if cb.extra else 0

    await state.update_data(datacenter_id=datacenter_id)
    await state.set_state(ServerCreateStates.waiting_plan)

    data = await state.get_data()

    async with db.session() as session:
        client_repo = ClientRepository(session)
        client = await client_repo.get_by_id(client_id)
        token = decrypt_token(client.api_token_encrypted)
        hetzner_client = await create_client(token)
        server_types = await hetzner_client.list_server_types()
        await close_client(hetzner_client)

    builder = InlineKeyboardBuilder()
    for st in server_types:
        price_monthly = next(
            (p.get("price_monthly", {}).get("net", 0) for p in st.prices if p.get("location") == "fsn1"), 0
        )
        builder.button(
            text=f"{st.name} [{st.memory} GB RAM, {st.cores} CPU, {price_monthly:.2f}€]",
            callback_data=create_callback(
                CallbackAreas.SERVER, CallbackTasks.CREATE, CallbackSteps.PLAN, 0, 0, st.id, str(client_id)
            ),
        )
    builder.adjust(1)
    builder.row(
        InlineKeyboardButton(
            text="🔙 Back", callback_data=create_callback(CallbackAreas.SERVER, CallbackTasks.LIST, "", 0, 0, client_id)
        )
    )

    await callback.message.edit_text("💰 Select a plan for the server:", reply_markup=builder.as_markup())
    await callback.answer()


@router.callback_query(F.data.startswith(f"{CallbackAreas.SERVER}:{CallbackTasks.CREATE}:{CallbackSteps.PLAN}"))
async def server_create_plan(callback: CallbackQuery, state: FSMContext):
    cb = parse_callback(callback.data)
    server_type_id = cb.target_id
    client_id = int(cb.extra) if cb.extra else 0

    await state.update_data(server_type_id=server_type_id)
    await state.set_state(ServerCreateStates.waiting_image)

    data = await state.get_data()

    async with db.session() as session:
        client_repo = ClientRepository(session)
        client = await client_repo.get_by_id(client_id)
        token = decrypt_token(client.api_token_encrypted)
        hetzner_client = await create_client(token)
        images = await hetzner_client.list_images()
        await close_client(hetzner_client)

    snapshots = [img for img in images if img.type == "snapshot"]
    system_images = [img for img in images if img.type == "system"]

    builder = InlineKeyboardBuilder()

    for img in snapshots:
        builder.button(
            text=f"📸 {img.name or img.description}",
            callback_data=create_callback(
                CallbackAreas.SERVER, CallbackTasks.CREATE, CallbackSteps.IMAGE, 0, 0, img.id, str(client_id)
            ),
        )

    for img in system_images[:20]:
        builder.button(
            text=f"🖼 {img.description}",
            callback_data=create_callback(
                CallbackAreas.SERVER, CallbackTasks.CREATE, CallbackSteps.IMAGE, 0, 0, img.id, str(client_id)
            ),
        )

    builder.adjust(1)
    builder.row(
        InlineKeyboardButton(
            text="🔙 Back", callback_data=create_callback(CallbackAreas.SERVER, CallbackTasks.LIST, "", 0, 0, client_id)
        )
    )

    await callback.message.edit_text("🖼 Select an image for the server:", reply_markup=builder.as_markup())
    await callback.answer()


@router.callback_query(F.data.startswith(f"{CallbackAreas.SERVER}:{CallbackTasks.CREATE}:{CallbackSteps.IMAGE}"))
async def server_create_image(callback: CallbackQuery, state: FSMContext):
    cb = parse_callback(callback.data)
    image_id = cb.target_id
    client_id = int(cb.extra) if cb.extra else 0

    await state.update_data(image_id=image_id)
    await state.set_state(ServerCreateStates.waiting_confirmation)

    data = await state.get_data()

    async with db.session() as session:
        client_repo = ClientRepository(session)
        client = await client_repo.get_by_id(client_id)
        token = decrypt_token(client.api_token_encrypted)
        hetzner_client = await create_client(token)

        datacenter = next(
            (dc for dc in await hetzner_client.list_datacenters() if dc.id == data["datacenter_id"]), None
        )
        server_type = next(
            (st for st in await hetzner_client.list_server_types() if st.id == data["server_type_id"]), None
        )
        image = next((img for img in await hetzner_client.list_images() if img.id == image_id), None)

        await close_client(hetzner_client)

    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="✅ Yes",
            callback_data=create_callback(
                CallbackAreas.SERVER, CallbackTasks.CREATE, CallbackSteps.CONFIRMATION, 0, 1, 0, str(client_id)
            ),
        ),
        InlineKeyboardButton(
            text="❌ No",
            callback_data=create_callback(
                CallbackAreas.SERVER, CallbackTasks.CREATE, CallbackSteps.CONFIRMATION, 0, 0, 0, str(client_id)
            ),
        ),
    )

    text = (
        f"📋 Server Creation Summary\n\n"
        f"📛 Name: {data['remark']}\n"
        f"🌍 Datacenter: {datacenter.name} ({datacenter.id})\n"
        f"💰 Plan: {server_type.name} ({server_type.cores} cores, {server_type.memory}GB RAM)\n"
        f"🖼 Image: {image.name or image.description}\n\n"
        f"⚠️ Do you want to create this server?"
    )
    await callback.message.edit_text(text, reply_markup=builder.as_markup())
    await callback.answer()


@router.callback_query(F.data.startswith(f"{CallbackAreas.SERVER}:{CallbackTasks.CREATE}:{CallbackSteps.CONFIRMATION}"))
async def server_create_confirm(callback: CallbackQuery, state: FSMContext):
    cb = parse_callback(callback.data)
    client_id = int(cb.extra) if cb.extra else 0

    if cb.approve != 1:
        await callback.message.edit_text("🚫❌ Action cancelled. ↩️ Go back to the previous menu.")
        await state.clear()
        await callback.answer()
        return

    data = await state.get_data()

    async with db.session() as session:
        client_repo = ClientRepository(session)
        client = await client_repo.get_by_id(client_id)
        token = decrypt_token(client.api_token_encrypted)
        hetzner_client = await create_client(token)

        from bot.hetzner.models import ServerCreateRequest

        request = ServerCreateRequest(
            name=data["remark"],
            server_type=str(data["server_type_id"]),
            image=str(data["image_id"]),
            datacenter=str(data["datacenter_id"]),
            ssh_keys=[],
            labels={},
        )

        try:
            response = await hetzner_client.create_server(request)
            await close_client(hetzner_client)

            audit_repo = AuditLogRepository(session)
            user_repo = UserRepository(session)
            user = await user_repo.get_by_telegram_id(callback.from_user.id)
            await audit_repo.log(
                action="server_create",
                success=True,
                user_id=user.id if user else None,
                client_id=client_id,
                resource_type="server",
                resource_id=response.server.id,
                details={"remark": data["remark"]},
            )

            await callback.message.edit_text("🎉✅ Server created successfully. ⚙️ You can now manage the server.")
        except Exception as e:
            await close_client(hetzner_client)
            await callback.message.edit_text(f"⚠️❌ Server creation failed: {e!s}")

    await state.clear()
    await callback.answer()
    await show_server_list(callback, client_id)


# Server Actions with Confirmation
ACTION_MESSAGES = {
    "power_off": "Power Off",
    "power_on": "Power On",
    "reboot": "Reboot",
    "reset": "Reset",
    "reset_password": "Reset Password",
    "delete_snapshot": "Delete Snapshot",
    "unassign_ipv4": "Unassign IPv4",
    "unassign_ipv6": "Unassign IPv6",
    "remove_server": "Remove Server",
}


@router.callback_query(F.data.startswith(f"{CallbackAreas.SERVER}:{CallbackTasks.ACTION}"))
async def server_action(callback: CallbackQuery, state: FSMContext):
    cb = parse_callback(callback.data)
    action = cb.step
    server_id = cb.target_id
    client_id = int(cb.extra) if cb.extra else 0

    if action in (
        "rebuild",
        "upgrade",
        "create_snapshot",
        "delete_snapshot",
        "assign_ipv4",
        "assign_ipv6",
        "grant_access",
        "list_access",
        "revoke_access",
    ):
        await handle_special_action(callback, state, action, server_id, client_id)
        return

    if action not in ACTION_MESSAGES:
        await callback.answer("Unknown action", show_alert=True)
        return

    await state.set_state(ServerActionStates.waiting_confirmation)
    await state.update_data(action=action, server_id=server_id, client_id=client_id)

    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="✅ Yes",
            callback_data=create_callback(
                CallbackAreas.SERVER, CallbackTasks.ACTION, f"{action}_confirm", 0, 1, server_id, str(client_id)
            ),
        ),
        InlineKeyboardButton(
            text="❌ No",
            callback_data=create_callback(
                CallbackAreas.SERVER, CallbackTasks.ACTION, f"{action}_confirm", 0, 0, server_id, str(client_id)
            ),
        ),
    )

    text = f"❓ Are you sure you want to {ACTION_MESSAGES[action].lower()}?\n🔘 Please approve to continue or cancel to go back."
    await callback.message.edit_text(text, reply_markup=builder.as_markup())
    await callback.answer()


async def handle_special_action(
    callback: CallbackQuery, state: FSMContext, action: str, server_id: int, client_id: int
):
    if action == "rebuild":
        await state.set_state(ServerRebuildStates.waiting_image)
        await state.update_data(server_id=server_id, client_id=client_id)

        async with db.session() as session:
            client_repo = ClientRepository(session)
            client = await client_repo.get_by_id(client_id)
            token = decrypt_token(client.api_token_encrypted)
            hetzner_client = await create_client(token)
            images = await hetzner_client.list_images()
            await close_client(hetzner_client)

        snapshots = [img for img in images if img.type == "snapshot"]
        system_images = [img for img in images if img.type == "system"]

        builder = InlineKeyboardBuilder()
        for img in snapshots:
            builder.button(
                text=f"📸 {img.name or img.description}",
                callback_data=create_callback(
                    CallbackAreas.SERVER,
                    CallbackTasks.ACTION,
                    "rebuild_image",
                    0,
                    0,
                    img.id,
                    f"{server_id}:{client_id}",
                ),
            )
        for img in system_images[:20]:
            builder.button(
                text=f"🖼 {img.description}",
                callback_data=create_callback(
                    CallbackAreas.SERVER,
                    CallbackTasks.ACTION,
                    "rebuild_image",
                    0,
                    0,
                    img.id,
                    f"{server_id}:{client_id}",
                ),
            )
        builder.adjust(1)
        builder.row(
            InlineKeyboardButton(
                text="🔙 Back",
                callback_data=create_callback(
                    CallbackAreas.SERVER, CallbackTasks.INFO, "", 0, 0, server_id, str(client_id)
                ),
            )
        )

        await callback.message.edit_text("🖼 Select an image for rebuild:", reply_markup=builder.as_markup())

    elif action == "upgrade":
        await state.set_state(ServerUpgradeStates.waiting_plan)
        await state.update_data(server_id=server_id, client_id=client_id)

        async with db.session() as session:
            client_repo = ClientRepository(session)
            client = await client_repo.get_by_id(client_id)
            token = decrypt_token(client.api_token_encrypted)
            hetzner_client = await create_client(token)
            server = await hetzner_client.get_server(server_id)
            server_types = await hetzner_client.list_server_types(architecture=server.server_type.get("architecture"))
            await close_client(hetzner_client)

        current_type = server.server_type.get("name")
        builder = InlineKeyboardBuilder()
        for st in server_types:
            if st.name == current_type:
                continue
            if st.cores >= server.server_type.get("cores", 0) and st.memory >= server.server_type.get("memory", 0):
                builder.button(
                    text=f"{st.name} [{st.memory} GB RAM, {st.cores} CPU]",
                    callback_data=create_callback(
                        CallbackAreas.SERVER,
                        CallbackTasks.ACTION,
                        "upgrade_plan",
                        0,
                        0,
                        st.id,
                        f"{server_id}:{client_id}",
                    ),
                )
        builder.adjust(1)
        builder.row(
            InlineKeyboardButton(
                text="🔙 Back",
                callback_data=create_callback(
                    CallbackAreas.SERVER, CallbackTasks.INFO, "", 0, 0, server_id, str(client_id)
                ),
            )
        )

        await callback.message.edit_text(
            f"⬆️ Select a plan to upgrade the server:\n\nCurrent: {current_type}", reply_markup=builder.as_markup()
        )

    elif action == "create_snapshot":
        await state.set_state(ServerActionStates.waiting_confirmation)
        await state.update_data(action="create_snapshot", server_id=server_id, client_id=client_id, step="remark")
        await callback.message.edit_text("✏️ Enter a remark for the snapshot:")

    elif action == "delete_snapshot":
        await state.set_state(ServerActionStates.waiting_confirmation)
        await state.update_data(action="delete_snapshot", server_id=server_id, client_id=client_id, step="select")

        async with db.session() as session:
            client_repo = ClientRepository(session)
            client = await client_repo.get_by_id(client_id)
            token = decrypt_token(client.api_token_encrypted)
            hetzner_client = await create_client(token)
            snapshots = await hetzner_client.list_snapshots()
            await close_client(hetzner_client)

        server_snapshots = [s for s in snapshots if s.server and s.server.get("id") == server_id]

        builder = InlineKeyboardBuilder()
        for snap in server_snapshots:
            builder.button(
                text=snap.name or snap.description,
                callback_data=create_callback(
                    CallbackAreas.SERVER,
                    CallbackTasks.ACTION,
                    "delete_snapshot_select",
                    0,
                    0,
                    snap.id,
                    f"{server_id}:{client_id}",
                ),
            )
        builder.adjust(1)
        builder.row(
            InlineKeyboardButton(
                text="🔙 Back",
                callback_data=create_callback(
                    CallbackAreas.SERVER, CallbackTasks.INFO, "", 0, 0, server_id, str(client_id)
                ),
            )
        )

        await callback.message.edit_text("🗑 Select a snapshot to delete:", reply_markup=builder.as_markup())

    elif action in ("assign_ipv4", "assign_ipv6"):
        ip_type = "ipv4" if action == "assign_ipv4" else "ipv6"

        async with db.session() as session:
            client_repo = ClientRepository(session)
            client = await client_repo.get_by_id(client_id)
            token = decrypt_token(client.api_token_encrypted)
            hetzner_client = await create_client(token)
            server = await hetzner_client.get_server(server_id)

            has_ip = False
            if ip_type == "ipv4":
                has_ip = server.public_net.get("ipv4", {}).get("ip") is not None
            else:
                has_ip = server.public_net.get("ipv6", {}).get("ip") is not None

            await close_client(hetzner_client)

        if has_ip:
            await callback.message.edit_text(
                "🔗 First Unassign IPv4" if ip_type == "ipv4" else "🔗 First Unassign IPv6"
            )
            await callback.answer()
            return

        await state.set_state(ServerActionStates.waiting_confirmation)
        await state.update_data(action=action, server_id=server_id, client_id=client_id, step="select")

        async with db.session() as session:
            client_repo = ClientRepository(session)
            client = await client_repo.get_by_id(client_id)
            token = decrypt_token(client.api_token_encrypted)
            hetzner_client = await create_client(token)
            primary_ips = await hetzner_client.list_primary_ips()
            await close_client(hetzner_client)

        available_ips = [ip for ip in primary_ips if ip.type == ip_type and ip.assignee_id is None]

        builder = InlineKeyboardBuilder()
        for ip in available_ips:
            builder.button(
                text=f"{ip.name} [{ip.ip}]",
                callback_data=create_callback(
                    CallbackAreas.SERVER,
                    CallbackTasks.ACTION,
                    f"{action}_select",
                    0,
                    0,
                    ip.id,
                    f"{server_id}:{client_id}",
                ),
            )
        builder.adjust(1)
        builder.row(
            InlineKeyboardButton(
                text="🔙 Back",
                callback_data=create_callback(
                    CallbackAreas.SERVER, CallbackTasks.INFO, "", 0, 0, server_id, str(client_id)
                ),
            )
        )

        await callback.message.edit_text(
            f"🔗 Select IPv{4 if ip_type == 'ipv4' else 6} to assign:", reply_markup=builder.as_markup()
        )

    elif action == "grant_access":
        await state.set_state(ServerAccessStates.waiting_chat_id)
        await state.update_data(server_id=server_id, client_id=client_id, action="grant")
        await callback.message.edit_text("✏️ Enter the Chat ID to grant access:")

    elif action == "list_access":
        async with db.session() as session:
            server_access_repo = ServerAccessRepository(session)
            user_repo = UserRepository(session)
            accesses = await server_access_repo.list_for_server(client_id, server_id)

            text = "📋 Server Access List\n\n"
            for access in accesses:
                user = await user_repo.get_by_id(access.user_id)
                if user:
                    text += f"• {user.telegram_id} — {user.first_name or ''} {user.last_name or ''} [{'env' if user.is_bot_admin else 'bot'}]\n"

            builder = InlineKeyboardBuilder()
            builder.row(
                InlineKeyboardButton(
                    text="🔙 Back",
                    callback_data=create_callback(
                        CallbackAreas.SERVER, CallbackTasks.INFO, "", 0, 0, server_id, str(client_id)
                    ),
                )
            )
            await callback.message.edit_text(text, reply_markup=builder.as_markup())

    elif action == "revoke_access":
        await state.set_state(ServerAccessStates.waiting_chat_id)
        await state.update_data(server_id=server_id, client_id=client_id, action="revoke")
        await callback.message.edit_text("✏️ Enter the Chat ID to revoke access:")

    await callback.answer()


@router.callback_query(F.data.startswith(f"{CallbackAreas.SERVER}:{CallbackTasks.ACTION}:rebuild_image"))
async def server_rebuild_image(callback: CallbackQuery, state: FSMContext):
    cb = parse_callback(callback.data)
    image_id = cb.target_id
    server_id, client_id = map(int, cb.extra.split(":"))

    await state.update_data(image_id=image_id)
    await state.set_state(ServerRebuildStates.waiting_confirmation)

    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="✅ Yes",
            callback_data=create_callback(
                CallbackAreas.SERVER,
                CallbackTasks.ACTION,
                "rebuild_confirm",
                0,
                1,
                server_id,
                f"{image_id}:{client_id}",
            ),
        ),
        InlineKeyboardButton(
            text="❌ No",
            callback_data=create_callback(
                CallbackAreas.SERVER,
                CallbackTasks.ACTION,
                "rebuild_confirm",
                0,
                0,
                server_id,
                f"{image_id}:{client_id}",
            ),
        ),
    )

    await callback.message.edit_text(
        "❓ Are you sure you want to rebuild the server?\n🔘 Please approve to continue or cancel to go back.",
        reply_markup=builder.as_markup(),
    )
    await callback.answer()


@router.callback_query(F.data.startswith(f"{CallbackAreas.SERVER}:{CallbackTasks.ACTION}:rebuild_confirm"))
async def server_rebuild_confirm(callback: CallbackQuery, state: FSMContext):
    cb = parse_callback(callback.data)
    server_id = cb.target_id
    image_id, client_id = map(int, cb.extra.split(":"))

    if cb.approve != 1:
        await callback.message.edit_text("🚫❌ Action cancelled. ↩️ Go back to the previous menu.")
        await state.clear()
        await callback.answer()
        return

    await execute_server_action(callback, "rebuild", server_id, client_id, image_id=image_id)
    await state.clear()


@router.callback_query(F.data.startswith(f"{CallbackAreas.SERVER}:{CallbackTasks.ACTION}:upgrade_plan"))
async def server_upgrade_plan(callback: CallbackQuery, state: FSMContext):
    cb = parse_callback(callback.data)
    plan_id = cb.target_id
    server_id, client_id = map(int, cb.extra.split(":"))

    await state.update_data(plan_id=plan_id)
    await state.set_state(ServerUpgradeStates.waiting_confirmation)

    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="✅ Yes",
            callback_data=create_callback(
                CallbackAreas.SERVER, CallbackTasks.ACTION, "upgrade_confirm", 0, 1, server_id, f"{plan_id}:{client_id}"
            ),
        ),
        InlineKeyboardButton(
            text="❌ No",
            callback_data=create_callback(
                CallbackAreas.SERVER, CallbackTasks.ACTION, "upgrade_confirm", 0, 0, server_id, f"{plan_id}:{client_id}"
            ),
        ),
    )

    await callback.message.edit_text(
        "❓ Are you sure you want to upgrade the server?\n🔘 Please approve to continue or cancel to go back.",
        reply_markup=builder.as_markup(),
    )
    await callback.answer()


@router.callback_query(F.data.startswith(f"{CallbackAreas.SERVER}:{CallbackTasks.ACTION}:upgrade_confirm"))
async def server_upgrade_confirm(callback: CallbackQuery, state: FSMContext):
    cb = parse_callback(callback.data)
    server_id = cb.target_id
    plan_id, client_id = map(int, cb.extra.split(":"))

    if cb.approve != 1:
        await callback.message.edit_text("🚫❌ Action cancelled. ↩️ Go back to the previous menu.")
        await state.clear()
        await callback.answer()
        return

    await execute_server_action(callback, "upgrade", server_id, client_id, plan_id=plan_id)
    await state.clear()


@router.callback_query(F.data.startswith(f"{CallbackAreas.SERVER}:{CallbackTasks.ACTION}:delete_snapshot_select"))
async def server_delete_snapshot_select(callback: CallbackQuery, state: FSMContext):
    cb = parse_callback(callback.data)
    snapshot_id = cb.target_id
    server_id, client_id = map(int, cb.extra.split(":"))

    await state.update_data(snapshot_id=snapshot_id)
    await state.set_state(SnapshotDeleteStates.waiting_confirmation)

    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="✅ Yes",
            callback_data=create_callback(
                CallbackAreas.SERVER,
                CallbackTasks.ACTION,
                "delete_snapshot_confirm",
                0,
                1,
                server_id,
                f"{snapshot_id}:{client_id}",
            ),
        ),
        InlineKeyboardButton(
            text="❌ No",
            callback_data=create_callback(
                CallbackAreas.SERVER,
                CallbackTasks.ACTION,
                "delete_snapshot_confirm",
                0,
                0,
                server_id,
                f"{snapshot_id}:{client_id}",
            ),
        ),
    )

    await callback.message.edit_text(
        "❓ Are you sure you want to delete this snapshot?\n🔘 Please approve to continue or cancel to go back.",
        reply_markup=builder.as_markup(),
    )
    await callback.answer()


@router.callback_query(F.data.startswith(f"{CallbackAreas.SERVER}:{CallbackTasks.ACTION}:delete_snapshot_confirm"))
async def server_delete_snapshot_confirm(callback: CallbackQuery, state: FSMContext):
    cb = parse_callback(callback.data)
    server_id = cb.target_id
    snapshot_id, client_id = map(int, cb.extra.split(":"))

    if cb.approve != 1:
        await callback.message.edit_text("🚫❌ Action cancelled. ↩️ Go back to the previous menu.")
        await state.clear()
        await callback.answer()
        return

    await execute_server_action(callback, "delete_snapshot", server_id, client_id, snapshot_id=snapshot_id)
    await state.clear()


@router.callback_query(F.data.startswith(f"{CallbackAreas.SERVER}:{CallbackTasks.ACTION}:assign_ipv4_select"))
async def server_assign_ipv4_select(callback: CallbackQuery, state: FSMContext):
    cb = parse_callback(callback.data)
    ip_id = cb.target_id
    server_id, client_id = map(int, cb.extra.split(":"))

    await execute_server_action(callback, "assign_ipv4", server_id, client_id, ip_id=ip_id)


@router.callback_query(F.data.startswith(f"{CallbackAreas.SERVER}:{CallbackTasks.ACTION}:assign_ipv6_select"))
async def server_assign_ipv6_select(callback: CallbackQuery, state: FSMContext):
    cb = parse_callback(callback.data)
    ip_id = cb.target_id
    server_id, client_id = map(int, cb.extra.split(":"))

    await execute_server_action(callback, "assign_ipv6", server_id, client_id, ip_id=ip_id)


async def execute_server_action(callback: CallbackQuery, action: str, server_id: int, client_id: int, **kwargs):
    async with db.session() as session:
        client_repo = ClientRepository(session)
        client = await client_repo.get_by_id(client_id)
        token = decrypt_token(client.api_token_encrypted)
        hetzner_client = await create_client(token)

        try:
            if action == "power_off":
                await hetzner_client.power_off(server_id)
            elif action == "power_on":
                await hetzner_client.power_on(server_id)
            elif action == "reboot":
                await hetzner_client.reboot(server_id)
            elif action == "reset":
                await hetzner_client.reset(server_id)
            elif action == "reset_password":
                result = await hetzner_client.reset_password(server_id)
                password = result.get("root_password", "N/A")
                await callback.message.answer(f"🔓 New root password: <code>{password}</code>", parse_mode="HTML")
            elif action == "rebuild":
                image_id = kwargs.get("image_id")
                await hetzner_client.rebuild(server_id, str(image_id))
            elif action == "upgrade":
                plan_id = kwargs.get("plan_id")
                await hetzner_client.upgrade(server_id, str(plan_id))
            elif action == "create_snapshot":
                data = await state.get_data()
                remark = data.get("remark", f"snapshot-{server_id}")
                await hetzner_client.create_snapshot(server_id, remark)
            elif action == "delete_snapshot":
                snapshot_id = kwargs.get("snapshot_id")
                await hetzner_client.delete_snapshot(snapshot_id)
            elif action == "unassign_ipv4":
                await hetzner_client.unassign_primary_ip(server_id, "ipv4")
            elif action == "unassign_ipv6":
                await hetzner_client.unassign_primary_ip(server_id, "ipv6")
            elif action == "assign_ipv4" or action == "assign_ipv6":
                ip_id = kwargs.get("ip_id")
                await hetzner_client.assign_primary_ip(server_id, ip_id)
            elif action == "remove_server":
                await hetzner_client.delete_server(server_id)

            await close_client(hetzner_client)

            audit_repo = AuditLogRepository(session)
            user_repo = UserRepository(session)
            user = await user_repo.get_by_telegram_id(callback.from_user.id)
            await audit_repo.log(
                action=f"server_{action}",
                success=True,
                user_id=user.id if user else None,
                client_id=client_id,
                resource_type="server",
                resource_id=server_id,
            )

            await callback.message.edit_text("🎉✅ Action completed successfully.")

        except Exception as e:
            await close_client(hetzner_client)
            await callback.message.edit_text(f"⚠️❌ Action failed: {e!s}")

    await callback.answer()
    await show_server_info(callback, client_id, server_id)


@router.message(ServerActionStates.waiting_confirmation)
async def server_action_snapshot_remark(message: Message, state: FSMContext):
    data = await state.get_data()
    action = data.get("action")

    if action == "create_snapshot":
        if data.get("step") == "remark":
            await state.update_data(remark=message.text, step="confirm")

            builder = InlineKeyboardBuilder()
            builder.row(
                InlineKeyboardButton(
                    text="✅ Yes",
                    callback_data=create_callback(
                        CallbackAreas.SERVER,
                        CallbackTasks.ACTION,
                        "create_snapshot_confirm",
                        0,
                        1,
                        data["server_id"],
                        str(data["client_id"]),
                    ),
                ),
                InlineKeyboardButton(
                    text="❌ No",
                    callback_data=create_callback(
                        CallbackAreas.SERVER,
                        CallbackTasks.ACTION,
                        "create_snapshot_confirm",
                        0,
                        0,
                        data["server_id"],
                        str(data["client_id"]),
                    ),
                ),
            )
            await message.answer(
                "❓ Are you sure you want to create this snapshot?\n🔘 Please approve to continue or cancel to go back.",
                reply_markup=builder.as_markup(),
            )


@router.callback_query(F.data.startswith(f"{CallbackAreas.SERVER}:{CallbackTasks.ACTION}:create_snapshot_confirm"))
async def server_create_snapshot_confirm(callback: CallbackQuery, state: FSMContext):
    cb = parse_callback(callback.data)
    server_id = cb.target_id
    client_id = int(cb.extra) if cb.extra else 0

    if cb.approve != 1:
        await callback.message.edit_text("🚫❌ Action cancelled. ↩️ Go back to the previous menu.")
        await state.clear()
        await callback.answer()
        return

    data = await state.get_data()
    remark = data.get("remark", f"snapshot-{server_id}")

    await execute_server_action(callback, "create_snapshot", server_id, client_id, remark=remark)
    await state.clear()


@router.message(ServerAccessStates.waiting_chat_id)
async def server_access_chat_id(message: Message, state: FSMContext):
    valid, error, chat_id = validate_chat_id(message.text)
    if not valid:
        await message.answer(f"⚠️❌ {error}")
        return

    data = await state.get_data()
    server_id = data["server_id"]
    client_id = data["client_id"]
    action = data["action"]

    async with db.session() as session:
        user_repo = UserRepository(session)
        server_access_repo = ServerAccessRepository(session)
        audit_repo = AuditLogRepository(session)

        target_user = await user_repo.get_by_telegram_id(chat_id)
        if not target_user:
            await message.answer("🔍❌ User not found. They must have started the bot first.")
            await state.clear()
            return

        if action == "grant":
            exists = await server_access_repo.has_access(target_user.id, client_id, server_id)
            if exists:
                await message.answer("⚠️❌ User already has access to this server.")
            else:
                await server_access_repo.grant(client_id, server_id, target_user.id, message.from_user.id)
                await audit_repo.log(
                    action="server_grant_access",
                    success=True,
                    user_id=message.from_user.id,
                    client_id=client_id,
                    resource_type="server",
                    resource_id=server_id,
                    details={"target_user_id": target_user.id},
                )
                await message.answer("🎉✅ Access granted successfully.")
        elif action == "revoke":
            success = await server_access_repo.revoke(client_id, server_id, target_user.id)
            if success:
                await audit_repo.log(
                    action="server_revoke_access",
                    success=True,
                    user_id=message.from_user.id,
                    client_id=client_id,
                    resource_type="server",
                    resource_id=server_id,
                    details={"target_user_id": target_user.id},
                )
                await message.answer("🎉✅ Access revoked successfully.")
            else:
                await message.answer("⚠️❌ User did not have access to this server.")

    await state.clear()


@router.callback_query(F.data.startswith(f"{CallbackAreas.SERVER}:{CallbackTasks.EDIT}:{CallbackSteps.REMARK}"))
async def server_edit_remark(callback: CallbackQuery, state: FSMContext):
    cb = parse_callback(callback.data)
    await state.set_state(ServerCreateStates.waiting_remark)
    await state.update_data(server_id=cb.target_id, client_id=int(cb.extra) if cb.extra else 0, editing=True)
    await callback.message.edit_text("✏️ Enter new remark for the server:")
    await callback.answer()


@router.message(ServerCreateStates.waiting_remark)
async def server_edit_remark_received(message: Message, state: FSMContext):
    data = await state.get_data()
    if not data.get("editing"):
        return

    valid, error = validate_remark(message.text)
    if not valid:
        await message.answer(
            "⚠️❌ Invalid remark format. 🔍 Please enter a valid remark without special characters and space."
        )
        return

    server_id = data["server_id"]
    client_id = data["client_id"]

    async with db.session() as session:
        client_repo = ClientRepository(session)
        client = await client_repo.get_by_id(client_id)
        token = decrypt_token(client.api_token_encrypted)
        hetzner_client = await create_client(token)

        try:
            await hetzner_client.change_server_alias(server_id, message.text)
            await close_client(hetzner_client)

            audit_repo = AuditLogRepository(session)
            await audit_repo.log(
                action="server_rename",
                success=True,
                client_id=client_id,
                resource_type="server",
                resource_id=server_id,
                details={"new_name": message.text},
            )

            await message.answer("🎉✅ Server remark updated successfully.")
        except Exception as e:
            await close_client(hetzner_client)
            await message.answer(f"⚠️❌ Failed to update remark: {e!s}")

    await state.clear()


@router.callback_query(F.data.startswith(f"{CallbackAreas.SERVER}:{CallbackTasks.DELETE}:{CallbackSteps.CONFIRMATION}"))
async def server_delete_confirm(callback: CallbackQuery):
    cb = parse_callback(callback.data)
    server_id = cb.target_id
    client_id = int(cb.extra) if cb.extra else 0

    if cb.approve == 1:
        await execute_server_action(callback, "remove_server", server_id, client_id)
    else:
        await callback.message.edit_text("🚫❌ Action cancelled. ↩️ Go back to the previous menu.")

    await callback.answer()
