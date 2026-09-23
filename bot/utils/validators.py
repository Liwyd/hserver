import ipaddress
import re


def validate_remark(remark: str) -> tuple[bool, str | None]:
    if not remark or not remark.strip():
        return False, "Remark cannot be empty"
    if " " in remark:
        return False, "Remark cannot contain spaces"
    if len(remark) > 64:
        return False, "Remark too long (max 64 characters)"
    if not re.match(r"^[a-zA-Z0-9_-]+$", remark):
        return False, "Remark can only contain letters, numbers, underscores, and hyphens"
    return True, None


def validate_cidr(cidr: str) -> tuple[bool, str | None]:
    try:
        network = ipaddress.ip_network(cidr, strict=False)
        if network.prefixlen < 8 or network.prefixlen > 24:
            return False, "CIDR prefix must be between /8 and /24"
        return True, None
    except ValueError:
        return False, "Invalid CIDR format"


def validate_size_gb(size: str) -> tuple[bool, str | None, int | None]:
    try:
        size_int = int(size)
        if size_int < 10:
            return False, "Minimum size is 10 GB", None
        if size_int > 10000:
            return False, "Maximum size is 10000 GB", None
        if size_int % 10 != 0:
            return False, "Size must be a multiple of 10 GB", None
        return True, None, size_int
    except ValueError:
        return False, "Size must be a number", None


def validate_chat_id(chat_id: str) -> tuple[bool, str | None, int | None]:
    try:
        cid = int(chat_id)
        if cid <= 0:
            return False, "Chat ID must be positive", None
        return True, None, cid
    except ValueError:
        return False, "Chat ID must be a number", None


def validate_ssh_public_key(key: str) -> tuple[bool, str | None]:
    key = key.strip()
    valid_prefixes = ("ssh-rsa", "ssh-ed25519", "ecdsa-sha2-nistp256", "ecdsa-sha2-nistp384", "ecdsa-sha2-nistp521")
    if not any(key.startswith(prefix) for prefix in valid_prefixes):
        return False, "Invalid SSH public key format"
    parts = key.split()
    if len(parts) < 2:
        return False, "Invalid SSH public key format"
    return True, None


def validate_pem(pem: str, expected_type: str) -> tuple[bool, str | None]:
    pem = pem.strip()
    begin_marker = f"-----BEGIN {expected_type}-----"
    end_marker = f"-----END {expected_type}-----"
    if not pem.startswith(begin_marker) or not pem.endswith(end_marker):
        return False, f"Invalid PEM format. Expected {expected_type}"
    return True, None


def validate_domain(domain: str) -> tuple[bool, str | None]:
    if not domain:
        return False, "Domain cannot be empty"
    if domain.startswith("*."):
        domain = domain[2:]
    if not re.match(r"^[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$", domain):
        return False, "Invalid domain format"
    return True, None


def validate_domains(domains_str: str) -> tuple[bool, str | None, list[str]]:
    domains = [d.strip() for d in domains_str.split(",") if d.strip()]
    if not domains:
        return False, "At least one domain required", []
    for domain in domains:
        valid, err = validate_domain(domain)
        if not valid:
            return False, f"Invalid domain '{domain}': {err}", []
    return True, None, domains
