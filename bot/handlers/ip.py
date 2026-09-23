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
from bot.states import FloatingIPCreateStates, PrimaryIPCreateStates
from bot.utils.callbacks import (
    CallbackAreas,
    CallbackSteps,
    CallbackTasks,
    create_callback,
    parse_callback,
)
from bot.utils.formatters import format_floating_ip_info, format_primary_ip_info

router = Router()


# Primary IPs
@router.callback_query(F.data.startswith(f"{CallbackAreas.PRIMARY_IP}:{CallbackTasks.LIST}"))
async def primary_ip_list(callback: CallbackQuery):
    cb = parse_callback(callback.data)
    client_id = cb.target_id
    await show_primary_ip_list(callback, client_id)


async def show_primary_ip_list(callback: CallbackQuery, client_id: int):
    async with db.session() as session:
        client_repo = ClientRepository(session)
        client = await client_repo.get_by_id(client_id)
        if not client:
            await callback.answer("🔍❌ Not found [client].", show_alert=True)
            return

        token = decrypt_token(client.api_token_encrypted)
        hetzner_client = await create_client(token)
        ips = await hetzner_client.list_primary_ips()
        await close_client(hetzner_client)

    builder = InlineKeyboardBuilder()
    for ip in ips:
        builder.button(
            text=f"{ip.name} [{ip.ip}]",
            callback_data=create_callback(
                CallbackAreas.PRIMARY_IP, CallbackTasks.INFO, "", 0, 0, ip.id, str(client_id)
            ),
        )
    builder.adjust(1)

    builder.row(
        InlineKeyboardButton(
            text="➕ Create IPv4",
            callback_data=create_callback(
                CallbackAreas.PRIMARY_IP, CallbackTasks.CREATE, CallbackSteps.TYPE, 0, 0, client_id, "ipv4"
            ),
        ),
        InlineKeyboardButton(
            text="➕ Create IPv6",
            callback_data=create_callback(
                CallbackAreas.PRIMARY_IP, CallbackTasks.CREATE, CallbackSteps.TYPE, 0, 0, client_id, "ipv6"
            ),
        ),
    )
    builder.row(
        InlineKeyboardButton(text="🔙 Back", callback_data=create_callback(CallbackAreas.CLIENT, CallbackTasks.LIST))
    )

    text = "🌐 Primary IPs Menu\n👇 Select an action from the menu below."
    await callback.message.edit_text(text, reply_markup=builder.as_markup())
    await callback.answer()


@router.callback_query(F.data.startswith(f"{CallbackAreas.PRIMARY_IP}:{CallbackTasks.INFO}"))
async def primary_ip_info(callback: CallbackQuery):
    cb = parse_callback(callback.data)
    ip_id = cb.target_id
    client_id = int(cb.extra) if cb.extra else 0

    async with db.session() as session:
        client_repo = ClientRepository(session)
        client = await client_repo.get_by_id(client_id)
        if not client:
            await callback.answer("🔍❌ Not found [client].", show_alert=True)
            return

        token = decrypt_token(client.api_token_encrypted)
        hetzner_client = await create_client(token)
        ip = await hetzner_client.get_primary_ip(ip_id)
        await close_client(hetzner_client)

    is_assigned = ip.assignee_id is not None

    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="✏️ Change Remark",
            callback_data=create_callback(
                CallbackAreas.PRIMARY_IP, CallbackTasks.EDIT, CallbackSteps.REMARK, 0, 0, ip_id, str(client_id)
            ),
        ),
    )
    if is_assigned:
        builder.row(
            InlineKeyboardButton(
                text="❌ Unassign IP",
                callback_data=create_callback(
                    CallbackAreas.PRIMARY_IP, CallbackTasks.ACTION, "unassign", 0, 0, ip_id, str(client_id)
                ),
            ),
        )
    else:
        builder.row(
            InlineKeyboardButton(
                text="🔗 Assign IP",
                callback_data=create_callback(
                    CallbackAreas.PRIMARY_IP, CallbackTasks.ACTION, "assign", 0, 0, ip_id, str(client_id)
                ),
            ),
        )
    builder.row(
        InlineKeyboardButton(
            text="🗑 Delete IP",
            callback_data=create_callback(
                CallbackAreas.PRIMARY_IP, CallbackTasks.DELETE, CallbackSteps.CONFIRMATION, 0, 0, ip_id, str(client_id)
            ),
        ),
    )
    builder.row(
        InlineKeyboardButton(
            text="🔙 Back",
            callback_data=create_callback(CallbackAreas.PRIMARY_IP, CallbackTasks.LIST, "", 0, 0, client_id),
        ),
    )

    text = format_primary_ip_info(ip)
    await callback.message.edit_text(text, reply_markup=builder.as_markup())
    await callback.answer()


