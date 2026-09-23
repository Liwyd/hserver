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
from bot.states import CertificateCreateStates, ManagedCertificateCreateStates
from bot.utils.callbacks import (
    CallbackAreas,
    CallbackSteps,
    CallbackTasks,
    create_callback,
    parse_callback,
)
from bot.utils.formatters import format_certificate_info
from bot.utils.validators import validate_domains, validate_remark

router = Router()


@router.callback_query(F.data.startswith(f"{CallbackAreas.CERTIFICATE}:{CallbackTasks.LIST}"))
async def certificate_list(callback: CallbackQuery):
    cb = parse_callback(callback.data)
    client_id = cb.target_id
    await show_certificate_list(callback, client_id)


async def show_certificate_list(callback: CallbackQuery, client_id: int):
    async with db.session() as session:
        client_repo = ClientRepository(session)
        client = await client_repo.get_by_id(client_id)
        if not client:
            await callback.answer("🔍❌ Not found [client].", show_alert=True)
            return

        token = decrypt_token(client.api_token_encrypted)
        hetzner_client = await create_client(token)
        certs = await hetzner_client.list_certificates()
        await close_client(hetzner_client)

    builder = InlineKeyboardBuilder()
    for cert in certs:
        builder.button(
            text=f"{cert.name} [{cert.type}]",
            callback_data=create_callback(
                CallbackAreas.CERTIFICATE, CallbackTasks.INFO, "", 0, 0, cert.id, str(client_id)
            ),
        )
    builder.adjust(1)

    builder.row(
        InlineKeyboardButton(
            text="➕ Add Certificate",
            callback_data=create_callback(
                CallbackAreas.CERTIFICATE, CallbackTasks.CREATE, CallbackSteps.NAME, 0, 0, client_id
            ),
        ),
        InlineKeyboardButton(
            text="🌍 Create Managed Cert",
            callback_data=create_callback(
                CallbackAreas.CERTIFICATE, CallbackTasks.CREATE, "managed_name", 0, 0, client_id
            ),
        ),
    )
    builder.row(
        InlineKeyboardButton(text="🔙 Back", callback_data=create_callback(CallbackAreas.CLIENT, CallbackTasks.LIST))
    )

    text = "📜 Certificates Menu\n👇 Select an action from the menu below."
    await callback.message.edit_text(text, reply_markup=builder.as_markup())
    await callback.answer()


@router.callback_query(F.data.startswith(f"{CallbackAreas.CERTIFICATE}:{CallbackTasks.INFO}"))
async def certificate_info(callback: CallbackQuery):
    cb = parse_callback(callback.data)
    cert_id = cb.target_id
    client_id = int(cb.extra) if cb.extra else 0

    async with db.session() as session:
        client_repo = ClientRepository(session)
        client = await client_repo.get_by_id(client_id)
        if not client:
            await callback.answer("🔍❌ Not found [client].", show_alert=True)
            return

        token = decrypt_token(client.api_token_encrypted)
        hetzner_client = await create_client(token)
        cert = await hetzner_client.get_certificate(cert_id)
        await close_client(hetzner_client)

    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="✏️ Change Remark",
            callback_data=create_callback(
                CallbackAreas.CERTIFICATE, CallbackTasks.EDIT, CallbackSteps.REMARK, 0, 0, cert_id, str(client_id)
            ),
        ),
        InlineKeyboardButton(
            text="🗑 Delete Certificate",
            callback_data=create_callback(
                CallbackAreas.CERTIFICATE,
                CallbackTasks.DELETE,
                CallbackSteps.CONFIRMATION,
                0,
                0,
                cert_id,
                str(client_id),
            ),
        ),
    )
    builder.row(
        InlineKeyboardButton(
            text="🔙 Back",
            callback_data=create_callback(CallbackAreas.CERTIFICATE, CallbackTasks.LIST, "", 0, 0, client_id),
        ),
    )

    text = format_certificate_info(cert)
    await callback.message.edit_text(text, reply_markup=builder.as_markup())
    await callback.answer()


@router.callback_query(F.data.startswith(f"{CallbackAreas.CERTIFICATE}:{CallbackTasks.CREATE}:{CallbackSteps.NAME}"))
async def certificate_create_name(callback: CallbackQuery, state: FSMContext):
    cb = parse_callback(callback.data)
    await state.set_state(CertificateCreateStates.waiting_name)
    await state.update_data(client_id=cb.target_id)
    await callback.message.edit_text("✏️ Enter a name for the certificate:")
    await callback.answer()


@router.message(CertificateCreateStates.waiting_name)
async def certificate_create_name_received(message: Message, state: FSMContext):
    valid, error = validate_remark(message.text)
    if not valid:
        await message.answer(
            "⚠️❌ Invalid name format. 🔍 Please enter a valid name without special characters and space."
        )
        return

    await state.update_data(name=message.text)
    await state.set_state(CertificateCreateStates.waiting_cert_pem)
    await message.answer("📜 Paste the certificate PEM:")


@router.message(CertificateCreateStates.waiting_cert_pem)
async def certificate_create_cert_received(message: Message, state: FSMContext):
    await state.update_data(cert_pem=message.text)
    await state.set_state(CertificateCreateStates.waiting_key_pem)
    await message.answer("🔐 Paste the private key PEM:")


