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
from bot.states import LoadBalancerCreateStates
from bot.utils.callbacks import (
    CallbackAreas,
    CallbackSteps,
    CallbackTasks,
    create_callback,
    parse_callback,
)
from bot.utils.formatters import format_load_balancer_info
from bot.utils.validators import validate_remark

router = Router()


@router.callback_query(F.data.startswith(f"{CallbackAreas.LOADBALANCER}:{CallbackTasks.LIST}"))
async def loadbalancer_list(callback: CallbackQuery):
    cb = parse_callback(callback.data)
    client_id = cb.target_id
    await show_loadbalancer_list(callback, client_id)


async def show_loadbalancer_list(callback: CallbackQuery, client_id: int):
    async with db.session() as session:
        client_repo = ClientRepository(session)
        client = await client_repo.get_by_id(client_id)
        if not client:
            await callback.answer("🔍❌ Not found [client].", show_alert=True)
            return

        token = decrypt_token(client.api_token_encrypted)
        hetzner_client = await create_client(token)
        lbs = await hetzner_client.list_load_balancers()
        await close_client(hetzner_client)

    builder = InlineKeyboardBuilder()
    for lb in lbs:
        builder.button(
            text=lb.name,
            callback_data=create_callback(
                CallbackAreas.LOADBALANCER, CallbackTasks.INFO, "", 0, 0, lb.id, str(client_id)
            ),
        )
    builder.adjust(1)

    builder.row(
        InlineKeyboardButton(
            text="➕ Create Load Balancer",
            callback_data=create_callback(
                CallbackAreas.LOADBALANCER, CallbackTasks.CREATE, CallbackSteps.REMARK, 0, 0, client_id
            ),
        ),
        InlineKeyboardButton(text="🔙 Back", callback_data=create_callback(CallbackAreas.CLIENT, CallbackTasks.LIST)),
    )

    text = "⚖️ Load Balancers Menu\n👇 Select an action from the menu below."
    await callback.message.edit_text(text, reply_markup=builder.as_markup())
    await callback.answer()


@router.callback_query(F.data.startswith(f"{CallbackAreas.LOADBALANCER}:{CallbackTasks.INFO}"))
async def loadbalancer_info(callback: CallbackQuery):
    cb = parse_callback(callback.data)
    lb_id = cb.target_id
    client_id = int(cb.extra) if cb.extra else 0

    async with db.session() as session:
        client_repo = ClientRepository(session)
        client = await client_repo.get_by_id(client_id)
        if not client:
            await callback.answer("🔍❌ Not found [client].", show_alert=True)
            return

        token = decrypt_token(client.api_token_encrypted)
        hetzner_client = await create_client(token)
        lb = await hetzner_client.get_load_balancer(lb_id)
        await close_client(hetzner_client)

    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="✏️ Change Remark",
            callback_data=create_callback(
                CallbackAreas.LOADBALANCER, CallbackTasks.EDIT, CallbackSteps.REMARK, 0, 0, lb_id, str(client_id)
            ),
        ),
    )
    builder.row(
        InlineKeyboardButton(
            text="🔗 Add Target",
            callback_data=create_callback(
                CallbackAreas.LOADBALANCER, CallbackTasks.ACTION, "add_target", 0, 0, lb_id, str(client_id)
            ),
        ),
        InlineKeyboardButton(
            text="❌ Remove Target",
            callback_data=create_callback(
                CallbackAreas.LOADBALANCER, CallbackTasks.ACTION, "remove_target", 0, 0, lb_id, str(client_id)
            ),
        ),
    )
    builder.row(
        InlineKeyboardButton(
            text="🗑 Delete Load Balancer",
            callback_data=create_callback(
                CallbackAreas.LOADBALANCER,
                CallbackTasks.DELETE,
                CallbackSteps.CONFIRMATION,
                0,
                0,
                lb_id,
                str(client_id),
            ),
        ),
    )
    builder.row(
        InlineKeyboardButton(
            text="🔙 Back",
            callback_data=create_callback(CallbackAreas.LOADBALANCER, CallbackTasks.LIST, "", 0, 0, client_id),
        ),
    )

    text = format_load_balancer_info(lb)
    await callback.message.edit_text(text, reply_markup=builder.as_markup())
    await callback.answer()