@router.callback_query(F.data.startswith(f"{CallbackAreas.PRIMARY_IP}:{CallbackTasks.CREATE}:{CallbackSteps.TYPE}"))
async def primary_ip_create_type(callback: CallbackQuery, state: FSMContext):
    cb = parse_callback(callback.data)
    ip_type = cb.extra
    client_id = cb.target_id

    await state.set_state(PrimaryIPCreateStates.waiting_location)
    await state.update_data(ip_type=ip_type, client_id=client_id)

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
                CallbackAreas.PRIMARY_IP,
                CallbackTasks.CREATE,
                CallbackSteps.LOCATION,
                0,
                0,
                dc.id,
                f"{ip_type}:{client_id}",
            ),
        )
    builder.adjust(1)
    builder.row(
        InlineKeyboardButton(
            text="🔙 Back",
            callback_data=create_callback(CallbackAreas.PRIMARY_IP, CallbackTasks.LIST, "", 0, 0, client_id),
        )
    )

    await callback.message.edit_text(f"🌍 Select location for {ip_type.upper()}:", reply_markup=builder.as_markup())
    await callback.answer()


@router.callback_query(F.data.startswith(f"{CallbackAreas.PRIMARY_IP}:{CallbackTasks.CREATE}:{CallbackSteps.LOCATION}"))
async def primary_ip_create_location(callback: CallbackQuery, state: FSMContext):
    cb = parse_callback(callback.data)
    datacenter_id = cb.target_id
    ip_type, client_id = cb.extra.split(":")

    async with db.session() as session:
        client_repo = ClientRepository(session)
        client = await client_repo.get_by_id(int(client_id))
        token = decrypt_token(client.api_token_encrypted)
        hetzner_client = await create_client(token)

        try:
            ip = await hetzner_client.create_primary_ip(ip_type, str(datacenter_id))
            await close_client(hetzner_client)

            audit_repo = AuditLogRepository(session)
            await audit_repo.log(
                action="primary_ip_create",
                success=True,
                client_id=int(client_id),
                resource_type="primary_ip",
                resource_id=ip.id,
                details={"type": ip_type, "datacenter": datacenter_id},
            )

            await callback.message.edit_text("🎉✅ Primary IP created successfully.")
        except Exception as e:
            await close_client(hetzner_client)
            await callback.message.edit_text(f"⚠️❌ Primary IP creation failed: {e!s}")

    await state.clear()
    await callback.answer()
    await show_primary_ip_list(callback, int(client_id))


@router.callback_query(F.data.startswith(f"{CallbackAreas.PRIMARY_IP}:{CallbackTasks.ACTION}:unassign"))
async def primary_ip_unassign(callback: CallbackQuery):
    cb = parse_callback(callback.data)
    ip_id = cb.target_id
    client_id = int(cb.extra) if cb.extra else 0

    async with db.session() as session:
        client_repo = ClientRepository(session)
        client = await client_repo.get_by_id(client_id)
        token = decrypt_token(client.api_token_encrypted)
        hetzner_client = await create_client(token)

        try:
            await hetzner_client.unassign_primary_ip_from_server(ip_id)
            await close_client(hetzner_client)

            audit_repo = AuditLogRepository(session)
            await audit_repo.log(
                action="primary_ip_unassign",
                success=True,
                client_id=client_id,
                resource_type="primary_ip",
                resource_id=ip_id,
            )

            await callback.message.edit_text("🎉✅ IP unassigned successfully.")
        except Exception as e:
            await close_client(hetzner_client)
            await callback.message.edit_text(f"⚠️❌ Unassign failed: {e!s}")

    await callback.answer()
    await show_primary_ip_info(callback, client_id, ip_id)


