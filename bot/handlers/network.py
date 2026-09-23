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
from bot.states import NetworkAddRouteStates, NetworkAddSubnetStates, NetworkCreateStates
from bot.utils.callbacks import (
    CallbackAreas,
    CallbackSteps,
    CallbackTasks,
    create_callback,
    parse_callback,
)
from bot.utils.formatters import format_network_info
from bot.utils.validators import validate_cidr, validate_remark

router = Router()


@router.callback_query(F.data.startswith(f"{CallbackAreas.NETWORK}:{CallbackTasks.LIST}"))
async def network_list(callback: CallbackQuery):
    cb = parse_callback(callback.data)
    client_id = cb.target_id
    await show_network_list(callback, client_id)


async def show_network_list(callback: CallbackQuery, client_id: int):
    async with db.session() as session:
        client_repo = ClientRepository(session)
        client = await client_repo.get_by_id(client_id)
        if not client:
            await callback.answer("🔍❌ Not found [client].", show_alert=True)
            return

        token = decrypt_token(client.api_token_encrypted)
        hetzner_client = await create_client(token)
        networks = await hetzner_client.list_networks()
        await close_client(hetzner_client)

    builder = InlineKeyboardBuilder()
    for net in networks:
        builder.button(
            text=net.name,
            callback_data=create_callback(CallbackAreas.NETWORK, CallbackTasks.INFO, "", 0, 0, net.id, str(client_id)),
        )
    builder.adjust(1)

    builder.row(
        InlineKeyboardButton(
            text="➕ Create Network",
            callback_data=create_callback(
                CallbackAreas.NETWORK, CallbackTasks.CREATE, CallbackSteps.REMARK, 0, 0, client_id
            ),
        ),
        InlineKeyboardButton(text="🔙 Back", callback_data=create_callback(CallbackAreas.CLIENT, CallbackTasks.LIST)),
    )

    text = "🕸 Networks Menu\n👇 Select an action from the menu below."
    await callback.message.edit_text(text, reply_markup=builder.as_markup())
    await callback.answer()


@router.callback_query(F.data.startswith(f"{CallbackAreas.NETWORK}:{CallbackTasks.INFO}"))
async def network_info(callback: CallbackQuery):
    cb = parse_callback(callback.data)
    network_id = cb.target_id
    client_id = int(cb.extra) if cb.extra else 0

    async with db.session() as session:
        client_repo = ClientRepository(session)
        client = await client_repo.get_by_id(client_id)
        if not client:
            await callback.answer("🔍❌ Not found [client].", show_alert=True)
            return

        token = decrypt_token(client.api_token_encrypted)
        hetzner_client = await create_client(token)
        network = await hetzner_client.get_network(network_id)
        await close_client(hetzner_client)

    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="✏️ Change Remark",
            callback_data=create_callback(
                CallbackAreas.NETWORK, CallbackTasks.EDIT, CallbackSteps.REMARK, 0, 0, network_id, str(client_id)
            ),
        ),
    )
    builder.row(
        InlineKeyboardButton(
            text="➕ Add Subnet",
            callback_data=create_callback(
                CallbackAreas.NETWORK, CallbackTasks.ACTION, "add_subnet", 0, 0, network_id, str(client_id)
            ),
        ),
        InlineKeyboardButton(
            text="❌ Delete Subnet",
            callback_data=create_callback(
                CallbackAreas.NETWORK, CallbackTasks.ACTION, "delete_subnet", 0, 0, network_id, str(client_id)
            ),
        ),
    )
    builder.row(
        InlineKeyboardButton(
            text="➕ Add Route",
            callback_data=create_callback(
                CallbackAreas.NETWORK, CallbackTasks.ACTION, "add_route", 0, 0, network_id, str(client_id)
            ),
        ),
        InlineKeyboardButton(
            text="❌ Delete Route",
            callback_data=create_callback(
                CallbackAreas.NETWORK, CallbackTasks.ACTION, "delete_route", 0, 0, network_id, str(client_id)
            ),
        ),
    )
    builder.row(
        InlineKeyboardButton(
            text="🗑 Delete Network",
            callback_data=create_callback(
                CallbackAreas.NETWORK,
                CallbackTasks.DELETE,
                CallbackSteps.CONFIRMATION,
                0,
                0,
                network_id,
                str(client_id),
            ),
        ),
    )
    builder.row(
        InlineKeyboardButton(
            text="🔙 Back",
            callback_data=create_callback(CallbackAreas.NETWORK, CallbackTasks.LIST, "", 0, 0, client_id),
        ),
    )

    text = format_network_info(network)
    await callback.message.edit_text(text, reply_markup=builder.as_markup())
    await callback.answer()


