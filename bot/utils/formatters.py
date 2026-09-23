from datetime import UTC, datetime

from bot.hetzner.models import (
    Certificate,
    Firewall,
    FloatingIP,
    LoadBalancer,
    Network,
    PlacementGroup,
    PrimaryIP,
    Server,
    Snapshot,
    SSHKey,
    Volume,
)


def format_server_status(status: str) -> str:
    status_map = {
        "running": "🟢",
        "off": "🔴",
        "starting": "🟡",
        "stopping": "🔴",
    }
    return status_map.get(status, "⚪️")


def format_server_button(server: Server) -> str:
    return f"{format_server_status(server.status)} {server.name} [{server.status}]"


def format_server_info(server: Server) -> str:
    public_net = server.public_net
    ipv4 = public_net.get("ipv4", {}).get("ip", "N/A")
    ipv6 = public_net.get("ipv6", {}).get("ip", "N/A")

    location = server.datacenter.get("location", "Unknown")
    dc_name = server.datacenter.get("name", "Unknown")

    server_type = server.server_type
    cores = server_type.get("cores", 0)
    memory = server_type.get("memory", 0)

    image = server.image.get("description", server.image.get("name", "Unknown"))

    traffic = server.get("traffic", {})
    incoming_gb = traffic.get("incoming", 0) / (1024**3)
    outgoing_gb = traffic.get("outgoing", 0) / (1024**3)
    total_gb = incoming_gb + outgoing_gb
    included_gb = traffic.get("included", 0) / (1024**3)
    used_percent = (outgoing_gb / included_gb * 100) if included_gb > 0 else 0
    billable_gb = max(0, outgoing_gb - included_gb)

    pricing = server_type.get("prices", [])
    hourly_price = next((p.get("price_hourly", {}).get("net", 0) for p in pricing if p.get("location") == location), 0)
    monthly_price = next(
        (p.get("price_monthly", {}).get("net", 0) for p in pricing if p.get("location") == location), 0
    )

    created = server.created
    if isinstance(created, str):
        created = datetime.fromisoformat(created.replace("Z", "+00:00"))
    days_ago = (datetime.now(UTC) - created).days

    return (
        f"🚀 Name: {server.name} [{server.status}]\n"
        f"🔗 IPV4: {ipv4}\n"
        f"🔗 IPV6: {ipv6}\n"
        f"🌍 County: {location}, {dc_name}\n"
        f"⚙️ Cpu: {cores} Core\n"
        f"💾 Ram: {memory} GB\n"
        f"💿 Disk: {server.primary_disk_size} GB\n"
        f"📸 Snapshots: {len([v for v in server.volumes if v])}\n"
        f"🖼 Image: {image}\n"
        f"📊 Traffic:\n"
        f" • In: {incoming_gb:.3f} GB\n"
        f" • Out: {outgoing_gb:.3f} GB\n"
        f" • Total: {total_gb:.3f} GB\n"
        f" • Included: {included_gb:.1f} GB\n"
        f" • Used: {used_percent:.1f}% [Out/Included traffic]\n"
        f" • Billable: {billable_gb:.1f} GB\n"
        f"💰 Price:\n"
        f" • Hourly: {hourly_price:.4f}€\n"
        f" • Monthly: {monthly_price:.2f}€\n"
        f"📅 Created: {created.strftime('%Y-%m-%d')} [{days_ago} days ago]"
    )


def format_snapshot_info(snapshot: Snapshot) -> str:
    size_gb = snapshot.size / (1024**3) if snapshot.size > 1024**3 else snapshot.size
    created = snapshot.created
    if isinstance(created, str):
        created = datetime.fromisoformat(created.replace("Z", "+00:00"))
    days_ago = (datetime.now(UTC) - created).days

    return (
        f"📸 Name: {snapshot.name or snapshot.description}\n"
        f"🔗 Status: {snapshot.status}\n"
        f"💾 Size: {size_gb:.1f} GB\n"
        f"📅 Created: {created.strftime('%Y-%m-%d')} [{days_ago} days ago]"
    )


def format_primary_ip_info(ip: PrimaryIP) -> str:
    assignee = ip.assignee_type or "Not assigned"
    assignee_id = ip.assignee_id or "N/A"
    created = ip.created
    if isinstance(created, str):
        created = datetime.fromisoformat(created.replace("Z", "+00:00"))
    days_ago = (datetime.now(UTC) - created).days

    return (
        f"🌐 Name: {ip.name}\n"
        f"🔗 IP: {ip.ip}\n"
        f"🔗 Assignee: {assignee}\n"
        f"🔗 Assignee ID: {assignee_id}\n"
        f"📅 Created: {created.strftime('%Y-%m-%d')} [{days_ago} days ago]"
    )