@router.message(CertificateCreateStates.waiting_key_pem)
async def certificate_create_key_received(message: Message, state: FSMContext):
    data = await state.get_data()
    client_id = data["client_id"]

    async with db.session() as session:
        client_repo = ClientRepository(session)
        client = await client_repo.get_by_id(client_id)
        token = decrypt_token(client.api_token_encrypted)
        hetzner_client = await create_client(token)

        try:
            cert = await hetzner_client.create_certificate(data["name"], data["cert_pem"], message.text)
            await close_client(hetzner_client)

            audit_repo = AuditLogRepository(session)
            await audit_repo.log(
                action="certificate_create",
                success=True,
                client_id=client_id,
                resource_type="certificate",
                resource_id=cert.id,
                details={"name": data["name"]},
            )

            await message.answer("🎉✅ Certificate added successfully.")
        except Exception as e:
            await close_client(hetzner_client)
            await message.answer(f"⚠️❌ Certificate creation failed: {e!s}")

    await state.clear()


@router.callback_query(F.data.startswith(f"{CallbackAreas.CERTIFICATE}:{CallbackTasks.CREATE}:managed_name"))
async def managed_cert_create_name(callback: CallbackQuery, state: FSMContext):
    cb = parse_callback(callback.data)
    await state.set_state(ManagedCertificateCreateStates.waiting_name)
    await state.update_data(client_id=cb.target_id)
    await callback.message.edit_text("✏️ Enter a name for the managed certificate:")
    await callback.answer()


@router.message(ManagedCertificateCreateStates.waiting_name)
async def managed_cert_create_name_received(message: Message, state: FSMContext):
    valid, error = validate_remark(message.text)
    if not valid:
        await message.answer(
            "⚠️❌ Invalid name format. 🔍 Please enter a valid name without special characters and space."
        )
        return

    await state.update_data(name=message.text)
    await state.set_state(ManagedCertificateCreateStates.waiting_domains)
    await message.answer("🌐 Enter domain names (comma separated):")


@router.message(ManagedCertificateCreateStates.waiting_domains)
async def managed_cert_create_domains_received(message: Message, state: FSMContext):
    valid, error, domains = validate_domains(message.text)
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
            cert = await hetzner_client.create_managed_certificate(data["name"], domains)
            await close_client(hetzner_client)

            audit_repo = AuditLogRepository(session)
            await audit_repo.log(
                action="certificate_create_managed",
                success=True,
                client_id=client_id,
                resource_type="certificate",
                resource_id=cert.id,
                details={"name": data["name"], "domains": domains},
            )

            await message.answer("🎉✅ Managed certificate created successfully.")
        except Exception as e:
            await close_client(hetzner_client)
            await message.answer(f"⚠️❌ Certificate creation failed: {e!s}")

    await state.clear()


@router.callback_query(
    F.data.startswith(f"{CallbackAreas.CERTIFICATE}:{CallbackTasks.DELETE}:{CallbackSteps.CONFIRMATION}")
)
async def certificate_delete_confirm(callback: CallbackQuery):
    cb = parse_callback(callback.data)
    cert_id = cb.target_id
    client_id = int(cb.extra) if cb.extra else 0

    if cb.approve == 1:
        async with db.session() as session:
            client_repo = ClientRepository(session)
            client = await client_repo.get_by_id(client_id)
            token = decrypt_token(client.api_token_encrypted)
            hetzner_client = await create_client(token)

            try:
                await hetzner_client.delete_certificate(cert_id)
                await close_client(hetzner_client)

                audit_repo = AuditLogRepository(session)
                await audit_repo.log(
                    action="certificate_delete",
                    success=True,
                    client_id=client_id,
                    resource_type="certificate",
                    resource_id=cert_id,
                )

                await callback.message.edit_text("🎉✅ Certificate deleted successfully.")
            except Exception as e:
                await close_client(hetzner_client)
                await callback.message.edit_text(f"⚠️❌ Deletion failed: {e!s}")
    else:
        await callback.message.edit_text("🚫❌ Action cancelled. ↩️ Go back to the previous menu.")

    await callback.answer()
    await show_certificate_list(callback, client_id)


@router.callback_query(F.data.startswith(f"{CallbackAreas.CERTIFICATE}:{CallbackTasks.EDIT}:{CallbackSteps.REMARK}"))
async def certificate_edit_remark(callback: CallbackQuery, state: FSMContext):
    cb = parse_callback(callback.data)
    await state.set_state(CertificateCreateStates.waiting_name)
    await state.update_data(cert_id=cb.target_id, client_id=int(cb.extra) if cb.extra else 0, editing=True)
    await callback.message.edit_text("✏️ Enter new remark for the certificate:")
    await callback.answer()


@router.message(CertificateCreateStates.waiting_name)
async def certificate_edit_remark_received(message: Message, state: FSMContext):
    data = await state.get_data()
    if not data.get("editing"):
        return

    valid, error = validate_remark(message.text)
    if not valid:
        await message.answer(
            "⚠️❌ Invalid remark format. 🔍 Please enter a valid remark without special characters and space."
        )
        return

    cert_id = data["cert_id"]
    client_id = data["client_id"]

    async with db.session() as session:
        client_repo = ClientRepository(session)
        client = await client_repo.get_by_id(client_id)
        token = decrypt_token(client.api_token_encrypted)
        hetzner_client = await create_client(token)

        try:
            await hetzner_client.update_certificate(cert_id, name=message.text)
            await close_client(hetzner_client)

            audit_repo = AuditLogRepository(session)
            await audit_repo.log(
                action="certificate_rename",
                success=True,
                client_id=client_id,
                resource_type="certificate",
                resource_id=cert_id,
                details={"new_name": message.text},
            )

            await message.answer("🎉✅ Certificate remark updated successfully.")
        except Exception as e:
            await close_client(hetzner_client)
            await message.answer(f"⚠️❌ Failed to update remark: {e!s}")

    await state.clear()