@router.callback_query(F.data.startswith(f"{CallbackAreas.NETWORK}:{CallbackTasks.CREATE}:{CallbackSteps.REMARK}"))
async def network_create_remark(callback: CallbackQuery, state: FSMContext):
    cb = parse_callback(callback.data)
    await state.set_state(NetworkCreateStates.waiting_remark)
    await state.update_data(client_id=cb.target_id)
    await callback.message.edit_text("✏️ Enter a remark for the network:")
    await callback.answer()


@router.message(NetworkCreateStates.waiting_remark)
async def network_create_remark_received(message: Message, state: FSMContext):
    valid, error = validate_remark(message.text)
    if not valid:
        await message.answer(
            "⚠️❌ Invalid remark format. 🔍 Please enter a valid remark without special characters and space."
        )
        return

    await state.update_data(remark=message.text)
    await state.set_state(NetworkCreateStates.waiting_ip_range)
    await message.answer("🔗 Enter IP range (e.g., 10.0.0.0/16):")


@router.message(NetworkCreateStates.waiting_ip_range)
async def network_create_ip_range_received(message: Message, state: FSMContext):
    valid, error = validate_cidr(message.text)
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
            network = await hetzner_client.create_network(data["remark"], message.text)
            await close_client(hetzner_client)

            audit_repo = AuditLogRepository(session)
            await audit_repo.log(
                action="network_create",
                success=True,
                client_id=client_id,
                resource_type="network",
                resource_id=network.id,
                details={"name": data["remark"], "ip_range": message.text},
            )

            await message.answer("🎉✅ Network created successfully.")
        except Exception as e:
            await close_client(hetzner_client)
            await message.answer(f"⚠️❌ Network creation failed: {e!s}")

    await state.clear()


@router.callback_query(F.data.startswith(f"{CallbackAreas.NETWORK}:{CallbackTasks.ACTION}:add_subnet"))
async def network_add_subnet(callback: CallbackQuery, state: FSMContext):
    cb = parse_callback(callback.data)
    network_id = cb.target_id
    client_id = int(cb.extra) if cb.extra else 0

    await state.set_state(NetworkAddSubnetStates.waiting_ip_range)
    await state.update_data(network_id=network_id, client_id=client_id)
    await callback.message.edit_text("🔗 Enter subnet IP range (e.g., 10.0.1.0/24):")
    await callback.answer()


@router.message(NetworkAddSubnetStates.waiting_ip_range)
async def network_add_subnet_ip_range(message: Message, state: FSMContext):
    valid, error = validate_cidr(message.text)
    if not valid:
        await message.answer(f"⚠️❌ {error}")
        return

    await state.update_data(ip_range=message.text)
    await state.set_state(NetworkAddSubnetStates.waiting_type)

    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="cloud", callback_data="network:subnet_type:cloud"),
        InlineKeyboardButton(text="vswitch", callback_data="network:subnet_type:vswitch"),
    )
    await message.answer("🌐 Select subnet type:", reply_markup=builder.as_markup())


@router.callback_query(F.data.startswith("network:subnet_type:"))
async def network_add_subnet_type(callback: CallbackQuery, state: FSMContext):
    subnet_type = callback.data.split(":")[-1]
    data = await state.get_data()
    network_id = data["network_id"]
    client_id = data["client_id"]
    ip_range = data["ip_range"]

    async with db.session() as session:
        client_repo = ClientRepository(session)
        client = await client_repo.get_by_id(client_id)
        token = decrypt_token(client.api_token_encrypted)
        hetzner_client = await create_client(token)

        try:
            await hetzner_client.add_subnet(network_id, ip_range, "eu-central", subnet_type)
            await close_client(hetzner_client)

            audit_repo = AuditLogRepository(session)
            await audit_repo.log(
                action="network_add_subnet",
                success=True,
                client_id=client_id,
                resource_type="network",
                resource_id=network_id,
                details={"ip_range": ip_range, "type": subnet_type},
            )

            await callback.message.edit_text("🎉✅ Subnet added successfully.")
        except Exception as e:
            await close_client(hetzner_client)
            await callback.message.edit_text(f"⚠️❌ Add subnet failed: {e!s}")

    await state.clear()
    await callback.answer()
    await show_network_info(callback, client_id, network_id)