def format_floating_ip_info(ip: FloatingIP) -> str:
    server = ip.server.get("name", "Not assigned") if ip.server else "Not assigned"
    created = ip.created
    if isinstance(created, str):
        created = datetime.fromisoformat(created.replace("Z", "+00:00"))
    days_ago = (datetime.now(UTC) - created).days

    return (
        f"🔗 IP: {ip.ip}\n"
        f"🏷 Description: {ip.description}\n"
        f"🌍 Type: {ip.type}\n"
        f"🔗 Server: {server}\n"
        f"📅 Created: {created.strftime('%Y-%m-%d')} [{days_ago} days ago]"
    )


def format_volume_info(volume: Volume) -> str:
    server = volume.server.get("name", "Not attached") if volume.server else "Not attached"
    created = volume.created
    if isinstance(created, str):
        created = datetime.fromisoformat(created.replace("Z", "+00:00"))
    days_ago = (datetime.now(UTC) - created).days

    return (
        f"💾 Name: {volume.name}\n"
        f"📏 Size: {volume.size} GB\n"
        f"🌍 Location: {volume.location}\n"
        f"🔗 Server: {server}\n"
        f"📅 Created: {created.strftime('%Y-%m-%d')} [{days_ago} days ago]"
    )


def format_network_info(network: Network) -> str:
    subnets_str = "\n".join(f"  • {s.get('ip_range', 'N/A')} ({s.get('type', 'N/A')})" for s in network.subnets)
    routes_str = "\n".join(f"  • {r.get('destination', 'N/A')} → {r.get('gateway', 'N/A')}" for r in network.routes)
    created = network.created
    if isinstance(created, str):
        created = datetime.fromisoformat(created.replace("Z", "+00:00"))
    days_ago = (datetime.now(UTC) - created).days

    return (
        f"🕸 Name: {network.name}\n"
        f"🔗 IP Range: {network.ip_range}\n"
        f"📍 Subnets:\n{subnets_str if subnets_str else '  • None'}\n"
        f"🛤 Routes:\n{routes_str if routes_str else '  • None'}\n"
        f"📅 Created: {created.strftime('%Y-%m-%d')} [{days_ago} days ago]"
    )


def format_firewall_info(firewall: Firewall) -> str:
    applied_count = len(firewall.applied_to)
    created = firewall.created
    if isinstance(created, str):
        created = datetime.fromisoformat(created.replace("Z", "+00:00"))
    days_ago = (datetime.now(UTC) - created).days

    return (
        f"🛡 Name: {firewall.name}\n"
        f"📋 Rules: {len(firewall.rules)}\n"
        f"🔗 Applied to: {applied_count}\n"
        f"📅 Created: {created.strftime('%Y-%m-%d')} [{days_ago} days ago]"
    )


def format_load_balancer_info(lb: LoadBalancer) -> str:
    lb_type = lb.load_balancer_type.get("name", "Unknown")
    ip = lb.public_net.get("ipv4", {}).get("ip", "N/A")
    location = lb.location.get("name", "Unknown")
    target_count = len(lb.targets)
    created = lb.created
    if isinstance(created, str):
        created = datetime.fromisoformat(created.replace("Z", "+00:00"))
    days_ago = (datetime.now(UTC) - created).days

    return (
        f"⚖️ Name: {lb.name}\n"
        f"🌍 Type: {lb_type}\n"
        f"🔗 IP: {ip}\n"
        f"🌍 Location: {location}\n"
        f"🔗 Targets: {target_count}\n"
        f"📅 Created: {created.strftime('%Y-%m-%d')} [{days_ago} days ago]"
    )


def format_ssh_key_info(key: SSHKey) -> str:
    created = key.created
    if isinstance(created, str):
        created = datetime.fromisoformat(created.replace("Z", "+00:00"))
    days_ago = (datetime.now(UTC) - created).days

    return (
        f"🔐 Name: {key.name}\n"
        f"🔑 Fingerprint: {key.fingerprint}\n"
        f"📅 Created: {created.strftime('%Y-%m-%d')} [{days_ago} days ago]"
    )


def format_certificate_info(cert: Certificate) -> str:
    domains = ", ".join(cert.domain_names) if cert.domain_names else "N/A"
    created = cert.created
    if isinstance(created, str):
        created = datetime.fromisoformat(created.replace("Z", "+00:00"))
    days_ago = (datetime.now(UTC) - created).days

    return (
        f"📜 Name: {cert.name}\n"
        f"🔗 Type: {cert.type}\n"
        f"🌐 Domains: {domains}\n"
        f"📅 Created: {created.strftime('%Y-%m-%d')} [{days_ago} days ago]"
    )


def format_placement_group_info(pg: PlacementGroup) -> str:
    created = pg.created
    if isinstance(created, str):
        created = datetime.fromisoformat(created.replace("Z", "+00:00"))
    days_ago = (datetime.now(UTC) - created).days

    return f"📍 Name: {pg.name}\n🔗 Type: {pg.type}\n📅 Created: {created.strftime('%Y-%m-%d')} [{days_ago} days ago]"


def format_client_button(client) -> str:
    return f"📁 {client.remark}"


def format_bytes(bytes_val: int) -> str:
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if bytes_val < 1024:
            return f"{bytes_val:.1f} {unit}"
        bytes_val /= 1024
    return f"{bytes_val:.1f} PB"