@router.callback_query(F.data.startswith(f"{CallbackAreas.LOADBALANCER}:{CallbackTasks.CREATE}:{CallbackSteps.REMARK}"))
async def loadbalancer_create_remark(callback: CallbackQuery, state: FSMContext):
    cb = parse_callback(callback.data)
    await state.set_state(LoadBalancerCreateStates.waiting_remark)
    await state.update_data(client_id=cb.target_id)
    await callback.message.edit_text("✏️ Enter a remark for the load balancer:")
    await callback.answer()


@router.message(LoadBalancerCreateStates.waiting_remark)
async def loadbalancer_create_remark_received(message: Message, state: FSMContext):
    valid, error = validate_remark(message.text)
    if not valid:
        await message.answer(
            "⚠️❌ Invalid remark format. 🔍 Please enter a valid remark without special characters and space."
        )
        return

    await state.update_data(remark=message.text)
    await state.set_state(LoadBalancerCreateStates.waiting_type)

    async with db.session() as session:
        client_repo = ClientRepository(session)
        client = await client_repo.get_by_id(data["client_id"])
        token = decrypt_token(client.api_token_encrypted)
        hetzner_client = await create_client(token)

        # Get LB types from server types
        server_types = await hetzner_client.list_server_types()
        lb_types = [st for st in server_types if st.name.startswith("lb")]
        await close_client(hetzner_client)

    builder = InlineKeyboardBuilder()
    for lb_type in lb_types:
        builder.button(
            text=f"{lb_type.name}",
            callback_data=create_callback(
                CallbackAreas.LOADBALANCER,
                CallbackTasks.CREATE,
                CallbackSteps.TYPE,
                0,
                0,
                0,
                f"{lb_type.name}:{data['client_id']}",
            ),
        )
    builder.adjust(1)
    builder.row(
        InlineKeyboardButton(
            text="🔙 Back",
            callback_data=create_callback(CallbackAreas.LOADBALANCER, CallbackTasks.LIST, "", 0, 0, data["client_id"]),
        )
    )

    await message.answer("🌍 Select load balancer type:", reply_markup=builder.as_markup())


@router.callback_query(F.data.startswith(f"{CallbackAreas.LOADBALANCER}:{CallbackTasks.CREATE}:{CallbackSteps.TYPE}"))
async def loadbalancer_create_type(callback: CallbackQuery, state: FSMContext):
    cb = parse_callback(callback.data)
    lb_type, client_id = cb.extra.split(":")

    await state.update_data(lb_type=lb_type)
    await state.set_state(LoadBalancerCreateStates.waiting_location)

    async with db.session() as session:
        client_repo = ClientRepository(session)
        client = await client_repo.get_by_id(int(client_id))
        token = decrypt_token(client.api_token_encrypted)
        hetzner_client = await create_client(token)
        datacenters = await hetzner_client.list_datacenters()
        await close_client(hetzner_client)

    builder = InlineKeyboardBuilder()
    for dc in datacenters:
        builder.button(
            text=f"{dc.name} [{dc.location}]",
            callback_data=create_callback(
                CallbackAreas.LOADBALANCER,
                CallbackTasks.CREATE,
                CallbackSteps.LOCATION,
                0,
                0,
                dc.id,
                f"{lb_type}:{client_id}",
            ),
        )
    builder.adjust(1)
    builder.row(
        InlineKeyboardButton(
            text="🔙 Back",
            callback_data=create_callback(CallbackAreas.LOADBALANCER, CallbackTasks.LIST, "", 0, 0, int(client_id)),
        )
    )

    await callback.message.edit_text("🌍 Select location:", reply_markup=builder.as_markup())
    await callback.answer()