async def show_primary_ip_info(callback: CallbackQuery, client_id: int, ip_id: int):
    async with db.session() as session:
        client_repo = ClientRepository(session)
        client = await client_repo.get_by_id(client_id)
        if not client:
            await callback.answer("🔍❌ Not found [client].", show_alert=True)
            return

        token = decrypt_token(client.api_token_encrypted)
        hetzner_client = await create_client(token)
        ip = await hetzner_client.get_primary_ip(ip_id)
        await close_client(hetzner_client)

    is_assigned = ip.assignee_id is not None

    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="✏️ Change Remark",
            callback_data=create_callback(
                CallbackAreas.PRIMARY_IP, CallbackTasks.EDIT, CallbackSteps.REMARK, 0, 0, ip_id, str(client_id)
            ),
        ),
    )
    if is_assigned:
        builder.row(
            InlineKeyboardButton(
                text="❌ Unassign IP",
                callback_data=create_callback(
                    CallbackAreas.PRIMARY_IP, CallbackTasks.ACTION, "unassign", 0, 0, ip_id, str(client_id)
                ),
            ),
        )
    else:
        builder.row(
            InlineKeyboardButton(
                text="🔗 Assign IP",
                callback_data=create_callback(
                    CallbackAreas.PRIMARY_IP, CallbackTasks.ACTION, "assign", 0, 0, ip_id, str(client_id)
                ),
            ),
        )
    builder.row(
        InlineKeyboardButton(
            text="🗑 Delete IP",
            callback_data=create_callback(
                CallbackAreas.PRIMARY_IP, CallbackTasks.DELETE, CallbackSteps.CONFIRMATION, 0, 0, ip_id, str(client_id)
            ),
        ),
    )
    builder.row(
        InlineKeyboardButton(
            text="🔙 Back",
            callback_data=create_callback(CallbackAreas.PRIMARY_IP, CallbackTasks.LIST, "", 0, 0, client_id),
        ),
    )

    text = format_primary_ip_info(ip)
    await callback.message.edit_text(text, reply_markup=builder.as_markup())


@router.callback_query(F.data.startswith(f"{CallbackAreas.PRIMARY_IP}:{CallbackTasks.ACTION}:assign"))
async def primary_ip_assign(callback: CallbackQuery, state: FSMContext):
    cb = parse_callback(callback.data)
    ip_id = cb.target_id
    client_id = int(cb.extra) if cb.extra else 0

    await state.set_state(PrimaryIPCreateStates.waiting_location)
    await state.update_data(ip_id=ip_id, client_id=client_id, action="assign")

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
                CallbackAreas.PRIMARY_IP, CallbackTasks.ACTION, "assign_select", 0, 0, server.id, f"{ip_id}:{client_id}"
            ),
        )
    builder.adjust(1)
    builder.row(
        InlineKeyboardButton(
            text="🔙 Back",
            callback_data=create_callback(
                CallbackAreas.PRIMARY_IP, CallbackTasks.INFO, "", 0, 0, ip_id, str(client_id)
            ),
        )
    )

    await callback.message.edit_text("🖥 Select server to assign IP:", reply_markup=builder.as_markup())
    await callback.answer()