async def show_network_info(callback: CallbackQuery, client_id: int, network_id: int):
    async with db.session() as session:
        client_repo = ClientRepository(session)
        client = await client_repo.get_by_id(client_id)
        if not client:
            await callback.answer("🔍❌ Not found [client].", show_alert=True)
            return

        token = decrypt_token(client.api_token_encrypted)
        hetzner_client = await create_client(token)
        network = await hetzner_client.get_network(network_id)
        await close_client(hetzner_client)

    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="✏️ Change Remark",
            callback_data=create_callback(
                CallbackAreas.NETWORK, CallbackTasks.EDIT, CallbackSteps.REMARK, 0, 0, network_id, str(client_id)
            ),
        ),
    )
    builder.row(
        InlineKeyboardButton(
            text="➕ Add Subnet",
            callback_data=create_callback(
                CallbackAreas.NETWORK, CallbackTasks.ACTION, "add_subnet", 0, 0, network_id, str(client_id)
            ),
        ),
        InlineKeyboardButton(
            text="❌ Delete Subnet",
            callback_data=create_callback(
                CallbackAreas.NETWORK, CallbackTasks.ACTION, "delete_subnet", 0, 0, network_id, str(client_id)
            ),
        ),
    )
    builder.row(
        InlineKeyboardButton(
            text="➕ Add Route",
            callback_data=create_callback(
                CallbackAreas.NETWORK, CallbackTasks.ACTION, "add_route", 0, 0, network_id, str(client_id)
            ),
        ),
        InlineKeyboardButton(
            text="❌ Delete Route",
            callback_data=create_callback(
                CallbackAreas.NETWORK, CallbackTasks.ACTION, "delete_route", 0, 0, network_id, str(client_id)
            ),
        ),
    )
    builder.row(
        InlineKeyboardButton(
            text="🗑 Delete Network",
            callback_data=create_callback(
                CallbackAreas.NETWORK,
                CallbackTasks.DELETE,
                CallbackSteps.CONFIRMATION,
                0,
                0,
                network_id,
                str(client_id),
            ),
        ),
    )
    builder.row(
        InlineKeyboardButton(
            text="🔙 Back",
            callback_data=create_callback(CallbackAreas.NETWORK, CallbackTasks.LIST, "", 0, 0, client_id),
        ),
    )

    text = format_network_info(network)
    await callback.message.edit_text(text, reply_markup=builder.as_markup())


@router.callback_query(F.data.startswith(f"{CallbackAreas.NETWORK}:{CallbackTasks.ACTION}:delete_subnet"))
async def network_delete_subnet(callback: CallbackQuery, state: FSMContext):
    cb = parse_callback(callback.data)
    network_id = cb.target_id
    client_id = int(cb.extra) if cb.extra else 0

    async with db.session() as session:
        client_repo = ClientRepository(session)
        client = await client_repo.get_by_id(client_id)
        token = decrypt_token(client.api_token_encrypted)
        hetzner_client = await create_client(token)
        network = await hetzner_client.get_network(network_id)
        await close_client(hetzner_client)

    builder = InlineKeyboardBuilder()
    for subnet in network.subnets:
        builder.button(
            text=subnet.get("ip_range", "N/A"),
            callback_data=create_callback(
                CallbackAreas.NETWORK,
                CallbackTasks.ACTION,
                "delete_subnet_select",
                0,
                0,
                0,
                f"{network_id}:{client_id}:{subnet.get('ip_range')}",
            ),
        )
    builder.adjust(1)
    builder.row(
        InlineKeyboardButton(
            text="🔙 Back",
            callback_data=create_callback(
                CallbackAreas.NETWORK, CallbackTasks.INFO, "", 0, 0, network_id, str(client_id)
            ),
        )
    )

    await callback.message.edit_text("❌ Select subnet to delete:", reply_markup=builder.as_markup())
    await callback.answer()


