from aiogram import Dispatcher

from bot.handlers.admin import router as admin_router
from bot.handlers.callback import router as callback_router
from bot.handlers.certificate import router as certificate_router
from bot.handlers.client import router as client_router
from bot.handlers.firewall import router as firewall_router
from bot.handlers.ip import router as ip_router
from bot.handlers.loadbalancer import router as loadbalancer_router
from bot.handlers.network import router as network_router
from bot.handlers.placementgroup import router as placementgroup_router
from bot.handlers.server import router as server_router
from bot.handlers.snapshot import router as snapshot_router
from bot.handlers.sshkey import router as sshkey_router
from bot.handlers.start import router as start_router
from bot.handlers.volume import router as volume_router


def register_handlers(dp: Dispatcher):
    dp.include_router(start_router)
    dp.include_router(client_router)
    dp.include_router(server_router)
    dp.include_router(snapshot_router)
    dp.include_router(ip_router)
    dp.include_router(volume_router)
    dp.include_router(network_router)
    dp.include_router(firewall_router)
    dp.include_router(loadbalancer_router)
    dp.include_router(sshkey_router)
    dp.include_router(certificate_router)
    dp.include_router(placementgroup_router)
    dp.include_router(admin_router)
    dp.include_router(callback_router)
