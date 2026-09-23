import asyncio
import hashlib

import httpx

from bot.hetzner.exceptions import (
    HetznerAuthError,
    HetznerError,
    HetznerNotFoundError,
    HetznerRateLimitError,
)
from bot.hetzner.models import (
    Action,
    Certificate,
    ConsoleResponse,
    Datacenter,
    Firewall,
    FloatingIP,
    Image,
    LoadBalancer,
    Network,
    PlacementGroup,
    PrimaryIP,
    Server,
    ServerCreateRequest,
    ServerCreateResponse,
    ServerType,
    Snapshot,
    SSHKey,
    Volume,
)
from bot.hetzner.rate_limiter import rate_limiter


class HetznerClient:
    def __init__(self, api_token: str):
        self.api_token = api_token
        self.base_url = "https://api.hetzner.cloud/v1"
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self):
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            headers={"Authorization": f"Bearer {self.api_token}", "Content-Type": "application/json"},
            timeout=30.0,
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._client:
            await self._client.aclose()

    async def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
        if not self._client:
            raise HetznerError("Client not initialized", status_code=0)

        await rate_limiter.acquire(self.api_token)

        for attempt in range(3):
            try:
                response = await self._client.request(method, path, **kwargs)
                rate_limiter.update_from_headers(self.api_token, dict(response.headers))

                if response.status_code == 429:
                    retry_after = float(response.headers.get("Retry-After", "1"))
                    if attempt < 2:
                        await asyncio.sleep(retry_after)
                        continue
                    raise HetznerRateLimitError(
                        "Rate limit exceeded",
                        status_code=429,
                        retry_after=retry_after,
                    )

                if response.status_code == 401:
                    raise HetznerAuthError("Invalid API token", status_code=401)

                if response.status_code == 404:
                    raise HetznerNotFoundError("Resource not found", status_code=404)

                if response.status_code >= 400:
                    data = (
                        response.json()
                        if response.headers.get("content-type", "").startswith("application/json")
                        else {}
                    )
                    raise HetznerError(
                        data.get("error", {}).get("message", f"HTTP {response.status_code}"),
                        code=data.get("error", {}).get("code"),
                        status_code=response.status_code,
                    )

                return response

            except (httpx.TimeoutException, httpx.NetworkError) as e:
                if attempt == 2:
                    raise HetznerError(f"Network error: {e}", status_code=0)
                await asyncio.sleep(2**attempt)

        raise HetznerError("Max retries exceeded", status_code=0)

    async def _get(self, path: str, params: dict | None = None) -> dict:
        response = await self._request("GET", path, params=params)
        return response.json()

    async def _post(self, path: str, json: dict | None = None) -> dict:
        response = await self._request("POST", path, json=json)
        return response.json()

    async def _put(self, path: str, json: dict | None = None) -> dict:
        response = await self._request("PUT", path, json=json)
        return response.json()

    async def _delete(self, path: str) -> None:
        await self._request("DELETE", path)

    async def _patch(self, path: str, json: dict | None = None) -> dict:
        response = await self._request("PATCH", path, json=json)
        return response.json()

    async def _wait_for_action(self, action: Action, poll_interval: float = 3.0) -> Action:
        while action.status == "running":
            await asyncio.sleep(poll_interval)
            action = await self.get_action(action.id)
        return action

    async def get_action(self, action_id: int) -> Action:
        data = await self._get(f"/actions/{action_id}")
        return Action(**data["action"])

    def _hash_token(self) -> str:
        return hashlib.sha256(self.api_token.encode()).hexdigest()

    # Datacenters
    async def list_datacenters(self) -> list[Datacenter]:
        data = await self._get("/datacenters")
        return [Datacenter(**dc) for dc in data["datacenters"]]

    # Server Types
    async def list_server_types(self, architecture: str | None = None) -> list[ServerType]:
        params = {}
        if architecture:
            params["architecture"] = architecture
        data = await self._get("/server_types", params=params)
        return [ServerType(**st) for st in data["server_types"]]

    # Images
    async def list_images(self, type: str | None = None) -> list[Image]:
        params = {}
        if type:
            params["type"] = type
        data = await self._get("/images", params=params)
        return [Image(**img) for img in data["images"]]

    # Servers
    async def list_servers(self) -> list[Server]:
        data = await self._get("/servers")
        return [Server(**s) for s in data["servers"]]

    async def get_server(self, server_id: int) -> Server:
        data = await self._get(f"/servers/{server_id}")
        return Server(**data["server"])

    async def create_server(self, request: ServerCreateRequest) -> ServerCreateResponse:
        data = await self._post("/servers", json=request.model_dump(exclude_none=True))
        return ServerCreateResponse(**data)

    async def delete_server(self, server_id: int) -> None:
        await self._delete(f"/servers/{server_id}")

    async def power_on(self, server_id: int) -> Action:
        data = await self._post(f"/servers/{server_id}/actions/poweron")
        return Action(**data["action"])

    async def power_off(self, server_id: int) -> Action:
        data = await self._post(f"/servers/{server_id}/actions/poweroff")
        return Action(**data["action"])

    async def reboot(self, server_id: int) -> Action:
        data = await self._post(f"/servers/{server_id}/actions/reboot")
        return Action(**data["action"])

    async def reset(self, server_id: int) -> Action:
        data = await self._post(f"/servers/{server_id}/actions/reset")
        return Action(**data["action"])

    async def rebuild(self, server_id: int, image: str) -> Action:
        data = await self._post(f"/servers/{server_id}/actions/rebuild", json={"image": image})
        return Action(**data["action"])

    async def reset_password(self, server_id: int) -> dict:
        data = await self._post(f"/servers/{server_id}/actions/reset_password")
        return data

    async def upgrade(self, server_id: int, server_type: str) -> Action:
        data = await self._post(f"/servers/{server_id}/actions/upgrade", json={"server_type": server_type})
        return Action(**data["action"])

    async def create_snapshot(self, server_id: int, description: str, labels: dict | None = None) -> Snapshot:
        data = await self._post(
            f"/servers/{server_id}/actions/create_image",
            json={"description": description, "type": "snapshot", "labels": labels or {}},
        )
        return Snapshot(**data["image"])

    async def assign_primary_ip(self, server_id: int, ip_id: int) -> Action:
        data = await self._post(f"/servers/{server_id}/actions/assign_primary_ip", json={"primary_ip": ip_id})
        return Action(**data["action"])

    async def unassign_primary_ip(self, server_id: int, ip_type: str) -> Action:
        data = await self._post(f"/servers/{server_id}/actions/unassign_primary_ip", json={"type": ip_type})
        return Action(**data["action"])

    async def change_primary_ip(self, server_id: int, ip_id: int, ip_type: str) -> Action:
        data = await self._post(
            f"/servers/{server_id}/actions/change_primary_ip",
            json={"primary_ip": ip_id, "type": ip_type},
        )
        return Action(**data["action"])

    async def get_server_traffic(self, server_id: int) -> dict:
        data = await self._get(f"/servers/{server_id}/traffic")
        return data["traffic"]

    async def get_server_console(self, server_id: int) -> ConsoleResponse:
        data = await self._post(f"/servers/{server_id}/actions/console")
        return ConsoleResponse(**data)

    async def change_server_alias(self, server_id: int, name: str) -> Server:
        data = await self._put(f"/servers/{server_id}", json={"name": name})
        return Server(**data["server"])

    async def change_server_labels(self, server_id: int, labels: dict) -> Server:
        data = await self._put(f"/servers/{server_id}", json={"labels": labels})
        return Server(**data["server"])

    # Snapshots
    async def list_snapshots(self) -> list[Snapshot]:
        data = await self._get("/images", params={"type": "snapshot"})
        return [Snapshot(**img) for img in data["images"]]

    async def get_snapshot(self, snapshot_id: int) -> Snapshot:
        data = await self._get(f"/images/{snapshot_id}")
        return Snapshot(**data["image"])

    async def delete_snapshot(self, snapshot_id: int) -> None:
        await self._delete(f"/images/{snapshot_id}")

    async def change_snapshot_description(self, snapshot_id: int, description: str) -> Snapshot:
        data = await self._put(f"/images/{snapshot_id}", json={"description": description})
        return Snapshot(**data["image"])

    # Primary IPs
    async def list_primary_ips(self) -> list[PrimaryIP]:
        data = await self._get("/primary_ips")
        return [PrimaryIP(**ip) for ip in data["primary_ips"]]

    async def get_primary_ip(self, ip_id: int) -> PrimaryIP:
        data = await self._get(f"/primary_ips/{ip_id}")
        return PrimaryIP(**data["primary_ip"])

    async def create_primary_ip(
        self, type: str, datacenter: str | None = None, labels: dict | None = None
    ) -> PrimaryIP:
        data = await self._post(
            "/primary_ips",
            json={"type": type, "datacenter": datacenter, "labels": labels or {}},
        )
        return PrimaryIP(**data["primary_ip"])

    async def delete_primary_ip(self, ip_id: int) -> None:
        await self._delete(f"/primary_ips/{ip_id}")

    async def update_primary_ip(
        self, ip_id: int, name: str | None = None, labels: dict | None = None, dns_ptr: dict | None = None
    ) -> PrimaryIP:
        payload = {}
        if name:
            payload["name"] = name
        if labels is not None:
            payload["labels"] = labels
        if dns_ptr is not None:
            payload["dns_ptr"] = dns_ptr
        data = await self._put(f"/primary_ips/{ip_id}", json=payload)
        return PrimaryIP(**data["primary_ip"])

    async def assign_primary_ip_to_server(self, ip_id: int, server_id: int) -> PrimaryIP:
        data = await self._post(f"/primary_ips/{ip_id}/actions/assign", json={"assignee_id": server_id})
        return PrimaryIP(**data["primary_ip"])

    async def unassign_primary_ip_from_server(self, ip_id: int) -> PrimaryIP:
        data = await self._post(f"/primary_ips/{ip_id}/actions/unassign")
        return PrimaryIP(**data["primary_ip"])

    # Floating IPs
    async def list_floating_ips(self) -> list[FloatingIP]:
        data = await self._get("/floating_ips")
        return [FloatingIP(**ip) for ip in data["floating_ips"]]

    async def get_floating_ip(self, ip_id: int) -> FloatingIP:
        data = await self._get(f"/floating_ips/{ip_id}")
        return FloatingIP(**data["floating_ip"])

    async def create_floating_ip(
        self,
        type: str,
        home_location: str | None = None,
        server: int | None = None,
        description: str | None = None,
        labels: dict | None = None,
    ) -> FloatingIP:
        payload = {"type": type, "labels": labels or {}}
        if home_location:
            payload["home_location"] = home_location
        if server:
            payload["server"] = server
        if description:
            payload["description"] = description
        data = await self._post("/floating_ips", json=payload)
        return FloatingIP(**data["floating_ip"])

    async def delete_floating_ip(self, ip_id: int) -> None:
        await self._delete(f"/floating_ips/{ip_id}")

    async def update_floating_ip(
        self, ip_id: int, description: str | None = None, labels: dict | None = None, dns_ptr: dict | None = None
    ) -> FloatingIP:
        payload = {}
        if description is not None:
            payload["description"] = description
        if labels is not None:
            payload["labels"] = labels
        if dns_ptr is not None:
            payload["dns_ptr"] = dns_ptr
        data = await self._put(f"/floating_ips/{ip_id}", json=payload)
        return FloatingIP(**data["floating_ip"])

    async def assign_floating_ip(self, ip_id: int, server_id: int) -> FloatingIP:
        data = await self._post(f"/floating_ips/{ip_id}/actions/assign", json={"server": server_id})
        return FloatingIP(**data["floating_ip"])

    async def unassign_floating_ip(self, ip_id: int) -> FloatingIP:
        data = await self._post(f"/floating_ips/{ip_id}/actions/unassign")
        return FloatingIP(**data["floating_ip"])

    async def change_floating_ip_dns(self, ip_id: int, ip: str, dns_ptr: str) -> FloatingIP:
        data = await self._post(f"/floating_ips/{ip_id}/actions/change_dns_ptr", json={"ip": ip, "dns_ptr": dns_ptr})
        return FloatingIP(**data["floating_ip"])

    # Volumes
    async def list_volumes(self) -> list[Volume]:
        data = await self._get("/volumes")
        return [Volume(**v) for v in data["volumes"]]

    async def get_volume(self, volume_id: int) -> Volume:
        data = await self._get(f"/volumes/{volume_id}")
        return Volume(**data["volume"])

    async def create_volume(
        self,
        name: str,
        size: int,
        location: str,
        server: int | None = None,
        format: str | None = None,
        labels: dict | None = None,
    ) -> Volume:
        payload = {"name": name, "size": size, "location": location, "labels": labels or {}}
        if server:
            payload["server"] = server
        if format:
            payload["format"] = format
        data = await self._post("/volumes", json=payload)
        return Volume(**data["volume"])

    async def delete_volume(self, volume_id: int) -> None:
        await self._delete(f"/volumes/{volume_id}")

    async def resize_volume(self, volume_id: int, size: int) -> Volume:
        data = await self._post(f"/volumes/{volume_id}/actions/resize", json={"size": size})
        return Volume(**data["volume"])

    async def attach_volume(self, volume_id: int, server_id: int) -> Volume:
        data = await self._post(f"/volumes/{volume_id}/actions/attach", json={"server": server_id})
        return Volume(**data["volume"])

    async def detach_volume(self, volume_id: int) -> Volume:
        data = await self._post(f"/volumes/{volume_id}/actions/detach")
        return Volume(**data["volume"])

    async def update_volume(self, volume_id: int, name: str | None = None, labels: dict | None = None) -> Volume:
        payload = {}
        if name:
            payload["name"] = name
        if labels is not None:
            payload["labels"] = labels
        data = await self._put(f"/volumes/{volume_id}", json=payload)
        return Volume(**data["volume"])

    # Networks
    async def list_networks(self) -> list[Network]:
        data = await self._get("/networks")
        return [Network(**n) for n in data["networks"]]

    async def get_network(self, network_id: int) -> Network:
        data = await self._get(f"/networks/{network_id}")
        return Network(**data["network"])

    async def create_network(self, name: str, ip_range: str, labels: dict | None = None) -> Network:
        data = await self._post("/networks", json={"name": name, "ip_range": ip_range, "labels": labels or {}})
        return Network(**data["network"])

    async def delete_network(self, network_id: int) -> None:
        await self._delete(f"/networks/{network_id}")

    async def update_network(self, network_id: int, name: str | None = None, labels: dict | None = None) -> Network:
        payload = {}
        if name:
            payload["name"] = name
        if labels is not None:
            payload["labels"] = labels
        data = await self._put(f"/networks/{network_id}", json=payload)
        return Network(**data["network"])

    async def add_subnet(
        self, network_id: int, ip_range: str, network_zone: str, type: str, labels: dict | None = None
    ) -> Network:
        payload = {"ip_range": ip_range, "network_zone": network_zone, "type": type, "labels": labels or {}}
        data = await self._post(f"/networks/{network_id}/actions/add_subnet", json=payload)
        return Network(**data["network"])

    async def delete_subnet(self, network_id: int, ip_range: str) -> Network:
        data = await self._post(f"/networks/{network_id}/actions/delete_subnet", json={"ip_range": ip_range})
        return Network(**data["network"])

    async def add_route(self, network_id: int, destination: str, gateway: str) -> Network:
        data = await self._post(
            f"/networks/{network_id}/actions/add_route", json={"destination": destination, "gateway": gateway}
        )
        return Network(**data["network"])

    async def delete_route(self, network_id: int, destination: str, gateway: str) -> Network:
        data = await self._post(
            f"/networks/{network_id}/actions/delete_route", json={"destination": destination, "gateway": gateway}
        )
        return Network(**data["network"])

    # Firewalls
    async def list_firewalls(self) -> list[Firewall]:
        data = await self._get("/firewalls")
        return [Firewall(**f) for f in data["firewalls"]]

    async def get_firewall(self, firewall_id: int) -> Firewall:
        data = await self._get(f"/firewalls/{firewall_id}")
        return Firewall(**data["firewall"])

    async def create_firewall(self, name: str, rules: list[dict] | None = None, labels: dict | None = None) -> Firewall:
        payload = {"name": name, "rules": rules or [], "labels": labels or {}}
        data = await self._post("/firewalls", json=payload)
        return Firewall(**data["firewall"])

    async def delete_firewall(self, firewall_id: int) -> None:
        await self._delete(f"/firewalls/{firewall_id}")

    async def update_firewall(self, firewall_id: int, name: str | None = None, labels: dict | None = None) -> Firewall:
        payload = {}
        if name:
            payload["name"] = name
        if labels is not None:
            payload["labels"] = labels
        data = await self._put(f"/firewalls/{firewall_id}", json=payload)
        return Firewall(**data["firewall"])

    async def set_firewall_rules(self, firewall_id: int, rules: list[dict]) -> Firewall:
        data = await self._put(f"/firewalls/{firewall_id}", json={"rules": rules})
        return Firewall(**data["firewall"])

    async def apply_firewall_to_resources(self, firewall_id: int, resources: list[dict]) -> Firewall:
        data = await self._post(f"/firewalls/{firewall_id}/actions/apply_to_resources", json={"resources": resources})
        return Firewall(**data["firewall"])

    async def remove_firewall_from_resources(self, firewall_id: int, resources: list[dict]) -> Firewall:
        data = await self._post(
            f"/firewalls/{firewall_id}/actions/remove_from_resources", json={"resources": resources}
        )
        return Firewall(**data["firewall"])

    # Load Balancers
    async def list_load_balancers(self) -> list[LoadBalancer]:
        data = await self._get("/load_balancers")
        return [LoadBalancer(**lb) for lb in data["load_balancers"]]

    async def get_load_balancer(self, lb_id: int) -> LoadBalancer:
        data = await self._get(f"/load_balancers/{lb_id}")
        return LoadBalancer(**data["load_balancer"])

    async def create_load_balancer(
        self,
        name: str,
        load_balancer_type: str,
        location: str,
        network_zone: str | None = None,
        labels: dict | None = None,
        services: list[dict] | None = None,
    ) -> LoadBalancer:
        payload = {
            "name": name,
            "load_balancer_type": load_balancer_type,
            "location": location,
            "labels": labels or {},
        }
        if network_zone:
            payload["network_zone"] = network_zone
        if services:
            payload["services"] = services
        data = await self._post("/load_balancers", json=payload)
        return LoadBalancer(**data["load_balancer"])

    async def delete_load_balancer(self, lb_id: int) -> None:
        await self._delete(f"/load_balancers/{lb_id}")

    async def update_load_balancer(
        self, lb_id: int, name: str | None = None, labels: dict | None = None
    ) -> LoadBalancer:
        payload = {}
        if name:
            payload["name"] = name
        if labels is not None:
            payload["labels"] = labels
        data = await self._put(f"/load_balancers/{lb_id}", json=payload)
        return LoadBalancer(**data["load_balancer"])

    async def add_load_balancer_target(self, lb_id: int, target: dict) -> LoadBalancer:
        data = await self._post(f"/load_balancers/{lb_id}/actions/add_target", json=target)
        return LoadBalancer(**data["load_balancer"])

    async def remove_load_balancer_target(self, lb_id: int, target: dict) -> LoadBalancer:
        data = await self._post(f"/load_balancers/{lb_id}/actions/remove_target", json=target)
        return LoadBalancer(**data["load_balancer"])

    async def add_load_balancer_service(self, lb_id: int, service: dict) -> LoadBalancer:
        data = await self._post(f"/load_balancers/{lb_id}/actions/add_service", json=service)
        return LoadBalancer(**data["load_balancer"])

    async def delete_load_balancer_service(self, lb_id: int, service_index: int) -> LoadBalancer:
        data = await self._delete(f"/load_balancers/{lb_id}/actions/delete_service", params={"service": service_index})
        return LoadBalancer(**data["load_balancer"])

    # SSH Keys
    async def list_ssh_keys(self) -> list[SSHKey]:
        data = await self._get("/ssh_keys")
        return [SSHKey(**k) for k in data["ssh_keys"]]

    async def get_ssh_key(self, key_id: int) -> SSHKey:
        data = await self._get(f"/ssh_keys/{key_id}")
        return SSHKey(**data["ssh_key"])

    async def create_ssh_key(self, name: str, public_key: str, labels: dict | None = None) -> SSHKey:
        data = await self._post("/ssh_keys", json={"name": name, "public_key": public_key, "labels": labels or {}})
        return SSHKey(**data["ssh_key"])

    async def delete_ssh_key(self, key_id: int) -> None:
        await self._delete(f"/ssh_keys/{key_id}")

    async def update_ssh_key(self, key_id: int, name: str | None = None, labels: dict | None = None) -> SSHKey:
        payload = {}
        if name:
            payload["name"] = name
        if labels is not None:
            payload["labels"] = labels
        data = await self._put(f"/ssh_keys/{key_id}", json=payload)
        return SSHKey(**data["ssh_key"])

    # Certificates
    async def list_certificates(self) -> list[Certificate]:
        data = await self._get("/certificates")
        return [Certificate(**c) for c in data["certificates"]]

    async def get_certificate(self, cert_id: int) -> Certificate:
        data = await self._get(f"/certificates/{cert_id}")
        return Certificate(**data["certificate"])

    async def create_certificate(
        self, name: str, certificate: str, private_key: str, labels: dict | None = None
    ) -> Certificate:
        data = await self._post(
            "/certificates",
            json={"name": name, "certificate": certificate, "private_key": private_key, "labels": labels or {}},
        )
        return Certificate(**data["certificate"])

    async def create_managed_certificate(
        self, name: str, domain_names: list[str], labels: dict | None = None
    ) -> Certificate:
        data = await self._post(
            "/certificates",
            json={"name": name, "type": "managed", "domain_names": domain_names, "labels": labels or {}},
        )
        return Certificate(**data["certificate"])

    async def delete_certificate(self, cert_id: int) -> None:
        await self._delete(f"/certificates/{cert_id}")

    async def update_certificate(
        self, cert_id: int, name: str | None = None, labels: dict | None = None
    ) -> Certificate:
        payload = {}
        if name:
            payload["name"] = name
        if labels is not None:
            payload["labels"] = labels
        data = await self._put(f"/certificates/{cert_id}", json=payload)
        return Certificate(**data["certificate"])

    # Placement Groups
    async def list_placement_groups(self) -> list[PlacementGroup]:
        data = await self._get("/placement_groups")
        return [PlacementGroup(**pg) for pg in data["placement_groups"]]

    async def get_placement_group(self, pg_id: int) -> PlacementGroup:
        data = await self._get(f"/placement_groups/{pg_id}")
        return PlacementGroup(**data["placement_group"])

    async def create_placement_group(
        self, name: str, type: str = "spread", labels: dict | None = None
    ) -> PlacementGroup:
        data = await self._post("/placement_groups", json={"name": name, "type": type, "labels": labels or {}})
        return PlacementGroup(**data["placement_group"])

    async def delete_placement_group(self, pg_id: int) -> None:
        await self._delete(f"/placement_groups/{pg_id}")

    async def update_placement_group(
        self, pg_id: int, name: str | None = None, labels: dict | None = None
    ) -> PlacementGroup:
        payload = {}
        if name:
            payload["name"] = name
        if labels is not None:
            payload["labels"] = labels
        data = await self._put(f"/placement_groups/{pg_id}", json=payload)
        return PlacementGroup(**data["placement_group"])


async def create_client(api_token: str) -> HetznerClient:
    client = HetznerClient(api_token)
    await client.__aenter__()
    return client


async def close_client(client: HetznerClient) -> None:
    await client.__aexit__(None, None, None)
