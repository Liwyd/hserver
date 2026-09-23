from datetime import datetime

from pydantic import BaseModel, Field


class HetznerMeta(BaseModel):
    pagination: dict | None = None


class Datacenter(BaseModel):
    id: int
    name: str
    description: str
    location: str
    server_types: dict[str, list[str]]


class ServerType(BaseModel):
    id: int
    name: str
    cores: int
    memory: float
    disk: int
    storage_type: str
    cpu_type: str
    architecture: str
    prices: list[dict]


class Image(BaseModel):
    id: int
    name: str
    description: str
    type: str
    status: str
    os_flavor: str | None = None
    os_version: str | None = None
    architecture: str | None = None
    created: datetime
    deprecated: datetime | None = None


class Server(BaseModel):
    id: int
    name: str
    status: str
    created: datetime
    public_net: dict
    server_type: dict
    datacenter: dict
    image: dict
    labels: dict
    backup_window: str | None = None
    protection: dict
    volumes: list[int]
    primary_disk_size: int
    placement_group: dict | None = None


class ServerCreateRequest(BaseModel):
    name: str
    server_type: str
    image: str
    datacenter: str | None = None
    location: str | None = None
    start_after_create: bool = True
    ssh_keys: list[str] = Field(default_factory=list)
    user_data: str | None = None
    labels: dict = Field(default_factory=dict)
    volumes: list[int] = Field(default_factory=list)
    networks: list[int] = Field(default_factory=list)
    placement_group: int | None = None
    automount: bool = True


class ServerCreateResponse(BaseModel):
    server: Server
    root_password: str | None = None
    next_actions: list[dict]


class Action(BaseModel):
    id: int
    command: str
    status: str
    progress: int
    started: datetime
    finished: datetime | None = None
    resources: list[dict]
    error: dict | None = None


class Snapshot(BaseModel):
    id: int
    name: str
    description: str
    type: str
    status: str
    created: datetime
    server: dict | None = None
    labels: dict
    size: float
    disk_size: float
    os_flavor: str | None = None
    os_version: str | None = None


class PrimaryIP(BaseModel):
    id: int
    name: str
    type: str
    ip: str
    dns_ptr: str | None = None
    assignee_type: str | None = None
    assignee_id: int | None = None
    blocked: bool
    created: datetime
    labels: dict
    protection: dict


class FloatingIP(BaseModel):
    id: int
    description: str
    type: str
    ip: str
    home_location: str
    server: dict | None = None
    labels: dict
    protection: dict
    created: datetime


class Volume(BaseModel):
    id: int
    name: str
    size: int
    location: str
    server: dict | None = None
    format: str | None = None
    labels: dict
    protection: dict
    created: datetime


class Network(BaseModel):
    id: int
    name: str
    ip_range: str
    subnets: list[dict]
    routes: list[dict]
    labels: dict
    protection: dict
    created: datetime


class Firewall(BaseModel):
    id: int
    name: str
    rules: list[dict]
    applied_to: list[dict]
    labels: dict
    created: datetime


class LoadBalancer(BaseModel):
    id: int
    name: str
    load_balancer_type: dict
    public_net: dict
    location: dict
    services: list[dict]
    targets: list[dict]
    labels: dict
    protection: dict
    created: datetime


class SSHKey(BaseModel):
    id: int
    name: str
    fingerprint: str
    public_key: str
    labels: dict
    created: datetime


class Certificate(BaseModel):
    id: int
    name: str
    type: str
    domain_names: list[str]
    labels: dict
    created: datetime
    not_valid_before: datetime | None = None
    not_valid_after: datetime | None = None


class PlacementGroup(BaseModel):
    id: int
    name: str
    type: str
    labels: dict
    created: datetime
    servers: list[int]


class Traffic(BaseModel):
    traffic: dict


class ConsoleResponse(BaseModel):
    url: str
    short_lived_token: str