@router.callback_query(F.data.startswith(f"{CallbackAreas.PRIMARY_IP}:{CallbackTasks.ACTION}:assign_select"))
async def primary_ip_assign_select(callback: CallbackQuery, state: FSMContext):
    cb = parse_callback(callback.data)
    server_id = cb.target_id
    ip_id, client_id = map(int, cb.extra.split(":"))

    async with db.session() as session:
        client_repo = ClientRepository(session)
        client = await client_repo.get_by_id(client_id)
        token = decrypt_token(client.api_token_encrypted)
        hetzner_client = await create_client(token)

        try:
            await hetzner_client.assign_primary_ip_to_server(ip_id, server_id)
            await close_client(hetzner_client)

            audit_repo = AuditLogRepository(session)
            await audit_repo.log(
                action="primary_ip_assign",
                success=True,
                client_id=client_id,
                resource_type="primary_ip",
                resource_id=ip_id,
                details={"server_id": server_id},
            )

            await callback.message.edit_text("🎉✅ IP assigned successfully.")
        except Exception as e:
            await close_client(hetzner_client)
            await callback.message.edit_text(f"⚠️❌ Assign failed: {e!s}")

    await state.clear()
    await callback.answer()
    await show_primary_ip_info(callback, client_id, ip_id)


@router.callback_query(
    F.data.startswith(f"{CallbackAreas.PRIMARY_IP}:{CallbackTasks.DELETE}:{CallbackSteps.CONFIRMATION}")
)
async def primary_ip_delete_confirm(callback: CallbackQuery):
    cb = parse_callback(callback.data)
    ip_id = cb.target_id
    client_id = int(cb.extra) if cb.extra else 0

    if cb.approve == 1:
        async with db.session() as session:
            client_repo = ClientRepository(session)
            client = await client_repo.get_by_id(client_id)
            token = decrypt_token(client.api_token_encrypted)
            hetzner_client = await create_client(token)

            try:
                await hetzner_client.delete_primary_ip(ip_id)
                await close_client(hetzner_client)

                audit_repo = AuditLogRepository(session)
                await audit_repo.log(
                    action="primary_ip_delete",
                    success=True,
                    client_id=client_id,
                    resource_type="primary_ip",
                    resource_id=ip_id,
                )

                await callback.message.edit_text("🎉✅ Primary IP deleted successfully.")
            except Exception as e:
                await close_client(hetzner_client)
                await callback.message.edit_text(f"⚠️❌ Deletion failed: {e!s}")
    else:
        await callback.message.edit_text("🚫❌ Action cancelled. ↩️ Go back to the previous menu.")

    await callback.answer()
    await show_primary_ip_list(callback, client_id)


# Floating IPs
@router.callback_query(F.data.startswith(f"{CallbackAreas.FLOATING_IP}:{CallbackTasks.LIST}"))
async def floating_ip_list(callback: CallbackQuery):
    cb = parse_callback(callback.data)
    client_id = cb.target_id
    await show_floating_ip_list(callback, client_id)


async def show_floating_ip_list(callback: CallbackQuery, client_id: int):
    async with db.session() as session:
        client_repo = ClientRepository(session)
        client = await client_repo.get_by_id(client_id)
        if not client:
            await callback.answer("🔍❌ Not found [client].", show_alert=True)
            return

        token = decrypt_token(client.api_token_encrypted)
        hetzner_client = await create_client(token)
        ips = await hetzner_client.list_floating_ips()
        await close_client(hetzner_client)

    builder = InlineKeyboardBuilder()
    for ip in ips:
        builder.button(
            text=f"{ip.description or 'No Name'} [{ip.ip}]",
            callback_data=create_callback(
                CallbackAreas.FLOATING_IP, CallbackTasks.INFO, "", 0, 0, ip.id, str(client_id)
            ),
        )
    builder.adjust(1)

    builder.row(
        InlineKeyboardButton(
            text="➕ Create IPv4",
            callback_data=create_callback(
                CallbackAreas.FLOATING_IP, CallbackTasks.CREATE, CallbackSteps.TYPE, 0, 0, client_id, "ipv4"
            ),
        ),
        InlineKeyboardButton(
            text="➕ Create IPv6",
            callback_data=create_callback(
                CallbackAreas.FLOATING_IP, CallbackTasks.CREATE, CallbackSteps.TYPE, 0, 0, client_id, "ipv6"
            ),
        ),
    )
    builder.row(
        InlineKeyboardButton(text="🔙 Back", callback_data=create_callback(CallbackAreas.CLIENT, CallbackTasks.LIST))
    )

    text = "🔗 Floating IPs Menu\n👇 Select an action from the menu below."
    await callback.message.edit_text(text, reply_markup=builder.as_markup())
    await callback.answer()