@router.callback_query(
    F.data.startswith(f"{CallbackAreas.LOADBALANCER}:{CallbackTasks.CREATE}:{CallbackSteps.LOCATION}")
)
async def loadbalancer_create_location(callback: CallbackQuery, state: FSMContext):
    cb = parse_callback(callback.data)
    datacenter_id = cb.target_id
    lb_type, client_id = cb.extra.split(":")

    data = await state.get_data()

    async with db.session() as session:
        client_repo = ClientRepository(session)
        client = await client_repo.get_by_id(int(client_id))
        token = decrypt_token(client.api_token_encrypted)
        hetzner_client = await create_client(token)

        try:
            lb = await hetzner_client.create_load_balancer(
                name=data["remark"],
                load_balancer_type=lb_type,
                location=str(datacenter_id),
            )
            await close_client(hetzner_client)

            audit_repo = AuditLogRepository(session)
            await audit_repo.log(
                action="loadbalancer_create",
                success=True,
                client_id=int(client_id),
                resource_type="loadbalancer",
                resource_id=lb.id,
                details={"name": data["remark"], "type": lb_type, "location": datacenter_id},
            )

            await callback.message.edit_text("🎉✅ Load Balancer created successfully.")
        except Exception as e:
            await close_client(hetzner_client)
            await callback.message.edit_text(f"⚠️❌ Load Balancer creation failed: {e!s}")

    await state.clear()
    await callback.answer()
    await show_loadbalancer_list(callback, int(client_id))


@router.callback_query(F.data.startswith(f"{CallbackAreas.LOADBALANCER}:{CallbackTasks.ACTION}:add_target"))
async def loadbalancer_add_target(callback: CallbackQuery):
    cb = parse_callback(callback.data)
    lb_id = cb.target_id
    client_id = int(cb.extra) if cb.extra else 0

    async with db.session() as session:
        client_repo = ClientRepository(session)
        client = await client_repo.get_by_id(client_id)
        token = decrypt_token(client.api_token_encrypted)
        hetzner_client = await create_client(token)
        servers = await hetzner_client.list_servers()
        lb = await hetzner_client.get_load_balancer(lb_id)
        await close_client(hetzner_client)

    existing_targets = {t.get("server", {}).get("id") for t in lb.targets if t.get("server")}

    builder = InlineKeyboardBuilder()
    for server in servers:
        if server.id in existing_targets:
            continue
        builder.button(
            text=f"{server.name} [{server.status}]",
            callback_data=create_callback(
                CallbackAreas.LOADBALANCER,
                CallbackTasks.ACTION,
                "add_target_select",
                0,
                0,
                server.id,
                f"{lb_id}:{client_id}",
            ),
        )
    builder.adjust(1)
    builder.row(
        InlineKeyboardButton(
            text="🔙 Back",
            callback_data=create_callback(
                CallbackAreas.LOADBALANCER, CallbackTasks.INFO, "", 0, 0, lb_id, str(client_id)
            ),
        )
    )

    await callback.message.edit_text("🖥 Select server to add as target:", reply_markup=builder.as_markup())
    await callback.answer()


@router.callback_query(F.data.startswith(f"{CallbackAreas.LOADBALANCER}:{CallbackTasks.ACTION}:add_target_select"))
async def loadbalancer_add_target_select(callback: CallbackQuery):
    cb = parse_callback(callback.data)
    server_id = cb.target_id
    lb_id, client_id = map(int, cb.extra.split(":"))

    async with db.session() as session:
        client_repo = ClientRepository(session)
        client = await client_repo.get_by_id(client_id)
        token = decrypt_token(client.api_token_encrypted)
        hetzner_client = await create_client(token)

        try:
            await hetzner_client.add_load_balancer_target(lb_id, {"type": "server", "server": {"id": server_id}})
            await close_client(hetzner_client)

            audit_repo = AuditLogRepository(session)
            await audit_repo.log(
                action="loadbalancer_add_target",
                success=True,
                client_id=client_id,
                resource_type="loadbalancer",
                resource_id=lb_id,
                details={"server_id": server_id},
            )

            await callback.message.edit_text("🎉✅ Target added successfully.")
        except Exception as e:
            await close_client(hetzner_client)
            await callback.message.edit_text(f"⚠️❌ Add target failed: {e!s}")

    await callback.answer()
    await show_loadbalancer_info(callback, client_id, lb_id)


