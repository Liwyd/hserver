from aiogram.fsm.state import State, StatesGroup


class ClientCreateStates(StatesGroup):
    waiting_remark = State()
    waiting_token = State()


class ClientSettingsStates(StatesGroup):
    waiting_new_remark = State()
    waiting_new_token = State()


class ServerCreateStates(StatesGroup):
    waiting_remark = State()
    waiting_datacenter = State()
    waiting_plan = State()
    waiting_image = State()
    waiting_confirmation = State()


class ServerActionStates(StatesGroup):
    waiting_confirmation = State()


class ServerRebuildStates(StatesGroup):
    waiting_image = State()
    waiting_confirmation = State()


class ServerUpgradeStates(StatesGroup):
    waiting_plan = State()
    waiting_confirmation = State()


class SnapshotCreateStates(StatesGroup):
    waiting_remark = State()
    waiting_server = State()


class SnapshotDeleteStates(StatesGroup):
    waiting_snapshot = State()
    waiting_confirmation = State()


class PrimaryIPCreateStates(StatesGroup):
    waiting_type = State()
    waiting_location = State()


class FloatingIPCreateStates(StatesGroup):
    waiting_type = State()
    waiting_location = State()
    waiting_server = State()


class VolumeCreateStates(StatesGroup):
    waiting_remark = State()
    waiting_size = State()
    waiting_location = State()
    waiting_server = State()


class VolumeActionStates(StatesGroup):
    waiting_size = State()
    waiting_confirmation = State()


class NetworkCreateStates(StatesGroup):
    waiting_remark = State()
    waiting_ip_range = State()


class NetworkAddSubnetStates(StatesGroup):
    waiting_ip_range = State()
    waiting_type = State()


class NetworkAddRouteStates(StatesGroup):
    waiting_destination_gateway = State()


class FirewallCreateStates(StatesGroup):
    waiting_remark = State()


class LoadBalancerCreateStates(StatesGroup):
    waiting_remark = State()
    waiting_type = State()
    waiting_location = State()


class SSHKeyCreateStates(StatesGroup):
    waiting_name = State()
    waiting_public_key = State()


class CertificateCreateStates(StatesGroup):
    waiting_name = State()
    waiting_cert_pem = State()
    waiting_key_pem = State()


class ManagedCertificateCreateStates(StatesGroup):
    waiting_name = State()
    waiting_domains = State()


class PlacementGroupCreateStates(StatesGroup):
    waiting_name = State()
    waiting_type = State()


class AdminAddStates(StatesGroup):
    waiting_user_id = State()


class ServerAccessStates(StatesGroup):
    waiting_chat_id = State()


class GenericConfirmationStates(StatesGroup):
    waiting_confirmation = State()