@router.callback_query(F.data.startswith(f"{CallbackAreas.FLOATING_IP}:{CallbackTasks.INFO}"))
async def floating_ip_info(callback: CallbackQuery):
    cb = parse_callback(callback.data)
    ip_id = cb.target_id
    client_id = int(cb.extra) if cb.extra else 0

    async with db.session() as session:
        client_repo = ClientRepository(session)
        client = await client_repo.get_by_id(client_id)
        if not client:
            await callback.answer("🔍❌ Not found [client].", show_alert=True)
            return

        token = decrypt_token(client.api_token_encrypted)
        hetzner_client = await create_client(token)
        ip = await hetzner_client.get_floating_ip(ip_id)
        await close_client(hetzner_client)

    is_assigned = ip.server is not None

    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="✏️ Change Remark",
            callback_data=create_callback(
                CallbackAreas.FLOATING_IP, CallbackTasks.EDIT, CallbackSteps.REMARK, 0, 0, ip_id, str(client_id)
            ),
        ),
    )
    if is_assigned:
        builder.row(
            InlineKeyboardButton(
                text="❌ Unassign from Server",
                callback_data=create_callback(
                    CallbackAreas.FLOATING_IP, CallbackTasks.ACTION, "unassign", 0, 0, ip_id, str(client_id)
                ),
            ),
        )
    else:
        builder.row(
            InlineKeyboardButton(
                text="🔗 Assign to Server",
                callback_data=create_callback(
                    CallbackAreas.FLOATING_IP, CallbackTasks.ACTION, "assign", 0, 0, ip_id, str(client_id)
                ),
            ),
        )
    builder.row(
        InlineKeyboardButton(
            text="🌍 Change DNS",
            callback_data=create_callback(
                CallbackAreas.FLOATING_IP, CallbackTasks.ACTION, "change_dns", 0, 0, ip_id, str(client_id)
            ),
        ),
        InlineKeyboardButton(
            text="🗑 Delete Floating IP",
            callback_data=create_callback(
                CallbackAreas.FLOATING_IP, CallbackTasks.DELETE, CallbackSteps.CONFIRMATION, 0, 0, ip_id, str(client_id)
            ),
        ),
    )
    builder.row(
        InlineKeyboardButton(
            text="🔙 Back",
            callback_data=create_callback(CallbackAreas.FLOATING_IP, CallbackTasks.LIST, "", 0, 0, client_id),
        ),
    )

    text = format_floating_ip_info(ip)
    await callback.message.edit_text(text, reply_markup=builder.as_markup())
    await callback.answer()


@router.callback_query(F.data.startswith(f"{CallbackAreas.FLOATING_IP}:{CallbackTasks.CREATE}:{CallbackSteps.TYPE}"))
async def floating_ip_create_type(callback: CallbackQuery, state: FSMContext):
    cb = parse_callback(callback.data)
    ip_type = cb.extra
    client_id = cb.target_id

    await state.set_state(FloatingIPCreateStates.waiting_location)
    await state.update_data(ip_type=ip_type, client_id=client_id)

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
                CallbackAreas.FLOATING_IP,
                CallbackTasks.CREATE,
                CallbackSteps.LOCATION,
                0,
                0,
                dc.id,
                f"{ip_type}:{client_id}",
            ),
        )
    builder.adjust(1)
    builder.row(
        InlineKeyboardButton(
            text="🔙 Back",
            callback_data=create_callback(CallbackAreas.FLOATING_IP, CallbackTasks.LIST, "", 0, 0, client_id),
        )
    )

    await callback.message.edit_text(f"🌍 Select location for {ip_type.upper()}:", reply_markup=builder.as_markup())
    await callback.answer()