async def show_loadbalancer_info(callback: CallbackQuery, client_id: int, lb_id: int):
    async with db.session() as session:
        client_repo = ClientRepository(session)
        client = await client_repo.get_by_id(client_id)
        if not client:
            await callback.answer("🔍❌ Not found [client].", show_alert=True)
            return

        token = decrypt_token(client.api_token_encrypted)
        hetzner_client = await create_client(token)
        lb = await hetzner_client.get_load_balancer(lb_id)
        await close_client(hetzner_client)

    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="✏️ Change Remark",
            callback_data=create_callback(
                CallbackAreas.LOADBALANCER, CallbackTasks.EDIT, CallbackSteps.REMARK, 0, 0, lb_id, str(client_id)
            ),
        ),
    )
    builder.row(
        InlineKeyboardButton(
            text="🔗 Add Target",
            callback_data=create_callback(
                CallbackAreas.LOADBALANCER, CallbackTasks.ACTION, "add_target", 0, 0, lb_id, str(client_id)
            ),
        ),
        InlineKeyboardButton(
            text="❌ Remove Target",
            callback_data=create_callback(
                CallbackAreas.LOADBALANCER, CallbackTasks.ACTION, "remove_target", 0, 0, lb_id, str(client_id)
            ),
        ),
    )
    builder.row(
        InlineKeyboardButton(
            text="🗑 Delete Load Balancer",
            callback_data=create_callback(
                CallbackAreas.LOADBALANCER,
                CallbackTasks.DELETE,
                CallbackSteps.CONFIRMATION,
                0,
                0,
                lb_id,
                str(client_id),
            ),
        ),
    )
    builder.row(
        InlineKeyboardButton(
            text="🔙 Back",
            callback_data=create_callback(CallbackAreas.LOADBALANCER, CallbackTasks.LIST, "", 0, 0, client_id),
        ),
    )

    text = format_load_balancer_info(lb)
    await callback.message.edit_text(text, reply_markup=builder.as_markup())


@router.callback_query(F.data.startswith(f"{CallbackAreas.LOADBALANCER}:{CallbackTasks.ACTION}:remove_target"))
async def loadbalancer_remove_target(callback: CallbackQuery):
    cb = parse_callback(callback.data)
    lb_id = cb.target_id
    client_id = int(cb.extra) if cb.extra else 0

    async with db.session() as session:
        client_repo = ClientRepository(session)
        client = await client_repo.get_by_id(client_id)
        token = decrypt_token(client.api_token_encrypted)
        hetzner_client = await create_client(token)
        lb = await hetzner_client.get_load_balancer(lb_id)
        await close_client(hetzner_client)

    builder = InlineKeyboardBuilder()
    for target in lb.targets:
        if target.get("server"):
            builder.button(
                text=target["server"].get("name", "Unknown"),
                callback_data=create_callback(
                    CallbackAreas.LOADBALANCER,
                    CallbackTasks.ACTION,
                    "remove_target_select",
                    0,
                    0,
                    target["server"]["id"],
                    f"{lb_id}:{client_id}",
                ),
            )
    builder.adjust(1)
    builder.row(
        InlineKeyboardButton(
            text="🔙 Back",
            callback_data=create_callback(
                CallbackAreas.LOADBALANCER, CallbackTasks.INFO, "", 0, 0, lb_id, str(client_id)
            ),
        )
    )

    await callback.message.edit_text("❌ Select target to remove:", reply_markup=builder.as_markup())
    await callback.answer()