@router.callback_query(F.data.startswith(f"{CallbackAreas.NETWORK}:{CallbackTasks.ACTION}:delete_subnet_select"))
async def network_delete_subnet_select(callback: CallbackQuery):
    cb = parse_callback(callback.data)
    network_id, client_id, ip_range = cb.extra.split(":")

    async with db.session() as session:
        client_repo = ClientRepository(session)
        client = await client_repo.get_by_id(int(client_id))
        token = decrypt_token(client.api_token_encrypted)
        hetzner_client = await create_client(token)

        try:
            await hetzner_client.delete_subnet(int(network_id), ip_range)
            await close_client(hetzner_client)

            audit_repo = AuditLogRepository(session)
            await audit_repo.log(
                action="network_delete_subnet",
                success=True,
                client_id=int(client_id),
                resource_type="network",
                resource_id=int(network_id),
                details={"ip_range": ip_range},
            )

            await callback.message.edit_text("🎉✅ Subnet deleted successfully.")
        except Exception as e:
            await close_client(hetzner_client)
            await callback.message.edit_text(f"⚠️❌ Delete subnet failed: {e!s}")

    await callback.answer()
    await show_network_info(callback, int(client_id), int(network_id))


@router.callback_query(F.data.startswith(f"{CallbackAreas.NETWORK}:{CallbackTasks.ACTION}:add_route"))
async def network_add_route(callback: CallbackQuery, state: FSMContext):
    cb = parse_callback(callback.data)
    network_id = cb.target_id
    client_id = int(cb.extra) if cb.extra else 0

    await state.set_state(NetworkAddRouteStates.waiting_destination_gateway)
    await state.update_data(network_id=network_id, client_id=client_id)
    await callback.message.edit_text("🛤 Enter destination and gateway (e.g., 10.100.0.0/16 10.0.0.1):")
    await callback.answer()


@router.message(NetworkAddRouteStates.waiting_destination_gateway)
async def network_add_route_received(message: Message, state: FSMContext):
    parts = message.text.strip().split()
    if len(parts) != 2:
        await message.answer("⚠️❌ Invalid format. Use: destination gateway")
        return

    destination, gateway = parts

    data = await state.get_data()
    network_id = data["network_id"]
    client_id = data["client_id"]

    async with db.session() as session:
        client_repo = ClientRepository(session)
        client = await client_repo.get_by_id(client_id)
        token = decrypt_token(client.api_token_encrypted)
        hetzner_client = await create_client(token)

        try:
            await hetzner_client.add_route(network_id, destination, gateway)
            await close_client(hetzner_client)

            audit_repo = AuditLogRepository(session)
            await audit_repo.log(
                action="network_add_route",
                success=True,
                client_id=client_id,
                resource_type="network",
                resource_id=network_id,
                details={"destination": destination, "gateway": gateway},
            )

            await message.answer("🎉✅ Route added successfully.")
        except Exception as e:
            await close_client(hetzner_client)
            await message.answer(f"⚠️❌ Add route failed: {e!s}")

    await state.clear()


@router.callback_query(F.data.startswith(f"{CallbackAreas.NETWORK}:{CallbackTasks.ACTION}:delete_route"))
async def network_delete_route(callback: CallbackQuery, state: FSMContext):
    cb = parse_callback(callback.data)
    network_id = cb.target_id
    client_id = int(cb.extra) if cb.extra else 0

    async with db.session() as session:
        client_repo = ClientRepository(session)
        client = await client_repo.get_by_id(client_id)
        token = decrypt_token(client.api_token_encrypted)
        hetzner_client = await create_client(token)
        network = await hetzner_client.get_network(network_id)
        await close_client(hetzner_client)

    builder = InlineKeyboardBuilder()
    for route in network.routes:
        builder.button(
            text=f"{route.get('destination')} → {route.get('gateway')}",
            callback_data=create_callback(
                CallbackAreas.NETWORK,
                CallbackTasks.ACTION,
                "delete_route_select",
                0,
                0,
                0,
                f"{network_id}:{client_id}:{route.get('destination')}:{route.get('gateway')}",
            ),
        )
    builder.adjust(1)
    builder.row(
        InlineKeyboardButton(
            text="🔙 Back",
            callback_data=create_callback(
                CallbackAreas.NETWORK, CallbackTasks.INFO, "", 0, 0, network_id, str(client_id)
            ),
        )
    )

    await callback.message.edit_text("❌ Select route to delete:", reply_markup=builder.as_markup())
    await callback.answer()