@router.callback_query(
    F.data.startswith(f"{CallbackAreas.FLOATING_IP}:{CallbackTasks.CREATE}:{CallbackSteps.LOCATION}")
)
async def floating_ip_create_location(callback: CallbackQuery, state: FSMContext):
    cb = parse_callback(callback.data)
    datacenter_id = cb.target_id
    ip_type, client_id = cb.extra.split(":")

    await state.set_state(FloatingIPCreateStates.waiting_server)
    await state.update_data(datacenter_id=datacenter_id, ip_type=ip_type, client_id=int(client_id))

    async with db.session() as session:
        client_repo = ClientRepository(session)
        client = await client_repo.get_by_id(int(client_id))
        token = decrypt_token(client.api_token_encrypted)
        hetzner_client = await create_client(token)
        servers = await hetzner_client.list_servers()
        await close_client(hetzner_client)

    builder = InlineKeyboardBuilder()
    builder.button(
        text="Skip (create without assignment)",
        callback_data=create_callback(
            CallbackAreas.FLOATING_IP,
            CallbackTasks.CREATE,
            CallbackSteps.SERVER,
            0,
            0,
            0,
            f"{ip_type}:{datacenter_id}:{client_id}",
        ),
    )
    for server in servers:
        builder.button(
            text=f"{server.name} [{server.status}]",
            callback_data=create_callback(
                CallbackAreas.FLOATING_IP,
                CallbackTasks.CREATE,
                CallbackSteps.SERVER,
                0,
                0,
                server.id,
                f"{ip_type}:{datacenter_id}:{client_id}",
            ),
        )
    builder.adjust(1)
    builder.row(
        InlineKeyboardButton(
            text="🔙 Back",
            callback_data=create_callback(CallbackAreas.FLOATING_IP, CallbackTasks.LIST, "", 0, 0, int(client_id)),
        )
    )

    await callback.message.edit_text("🖥 Select server to assign (optional):", reply_markup=builder.as_markup())
    await callback.answer()


@router.callback_query(F.data.startswith(f"{CallbackAreas.FLOATING_IP}:{CallbackTasks.CREATE}:{CallbackSteps.SERVER}"))
async def floating_ip_create_server(callback: CallbackQuery, state: FSMContext):
    cb = parse_callback(callback.data)
    server_id = cb.target_id
    ip_type, datacenter_id, client_id = cb.extra.split(":")

    async with db.session() as session:
        client_repo = ClientRepository(session)
        client = await client_repo.get_by_id(int(client_id))
        token = decrypt_token(client.api_token_encrypted)
        hetzner_client = await create_client(token)

        try:
            server = server_id if server_id > 0 else None
            ip = await hetzner_client.create_floating_ip(ip_type, str(datacenter_id), server)
            await close_client(hetzner_client)

            audit_repo = AuditLogRepository(session)
            await audit_repo.log(
                action="floating_ip_create",
                success=True,
                client_id=int(client_id),
                resource_type="floating_ip",
                resource_id=ip.id,
                details={"type": ip_type, "location": datacenter_id, "server": server},
            )

            await callback.message.edit_text("🎉✅ Floating IP created successfully.")
        except Exception as e:
            await close_client(hetzner_client)
            await callback.message.edit_text(f"⚠️❌ Floating IP creation failed: {e!s}")

    await state.clear()
    await callback.answer()
    await show_floating_ip_list(callback, int(client_id))


@router.callback_query(F.data.startswith(f"{CallbackAreas.FLOATING_IP}:{CallbackTasks.ACTION}:assign"))
async def floating_ip_assign(callback: CallbackQuery):
    cb = parse_callback(callback.data)
    ip_id = cb.target_id
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
                CallbackAreas.FLOATING_IP,
                CallbackTasks.ACTION,
                "assign_select",
                0,
                0,
                server.id,
                f"{ip_id}:{client_id}",
            ),
        )
    builder.adjust(1)
    builder.row(
        InlineKeyboardButton(
            text="🔙 Back",
            callback_data=create_callback(
                CallbackAreas.FLOATING_IP, CallbackTasks.INFO, "", 0, 0, ip_id, str(client_id)
            ),
        )
    )

    await callback.message.edit_text("🖥 Select server to assign:", reply_markup=builder.as_markup())
    await callback.answer()