@router.callback_query(F.data.startswith(f"{CallbackAreas.LOADBALANCER}:{CallbackTasks.ACTION}:remove_target_select"))
async def loadbalancer_remove_target_select(callback: CallbackQuery):
    cb = parse_callback(callback.data)
    server_id = cb.target_id
    lb_id, client_id = map(int, cb.extra.split(":"))

    async with db.session() as session:
        client_repo = ClientRepository(session)
        client = await client_repo.get_by_id(client_id)
        token = decrypt_token(client.api_token_encrypted)
        hetzner_client = await create_client(token)

        try:
            await hetzner_client.remove_load_balancer_target(lb_id, {"type": "server", "server": {"id": server_id}})
            await close_client(hetzner_client)

            audit_repo = AuditLogRepository(session)
            await audit_repo.log(
                action="loadbalancer_remove_target",
                success=True,
                client_id=client_id,
                resource_type="loadbalancer",
                resource_id=lb_id,
                details={"server_id": server_id},
            )

            await callback.message.edit_text("🎉✅ Target removed successfully.")
        except Exception as e:
            await close_client(hetzner_client)
            await callback.message.edit_text(f"⚠️❌ Remove target failed: {e!s}")

    await callback.answer()
    await show_loadbalancer_info(callback, client_id, lb_id)


@router.callback_query(
    F.data.startswith(f"{CallbackAreas.LOADBALANCER}:{CallbackTasks.DELETE}:{CallbackSteps.CONFIRMATION}")
)
async def loadbalancer_delete_confirm(callback: CallbackQuery):
    cb = parse_callback(callback.data)
    lb_id = cb.target_id
    client_id = int(cb.extra) if cb.extra else 0

    if cb.approve == 1:
        async with db.session() as session:
            client_repo = ClientRepository(session)
            client = await client_repo.get_by_id(client_id)
            token = decrypt_token(client.api_token_encrypted)
            hetzner_client = await create_client(token)

            try:
                await hetzner_client.delete_load_balancer(lb_id)
                await close_client(hetzner_client)

                audit_repo = AuditLogRepository(session)
                await audit_repo.log(
                    action="loadbalancer_delete",
                    success=True,
                    client_id=client_id,
                    resource_type="loadbalancer",
                    resource_id=lb_id,
                )

                await callback.message.edit_text("🎉✅ Load Balancer deleted successfully.")
            except Exception as e:
                await close_client(hetzner_client)
                await callback.message.edit_text(f"⚠️❌ Deletion failed: {e!s}")
    else:
        await callback.message.edit_text("🚫❌ Action cancelled. ↩️ Go back to the previous menu.")

    await callback.answer()
    await show_loadbalancer_list(callback, client_id)


@router.callback_query(F.data.startswith(f"{CallbackAreas.LOADBALANCER}:{CallbackTasks.EDIT}:{CallbackSteps.REMARK}"))
async def loadbalancer_edit_remark(callback: CallbackQuery, state: FSMContext):
    cb = parse_callback(callback.data)
    await state.set_state(LoadBalancerCreateStates.waiting_remark)
    await state.update_data(lb_id=cb.target_id, client_id=int(cb.extra) if cb.extra else 0, editing=True)
    await callback.message.edit_text("✏️ Enter new remark for the load balancer:")
    await callback.answer()


@router.message(LoadBalancerCreateStates.waiting_remark)
async def loadbalancer_edit_remark_received(message: Message, state: FSMContext):
    data = await state.get_data()
    if not data.get("editing"):
        return

    valid, error = validate_remark(message.text)
    if not valid:
        await message.answer(
            "⚠️❌ Invalid remark format. 🔍 Please enter a valid remark without special characters and space."
        )
        return

    lb_id = data["lb_id"]
    client_id = data["client_id"]

    async with db.session() as session:
        client_repo = ClientRepository(session)
        client = await client_repo.get_by_id(client_id)
        token = decrypt_token(client.api_token_encrypted)
        hetzner_client = await create_client(token)

        try:
            await hetzner_client.update_load_balancer(lb_id, name=message.text)
            await close_client(hetzner_client)

            audit_repo = AuditLogRepository(session)
            await audit_repo.log(
                action="loadbalancer_rename",
                success=True,
                client_id=client_id,
                resource_type="loadbalancer",
                resource_id=lb_id,
                details={"new_name": message.text},
            )

            await message.answer("🎉✅ Load Balancer remark updated successfully.")
        except Exception as e:
            await close_client(hetzner_client)
            await message.answer(f"⚠️❌ Failed to update remark: {e!s}")

    await state.clear()
