from dataclasses import dataclass


@dataclass
class CallbackData:
    area: str
    task: str
    step: str = ""
    page: int = 0
    approve: int = 0
    target_id: int = 0
    extra: str = ""

    def pack(self) -> str:
        parts = [
            self.area,
            self.task,
            self.step,
            str(self.page),
            str(self.approve),
            str(self.target_id),
            self.extra,
        ]
        return ":".join(parts)

    @classmethod
    def unpack(cls, data: str) -> "CallbackData":
        parts = data.split(":")
        while len(parts) < 7:
            parts.append("")
        return cls(
            area=parts[0],
            task=parts[1],
            step=parts[2],
            page=int(parts[3]) if parts[3] else 0,
            approve=int(parts[4]) if parts[4] else 0,
            target_id=int(parts[5]) if parts[5] else 0,
            extra=parts[6],
        )


def create_callback(
    area: str,
    task: str,
    step: str = "",
    page: int = 0,
    approve: int = 0,
    target_id: int = 0,
    extra: str = "",
) -> str:
    return CallbackData(area, task, step, page, approve, target_id, extra).pack()


def parse_callback(data: str) -> CallbackData:
    return CallbackData.unpack(data)


class CallbackAreas:
    CLIENT = "client"
    SERVER = "server"
    SNAPSHOT = "snapshot"
    PRIMARY_IP = "primaryip"
    FLOATING_IP = "floatingip"
    VOLUME = "volume"
    NETWORK = "network"
    FIREWALL = "firewall"
    LOADBALANCER = "loadbalancer"
    SSHKEY = "sshkey"
    CERTIFICATE = "certificate"
    PLACEMENTGROUP = "placementgroup"
    ADMIN = "admin"
    HOME = "home"


class CallbackTasks:
    LIST = "list"
    INFO = "info"
    CREATE = "create"
    EDIT = "edit"
    DELETE = "delete"
    SETTINGS = "settings"
    ACTION = "action"
    CONFIRM = "confirm"
    BACK = "back"
    REFRESH = "refresh"


class CallbackSteps:
    REMARK = "remark"
    DATACENTER = "datacenter"
    PLAN = "plan"
    IMAGE = "image"
    CONFIRMATION = "confirmation"
    TYPE = "type"
    LOCATION = "location"
    SIZE = "size"
    SERVER = "server"
    IP_RANGE = "iprange"
    SUBNET_TYPE = "subnettype"
    DESTINATION_GATEWAY = "destgw"
    NAME = "name"
    PUBLIC_KEY = "pubkey"
    CERT_PEM = "certpem"
    KEY_PEM = "keypem"
    DOMAINS = "domains"
    TOKEN = "token"
    CHAT_ID = "chatid"