@router.callback_query(F.data.startswith(f"{CallbackAreas.FLOATING_IP}:{CallbackTasks.ACTION}:assign_select"))
async def floating_ip_assign_select(callback: CallbackQuery):
    cb = parse_callback(callback.data)
    server_id = cb.target_id
    ip_id, client_id = map(int, cb.extra.split(":"))

    async with db.session() as session:
        client_repo = ClientRepository(session)
        client = await client_repo.get_by_id(client_id)
        token = decrypt_token(client.api_token_encrypted)
        hetzner_client = await create_client(token)

        try:
            await hetzner_client.assign_floating_ip(ip_id, server_id)
            await close_client(hetzner_client)

            audit_repo = AuditLogRepository(session)
            await audit_repo.log(
                action="floating_ip_assign",
                success=True,
                client_id=client_id,
                resource_type="floating_ip",
                resource_id=ip_id,
                details={"server_id": server_id},
            )

            await callback.message.edit_text("🎉✅ Floating IP assigned successfully.")
        except Exception as e:
            await close_client(hetzner_client)
            await callback.message.edit_text(f"⚠️❌ Assign failed: {e!s}")

    await callback.answer()
    await show_floating_ip_info(callback, client_id, ip_id)


async def show_floating_ip_info(callback: CallbackQuery, client_id: int, ip_id: int):
    async with db.session() as session:
        client_repo = ClientRepository(session)
        client = await client_repo.get_by_id(client_id)
        if not client:
            await callback.answer("🔍❌ Not found [client].", show_alert=True)
            return

        token = decrypt_token(client.api_token_encrypted)
        hetzner_client = await create_client(token)
        ip = await hetzner_client.get_floating_ip(ip_id)
        await close_client(hetzner_client)

    is_assigned = ip.server is not None

    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="✏️ Change Remark",
            callback_data=create_callback(
                CallbackAreas.FLOATING_IP, CallbackTasks.EDIT, CallbackSteps.REMARK, 0, 0, ip_id, str(client_id)
            ),
        ),
    )
    if is_assigned:
        builder.row(
            InlineKeyboardButton(
                text="❌ Unassign from Server",
                callback_data=create_callback(
                    CallbackAreas.FLOATING_IP, CallbackTasks.ACTION, "unassign", 0, 0, ip_id, str(client_id)
                ),
            ),
        )
    else:
        builder.row(
            InlineKeyboardButton(
                text="🔗 Assign to Server",
                callback_data=create_callback(
                    CallbackAreas.FLOATING_IP, CallbackTasks.ACTION, "assign", 0, 0, ip_id, str(client_id)
                ),
            ),
        )
    builder.row(
        InlineKeyboardButton(
            text="🌍 Change DNS",
            callback_data=create_callback(
                CallbackAreas.FLOATING_IP, CallbackTasks.ACTION, "change_dns", 0, 0, ip_id, str(client_id)
            ),
        ),
        InlineKeyboardButton(
            text="🗑 Delete Floating IP",
            callback_data=create_callback(
                CallbackAreas.FLOATING_IP, CallbackTasks.DELETE, CallbackSteps.CONFIRMATION, 0, 0, ip_id, str(client_id)
            ),
        ),
    )
    builder.row(
        InlineKeyboardButton(
            text="🔙 Back",
            callback_data=create_callback(CallbackAreas.FLOATING_IP, CallbackTasks.LIST, "", 0, 0, client_id),
        ),
    )

    text = format_floating_ip_info(ip)
    await callback.message.edit_text(text, reply_markup=builder.as_markup())