@router.callback_query(F.data.startswith(f"{CallbackAreas.NETWORK}:{CallbackTasks.ACTION}:delete_route_select"))
async def network_delete_route_select(callback: CallbackQuery):
    cb = parse_callback(callback.data)
    network_id, client_id, destination, gateway = cb.extra.split(":")

    async with db.session() as session:
        client_repo = ClientRepository(session)
        client = await client_repo.get_by_id(int(client_id))
        token = decrypt_token(client.api_token_encrypted)
        hetzner_client = await create_client(token)

        try:
            await hetzner_client.delete_route(int(network_id), destination, gateway)
            await close_client(hetzner_client)

            audit_repo = AuditLogRepository(session)
            await audit_repo.log(
                action="network_delete_route",
                success=True,
                client_id=int(client_id),
                resource_type="network",
                resource_id=int(network_id),
                details={"destination": destination, "gateway": gateway},
            )

            await callback.message.edit_text("🎉✅ Route deleted successfully.")
        except Exception as e:
            await close_client(hetzner_client)
            await callback.message.edit_text(f"⚠️❌ Delete route failed: {e!s}")

    await callback.answer()
    await show_network_info(callback, int(client_id), int(network_id))


@router.callback_query(
    F.data.startswith(f"{CallbackAreas.NETWORK}:{CallbackTasks.DELETE}:{CallbackSteps.CONFIRMATION}")
)
async def network_delete_confirm(callback: CallbackQuery):
    cb = parse_callback(callback.data)
    network_id = cb.target_id
    client_id = int(cb.extra) if cb.extra else 0

    if cb.approve == 1:
        async with db.session() as session:
            client_repo = ClientRepository(session)
            client = await client_repo.get_by_id(client_id)
            token = decrypt_token(client.api_token_encrypted)
            hetzner_client = await create_client(token)

            try:
                await hetzner_client.delete_network(network_id)
                await close_client(hetzner_client)

                audit_repo = AuditLogRepository(session)
                await audit_repo.log(
                    action="network_delete",
                    success=True,
                    client_id=client_id,
                    resource_type="network",
                    resource_id=network_id,
                )

                await callback.message.edit_text("🎉✅ Network deleted successfully.")
            except Exception as e:
                await close_client(hetzner_client)
                await callback.message.edit_text(f"⚠️❌ Deletion failed: {e!s}")
    else:
        await callback.message.edit_text("🚫❌ Action cancelled. ↩️ Go back to the previous menu.")

    await callback.answer()
    await show_network_list(callback, client_id)


@router.callback_query(F.data.startswith(f"{CallbackAreas.NETWORK}:{CallbackTasks.EDIT}:{CallbackSteps.REMARK}"))
async def network_edit_remark(callback: CallbackQuery, state: FSMContext):
    cb = parse_callback(callback.data)
    await state.set_state(NetworkCreateStates.waiting_remark)
    await state.update_data(network_id=cb.target_id, client_id=int(cb.extra) if cb.extra else 0, editing=True)
    await callback.message.edit_text("✏️ Enter new remark for the network:")
    await callback.answer()


@router.message(NetworkCreateStates.waiting_remark)
async def network_edit_remark_received(message: Message, state: FSMContext):
    data = await state.get_data()
    if not data.get("editing"):
        return

    valid, error = validate_remark(message.text)
    if not valid:
        await message.answer(
            "⚠️❌ Invalid remark format. 🔍 Please enter a valid remark without special characters and space."
        )
        return

    network_id = data["network_id"]
    client_id = data["client_id"]

    async with db.session() as session:
        client_repo = ClientRepository(session)
        client = await client_repo.get_by_id(client_id)
        token = decrypt_token(client.api_token_encrypted)
        hetzner_client = await create_client(token)

        try:
            await hetzner_client.update_network(network_id, name=message.text)
            await close_client(hetzner_client)

            audit_repo = AuditLogRepository(session)
            await audit_repo.log(
                action="network_rename",
                success=True,
                client_id=client_id,
                resource_type="network",
                resource_id=network_id,
                details={"new_name": message.text},
            )

            await message.answer("🎉✅ Network remark updated successfully.")
        except Exception as e:
            await close_client(hetzner_client)
            await message.answer(f"⚠️❌ Failed to update remark: {e!s}")

    await state.clear()