@router.callback_query(F.data.startswith(f"{CallbackAreas.FLOATING_IP}:{CallbackTasks.ACTION}:unassign"))
async def floating_ip_unassign(callback: CallbackQuery):
    cb = parse_callback(callback.data)
    ip_id = cb.target_id
    client_id = int(cb.extra) if cb.extra else 0

    async with db.session() as session:
        client_repo = ClientRepository(session)
        client = await client_repo.get_by_id(client_id)
        token = decrypt_token(client.api_token_encrypted)
        hetzner_client = await create_client(token)

        try:
            await hetzner_client.unassign_floating_ip(ip_id)
            await close_client(hetzner_client)

            audit_repo = AuditLogRepository(session)
            await audit_repo.log(
                action="floating_ip_unassign",
                success=True,
                client_id=client_id,
                resource_type="floating_ip",
                resource_id=ip_id,
            )

            await callback.message.edit_text("🎉✅ Floating IP unassigned successfully.")
        except Exception as e:
            await close_client(hetzner_client)
            await callback.message.edit_text(f"⚠️❌ Unassign failed: {e!s}")

    await callback.answer()
    await show_floating_ip_info(callback, client_id, ip_id)


@router.callback_query(F.data.startswith(f"{CallbackAreas.FLOATING_IP}:{CallbackTasks.ACTION}:change_dns"))
async def floating_ip_change_dns(callback: CallbackQuery, state: FSMContext):
    cb = parse_callback(callback.data)
    ip_id = cb.target_id
    client_id = int(cb.extra) if cb.extra else 0

    await state.set_state(FloatingIPCreateStates.waiting_server)
    await state.update_data(ip_id=ip_id, client_id=client_id, action="dns")

    await callback.message.edit_text("🌍 Enter DNS entry (format: ip dns_ptr):")
    await callback.answer()


@router.message(FloatingIPCreateStates.waiting_server)
async def floating_ip_dns_received(message: Message, state: FSMContext):
    data = await state.get_data()
    if data.get("action") != "dns":
        return

    parts = message.text.strip().split()
    if len(parts) != 2:
        await message.answer("⚠️❌ Invalid format. Use: ip dns_ptr")
        return

    ip, dns_ptr = parts

    async with db.session() as session:
        client_repo = ClientRepository(session)
        client = await client_repo.get_by_id(data["client_id"])
        token = decrypt_token(client.api_token_encrypted)
        hetzner_client = await create_client(token)

        try:
            await hetzner_client.change_floating_ip_dns(data["ip_id"], ip, dns_ptr)
            await close_client(hetzner_client)

            audit_repo = AuditLogRepository(session)
            await audit_repo.log(
                action="floating_ip_dns_change",
                success=True,
                client_id=data["client_id"],
                resource_type="floating_ip",
                resource_id=data["ip_id"],
                details={"ip": ip, "dns_ptr": dns_ptr},
            )

            await message.answer("🎉✅ DNS updated successfully.")
        except Exception as e:
            await close_client(hetzner_client)
            await message.answer(f"⚠️❌ DNS change failed: {e!s}")

    await state.clear()


@router.callback_query(
    F.data.startswith(f"{CallbackAreas.FLOATING_IP}:{CallbackTasks.DELETE}:{CallbackSteps.CONFIRMATION}")
)
async def floating_ip_delete_confirm(callback: CallbackQuery):
    cb = parse_callback(callback.data)
    ip_id = cb.target_id
    client_id = int(cb.extra) if cb.extra else 0

    if cb.approve == 1:
        async with db.session() as session:
            client_repo = ClientRepository(session)
            client = await client_repo.get_by_id(client_id)
            token = decrypt_token(client.api_token_encrypted)
            hetzner_client = await create_client(token)

            try:
                await hetzner_client.delete_floating_ip(ip_id)
                await close_client(hetzner_client)

                audit_repo = AuditLogRepository(session)
                await audit_repo.log(
                    action="floating_ip_delete",
                    success=True,
                    client_id=client_id,
                    resource_type="floating_ip",
                    resource_id=ip_id,
                )

                await callback.message.edit_text("🎉✅ Floating IP deleted successfully.")
            except Exception as e:
                await close_client(hetzner_client)
                await callback.message.edit_text(f"⚠️❌ Deletion failed: {e!s}")
    else:
        await callback.message.edit_text("🚫❌ Action cancelled. ↩️ Go back to the previous menu.")

    await callback.answer()
    await show_floating_ip_list(callback, client_id)
