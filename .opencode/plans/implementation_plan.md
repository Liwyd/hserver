# Telegram Cloud Server Management Bot — Implementation Plan

## Executive Summary

This document outlines a comprehensive implementation plan for a production-grade Telegram bot and CLI tool for managing Hetzner Cloud infrastructure. The system features inline keyboard-driven UI, multi-client management, role-based access control, and a companion terminal CLI.

**Estimated Timeline:** 6-8 weeks for full implementation  
**Team Size:** 1-2 engineers  
**Risk Level:** Medium (external API dependency, security-sensitive operations)

---

## 1. Architecture & Technology Stack

### 1.1 High-Level Architecture

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│   Telegram      │────▶│   Bot Application │────▶│  Hetzner Cloud  │
│   Users         │     │   (Python/aiogram)│     │  API (REST)     │
└─────────────────┘     └────────┬─────────┘     └─────────────────┘
                                 │
                    ┌────────────┼────────────┐
                    ▼            ▼            ▼
            ┌─────────────┐ ┌──────────┐ ┌──────────┐
            │ PostgreSQL  │ │  Redis   │ │  Files   │
            │  (Primary)  │ │ (Cache/  │ │ (Logs/   │
            │             │ │  State)  │ │  Backups)│
            └─────────────┘ └──────────┘ └──────────┘
                                 ▲
                    ┌────────────┴────────────┐
                    ▼                         ▼
            ┌─────────────┐           ┌─────────────┐
            │ CLI Tool    │           │  Background │
            │ (hserver)   │           │  Workers    │
            └─────────────┘           │ (Traffic    │
                                      │  Monitor)   │
                                      └─────────────┘
```

### 1.2 Technology Stack

| Layer | Technology | Version | Justification |
|-------|------------|---------|---------------|
| **Language** | Python | 3.11+ | Modern async support, excellent ecosystem |
| **Bot Framework** | aiogram | 3.x | Native async, FSM support, inline keyboards |
| **Database** | PostgreSQL | 15+ | ACID, JSON support, mature, production-ready |
| **ORM** | SQLAlchemy | 2.0+ | Async support, type-safe, migration-friendly |
| **Migrations** | Alembic | Latest | Version-controlled schema changes |
| **CLI Framework** | Typer | Latest | Modern, type-hint based, Rich integration |
| **CLI Output** | Rich | Latest | Beautiful terminal formatting |
| **Config** | Pydantic Settings | v2 | Type-safe config with env file support |
| **HTTP Client** | httpx | Latest | Async, HTTP/2, retry logic |
| **Containerization** | Docker | Latest | Standard deployment |
| **Orchestration** | Docker Compose | v2 | Simple multi-container |
| **CI/CD** | GitHub Actions | - | Native GitHub integration |
| **Code Quality** | Ruff | Latest | Fast, comprehensive linting/formatting |
| **Testing** | pytest + pytest-asyncio | Latest | Industry standard |
| **Secrets** | Docker secrets / .env | - | No hardcoded secrets |

### 1.3 Key Architectural Decisions

1. **Monolithic bot application** — Single process handles bot, CLI, and background tasks. Avoids distributed complexity.
2. **Host networking** — Both bot and DB use host networking per spec (simplifies local dev, but note: limits horizontal scaling).
3. **Stateful FSM per user** — aiogram's FSM with Redis storage for multi-step flows.
4. **Callback data encoding** — Compact binary/JSON encoding for inline keyboard actions.
5. **Message tracking** — Track sent message IDs per user for cleanup (chat hygiene).

---

## 2. Database Schema Design

### 2.1 Core Tables

```sql
-- Users (Telegram users who interact with bot)
CREATE TABLE users (
    id BIGSERIAL PRIMARY KEY,
    telegram_id BIGINT UNIQUE NOT NULL,
    username VARCHAR(255),
    first_name VARCHAR(255),
    last_name VARCHAR(255),
    role VARCHAR(50) NOT NULL DEFAULT 'user',  -- owner, admin, user
    is_bot_admin BOOLEAN DEFAULT FALSE,         -- env-configured admin
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Clients (Hetzner Cloud API accounts)
CREATE TABLE clients (
    id BIGSERIAL PRIMARY KEY,
    remark VARCHAR(255) NOT NULL,
    api_token_encrypted BYTEA NOT NULL,  -- Encrypted at rest
    token_hash VARCHAR(64) NOT NULL,     -- For deduplication (SHA256)
    owner_id BIGINT REFERENCES users(id),
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(remark)
);

-- User-Client Access (many-to-many for regular users)
CREATE TABLE user_client_access (
    user_id BIGINT REFERENCES users(id) ON DELETE CASCADE,
    client_id BIGINT REFERENCES clients(id) ON DELETE CASCADE,
    granted_by BIGINT REFERENCES users(id),
    granted_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (user_id, client_id)
);

-- Server Access Control (per-server granular access)
CREATE TABLE server_access (
    id BIGSERIAL PRIMARY KEY,
    client_id BIGINT REFERENCES clients(id) ON DELETE CASCADE,
    server_id BIGINT NOT NULL,  -- Hetzner server ID
    user_id BIGINT REFERENCES users(id) ON DELETE CASCADE,
    granted_by BIGINT REFERENCES users(id),
    granted_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (client_id, server_id, user_id)
);

-- Audit Log (security-critical actions)
CREATE TABLE audit_logs (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT REFERENCES users(id),
    client_id BIGINT REFERENCES clients(id),
    action VARCHAR(100) NOT NULL,
    resource_type VARCHAR(50),
    resource_id BIGINT,
    details JSONB,
    ip_address INET,
    success BOOLEAN NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Bot State (for FSM persistence across restarts)
CREATE TABLE bot_fsm_state (
    user_id BIGINT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    chat_id BIGINT NOT NULL,
    state_data JSONB NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Message Tracking (for cleanup)
CREATE TABLE user_messages (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT REFERENCES users(id) ON DELETE CASCADE,
    chat_id BIGINT NOT NULL,
    message_id BIGINT NOT NULL,
    message_type VARCHAR(50),  -- menu, info, confirmation, etc.
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Traffic Alert Config
CREATE TABLE traffic_alert_config (
    id BIGSERIAL PRIMARY KEY,
    client_id BIGINT REFERENCES clients(id) ON DELETE CASCADE,
    enabled BOOLEAN DEFAULT FALSE,
    alert_percent INTEGER DEFAULT 80,
    last_check TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Admin Management (bot-managed admins)
CREATE TABLE bot_admins (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT UNIQUE REFERENCES users(id) ON DELETE CASCADE,
    added_by BIGINT REFERENCES users(id),
    added_at TIMESTAMPTZ DEFAULT NOW()
);
```

### 2.2 Indexes

```sql
-- Performance indexes
CREATE INDEX idx_users_telegram_id ON users(telegram_id);
CREATE INDEX idx_users_role ON users(role);
CREATE INDEX idx_clients_owner ON clients(owner_id);
CREATE INDEX idx_user_client_access_user ON user_client_access(user_id);
CREATE INDEX idx_server_access_user ON server_access(user_id);
CREATE INDEX idx_server_access_server ON server_access(server_id);
CREATE INDEX idx_audit_logs_user ON audit_logs(user_id);
CREATE INDEX idx_audit_logs_client ON audit_logs(client_id);
CREATE INDEX idx_audit_logs_created ON audit_logs(created_at);
CREATE INDEX idx_user_messages_user ON user_messages(user_id);
```

### 2.3 Security Notes

- **API tokens encrypted at rest** using Fernet (AES-128) with key from env
- **Token hash** for deduplication without decrypting
- **Audit logging** on all mutating operations
- **Row-level security** via application logic (not Postgres RLS for simplicity)

---

## 3. Bot Implementation Plan

### 3.1 Project Structure

```
hserver/
├── bot/
│   ├── __init__.py
│   ├── main.py                 # Entry point
│   ├── config.py               # Pydantic settings
│   ├── database/
│   │   ├── __init__.py
│   │   ├── base.py             # SQLAlchemy base, session
│   │   ├── models.py           # ORM models
│   │   ├── repositories.py     # Data access layer
│   │   └── migrations/         # Alembic migrations
│   ├── encryption.py           # Token encryption/decryption
│   ├── hetzner/
│   │   ├── __init__.py
│   │   ├── client.py           # Hetzner API client
│   │   ├── models.py           # API response models
│   │   └── exceptions.py       # Custom exceptions
│   ├── handlers/
│   │   ├── __init__.py
│   │   ├── base.py             # Base handler class
│   │   ├── start.py            # /start, home screen
│   │   ├── client.py           # Client menu, settings
│   │   ├── server.py           # Server CRUD, actions
│   │   ├── snapshot.py         # Snapshot management
│   │   ├── ip.py               # Primary & Floating IPs
│   │   ├── volume.py           # Volume management
│   │   ├── network.py          # Network management
│   │   ├── firewall.py         # Firewall management
│   │   ├── loadbalancer.py     # Load balancer management
│   │   ├── sshkey.py           # SSH key management
│   │   ├── certificate.py      # Certificate management
│   │   ├── placementgroup.py   # Placement group management
│   │   ├── admin.py            # Admin management
│   │   └── callback.py         # Callback router
│   ├── keyboards/
│   │   ├── __init__.py
│   │   ├── base.py             # Keyboard builders
│   │   ├── client.py
│   │   ├── server.py
│   │   └── ... (per resource)
│   ├── states/
│   │   ├── __init__.py
│   │   ├── base.py             # Base state groups
│   │   ├── server.py           # Server creation flow states
│   │   ├── snapshot.py
│   │   ├── ip.py
│   │   ├── volume.py
│   │   ├── network.py
│   │   ├── firewall.py
│   │   ├── loadbalancer.py
│   │   ├── sshkey.py
│   │   ├── certificate.py
│   │   └── placementgroup.py
│   ├── middleware/
│   │   ├── __init__.py
│   │   ├── auth.py             # Authentication/authorization
│   │   ├── logging.py          # Request logging
│   │   ├── message_tracker.py  # Message cleanup
│   │   └── rate_limit.py       # Rate limiting
│   ├── services/
│   │   ├── __init__.py
│   │   ├── traffic_monitor.py  # Background traffic checks
│   │   ├── notification.py     # Admin notifications
│   │   └── audit.py            # Audit logging
│   ├── utils/
│   │   ├── __init__.py
│   │   ├── callbacks.py        # Callback data encoding/decoding
│   │   ├── formatters.py       # Message formatting
│   │   ├── validators.py       # Input validation
│   │   └── helpers.py
│   └── cli/
│       ├── __init__.py
│       ├── main.py             # CLI entry point
│       ├── commands/
│       │   ├── __init__.py
│       │   ├── bot.py          # Bot management commands
│       │   ├── server.py
│       │   ├── volume.py
│       │   ├── ip.py
│       │   ├── network.py
│       │   ├── firewall.py
│       │   ├── loadbalancer.py
│       │   ├── sshkey.py
│       │   ├── certificate.py
│       │   ├── placementgroup.py
│       │   ├── snapshot.py
│       │   └── client.py
│       └── output.py           # Rich formatting helpers
├── tests/
│   ├── __init__.py
│   ├── conftest.py
│   ├── unit/
│   ├── integration/
│   └── fixtures/
├── docker/
│   ├── Dockerfile
│   ├── docker-compose.yml
│   └── .env.example
├── scripts/
│   ├── install.sh
│   ├── update.sh
│   └── uninstall.sh
├── .github/
│   └── workflows/
│       ├── formatter.yml
│       ├── push_build.yml
│       ├── dockerhub_build.yml
│       └── release_build.yml
├── pyproject.toml
├── README.md
└── LICENSE
```

### 3.2 State Machine Design (FSM)

Each multi-step flow uses aiogram's FSM with distinct state groups:

```python
# Example: Server Creation Flow
class ServerCreateStates(StatesGroup):
    waiting_remark = State()
    waiting_datacenter = State()
    waiting_plan = State()
    waiting_image = State()
    waiting_confirmation = State()


# Example: Snapshot Creation
class SnapshotCreateStates(StatesGroup):
    waiting_remark = State()
    waiting_server = State()


# Example: Volume Creation
class VolumeCreateStates(StatesGroup):
    waiting_remark = State()
    waiting_size = State()
    waiting_location = State()
    waiting_server = State()  # Optional


# Example: Network Creation
class NetworkCreateStates(StatesGroup):
    waiting_remark = State()
    waiting_ip_range = State()


# Example: Add Subnet
class NetworkAddSubnetStates(StatesGroup):
    waiting_ip_range = State()
    waiting_type = State()


# Example: Add Route
class NetworkAddRouteStates(StatesGroup):
    waiting_destination_gateway = State()


# Example: Floating IP Creation
class FloatingIPCreateStates(StatesGroup):
    waiting_type = State()
    waiting_location = State()
    waiting_server = State()  # Optional


# Example: Primary IP Creation
class PrimaryIPCreateStates(StatesGroup):
    waiting_type = State()
    waiting_location = State()


# Example: Load Balancer Creation
class LoadBalancerCreateStates(StatesGroup):
    waiting_remark = State()
    waiting_type = State()
    waiting_location = State()


# Example: SSH Key Creation
class SSHKeyCreateStates(StatesGroup):
    waiting_name = State()
    waiting_public_key = State()


# Example: Certificate Creation
class CertificateCreateStates(StatesGroup):
    waiting_name = State()
    waiting_cert_pem = State()
    waiting_key_pem = State()


# Example: Managed Certificate
class ManagedCertificateCreateStates(StatesGroup):
    waiting_name = State()
    waiting_domains = State()


# Example: Placement Group Creation
class PlacementGroupCreateStates(StatesGroup):
    waiting_name = State()
    waiting_type = State()


# Example: Client Creation
class ClientCreateStates(StatesGroup):
    waiting_remark = State()
    waiting_token = State()


# Example: Admin Management
class AdminAddStates(StatesGroup):
    waiting_user_id = State()


# Example: Server Access Grant/Revoke
class ServerAccessStates(StatesGroup):
    waiting_chat_id = State()


# Example: Rebuild Server (Image Selection)
class ServerRebuildStates(StatesGroup):
    waiting_image = State()
    waiting_confirmation = State()


# Example: Upgrade Server (Plan Selection)
class ServerUpgradeStates(StatesGroup):
    waiting_plan = State()
    waiting_confirmation = State()


# Example: Delete Snapshot Selection
class SnapshotDeleteStates(StatesGroup):
    waiting_snapshot = State()
    waiting_confirmation = State()
```

### 3.3 Callback Data Encoding

Compact encoding for inline keyboard callbacks:

```python
# Format: "area:task:step:page:approve:target_id"
# Example: "server:create:datacenter:0:0:0"
# Example: "server:power_off:confirm:0:1:12345"


class CallbackData:
    AREA = "area"  # client, server, snapshot, ip, volume, network, firewall, lb, sshkey, cert, pg, admin
    TASK = "task"  # list, info, create, edit, delete, action (power_on, reboot, etc.)
    STEP = "step"  # remark, datacenter, plan, image, confirmation, etc.
    PAGE = "page"  # For pagination
    APPROVE = "approve"  # 0=no, 1=yes (for confirmations)
    TARGET = "target"  # Resource ID
```

### 3.4 Keyboard Builders

Each resource type has dedicated keyboard builders following the spec's grid layouts:

- **Client Menu**: 2-col grid (6 rows) + Back
- **Server List**: 2-col grid + Create/Back
- **Server Info**: Dynamic based on role (owner vs user)
- **Snapshot List**: 1-col + Create/Back
- **IP Lists**: 1-col + Create IPv4/IPv6/Back
- **Volume/Network/Firewall/LB/SSHKey/Cert/PG**: 1-col + Create/Back

### 3.5 Message Management

```python
class MessageTracker:
    async def track_message(self, user_id: int, chat_id: int, message_id: int, msg_type: str)
    async def cleanup_user_messages(self, user_id: int, chat_id: int, keep_types: list = None)
    async def get_last_message(self, user_id: int, chat_id: int, msg_type: str)
```

- Track all bot-sent messages per user/chat
- On navigation: delete previous messages of same/related types
- Keep confirmation dialogs until resolved

### 3.6 Middleware Stack

1. **AuthMiddleware** — Resolve user, check role, load client context
2. **RateLimitMiddleware** — Per-user rate limiting (configurable)
3. **MessageTrackerMiddleware** — Auto-track sent messages
4. **LoggingMiddleware** — Structured request logging
5. **ErrorHandlerMiddleware** — Graceful error handling with user feedback

---

## 4. CLI Implementation Plan

### 4.1 Command Structure

Using Typer with subcommand groups matching the spec exactly.

### 4.2 Shared Infrastructure

```python
# cli/output.py
class CLIOutput:
    def print_table(self, title: str, columns: list, rows: list)
    def print_panel(self, title: str, content: str, style: str)
    def print_success(self, msg: str)
    def print_error(self, msg: str)
    def print_warning(self, msg: str)
    def confirm(self, prompt: str) -> bool
    def spinner(self, text: str)
```

### 4.3 Client Context

All resource commands accept `--client ID` to scope operations. Default: first client or prompt.

---

## 5. Docker & Deployment

### 5.1 Dockerfile

```dockerfile
FROM python:3.11-alpine

ENV TZ=UTC
ENV PYTHONUNBUFFERED=1
ENV UV_VERSION=0.4.0

RUN apk add --no-cache \
    gcc \
    musl-dev \
    libffi-dev \
    openssl-dev \
    postgresql-dev \
    && pip install --no-cache-dir uv==$UV_VERSION

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY . .
RUN uv run alembic upgrade head

CMD ["uv", "run", "python", "-m", "bot.main"]
```

### 5.2 Docker Compose

```yaml
services:
  servermanagerbot:
    build: .
    network_mode: host
    restart: always
    env_file: .env
    depends_on:
      postgres:
        condition: service_healthy

  postgres:
    image: postgres:15-alpine
    network_mode: host
    restart: always
    environment:
      POSTGRES_DB: ${POSTGRES_DB}
      POSTGRES_USER: ${POSTGRES_USER}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
      PGPORT: ${PGPORT:-5432}
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER} -d ${POSTGRES_DB}"]
      interval: 5s
      timeout: 5s
      retries: 10

volumes:
  postgres_data:
```

### 5.3 Environment Variables

All variables from spec + encryption key for token encryption.

### 5.4 Installation Scripts

- `install.sh` — One-line install per spec
- `update.sh` — Backup, pull, rebuild, migrate, rollback on failure
- `uninstall.sh` — Confirmation + cleanup

---

## 6. CI/CD Pipelines

### 6.1 Formatter Workflow (`.github/workflows/formatter.yml`)

- Trigger: push to main/master, all PRs
- Run: `ruff format --check .`

### 6.2 CI Build (`.github/workflows/push_build.yml`)

- Trigger: push to main/master, PRs
- Steps: install deps → ruff check → build Docker → test import

### 6.3 Docker Hub Build (`.github/workflows/dockerhub_build.yml`)

- Trigger: push to master, version tags (v*.*.*)
- Multi-platform: linux/amd64, linux/arm64
- Tags: latest, semver, SHA
- Cache: GitHub Actions cache

### 6.4 Release Build (`.github/workflows/release_build.yml`)

- Trigger: version tags (v*.*.*)
- Build locally, save as .tar.gz artifact
- 30-day retention

---

## 7. Security Implementation

### 7.1 Authentication & Authorization

| Role | Client Access | Server Actions | Admin Mgmt | Server Access Control |
|------|---------------|----------------|------------|----------------------|
| Owner | All | All | Yes | Grant/Revoke/List |
| Admin | All | All | Yes | No |
| User | Granted only | Subset | No | No |

### 7.2 Security Controls

1. **Token Encryption**: Fernet (cryptography library) with key from `ENCRYPTION_KEY` env
2. **Input Validation**: All user inputs validated (remark format, CIDR, sizes, etc.)
3. **Rate Limiting**: Per-user, per-action limits (configurable)
4. **Audit Logging**: All mutating operations logged with user, resource, outcome
5. **Confirmation Dialogs**: Required for destructive actions
6. **SQL Injection Prevention**: ORM parameterized queries only
7. **Secret Handling**: No secrets in logs, masked in CLI output
8. **HTTPS Only**: All Hetzner API calls over TLS
9. **Webhook Security**: N/A (bot uses long polling)

### 7.3 Threat Model & Mitigations

| Threat | Mitigation | Severity if Unmitigated |
|--------|------------|------------------------|
| API token theft | Encryption at rest, masked display | FATAL |
| Unauthorized server access | Role + per-server ACL checks | SEVERE |
| Privilege escalation | Strict role enforcement, no self-promotion | SEVERE |
| IDOR/BOLA | Resource ownership validation on every action | SEVERE |
| Injection attacks | ORM, input validation, parameterized queries | FATAL |
| Replay attacks | Telegram's built-in callback query ID tracking | DANGEROUS |
| Brute force | Rate limiting on auth-sensitive actions | DANGEROUS |
| Info leakage | No sensitive data in logs/errors | WARNING |

---

## 8. Hetzner API Integration

### 8.1 Client Design

```python
class HetznerClient:
    def __init__(self, api_token: str, base_url: str = "https://api.hetzner.cloud/v1")
    
    # Servers
    async def list_servers(self) -> List[Server]
    async def get_server(self, server_id: int) -> Server
    async def create_server(self, create_request: ServerCreateRequest) -> ServerCreateResponse
    async def delete_server(self, server_id: int) -> None
    async def power_on(self, server_id: int) -> Action
    async def power_off(self, server_id: int) -> Action
    async def reboot(self, server_id: int) -> Action
    async def reset(self, server_id: int) -> Action
    async def rebuild(self, server_id: int, image: str) -> Action
    async def reset_password(self, server_id: int) -> PasswordResetResponse
    async def upgrade(self, server_id: int, server_type: str) -> Action
    async def create_snapshot(self, server_id: int, description: str) -> Snapshot
    async def assign_ip(self, server_id: int, ip_id: int, ip_type: str) -> Action
    async def unassign_ip(self, server_id: int, ip_type: str) -> Action
    async def get_traffic(self, server_id: int) -> Traffic
    async def get_console(self, server_id: int) -> ConsoleResponse
    
    # ... similar for all resource types
```

### 8.2 Error Handling

- Map Hetzner API errors to domain exceptions
- Retry logic with exponential backoff for transient errors
- Rate limit handling (respect Hetzner's limits)
- Action polling for async operations

---

## 9. Background Services

### 9.1 Traffic Monitor

```python
class TrafficMonitor:
    async def check_all_clients(self):
        for client in active_clients:
            for server in client.servers:
                traffic = await hetzner.get_traffic(server.id)
                if traffic.outgoing_gb / traffic.included_gb * 100 >= threshold:
                    await notify_admins(client, server, traffic)
```

- Runs every 15 minutes (configurable)
- Sends alerts to all admins (env + bot-managed)
- Respects `TRAFFIC_MONITOR_ENABLED` env var

---

## 10. Implementation Phases

### Phase 1: Foundation (Week 1-2)
- [ ] Project setup: pyproject.toml, Docker, docker-compose
- [ ] Database models + Alembic initial migration
- [ ] Config management (Pydantic Settings)
- [ ] Encryption utility for API tokens
- [ ] Hetzner API client (core + server endpoints)
- [ ] Basic bot structure with aiogram
- [ ] Auth middleware + user/client resolution
- [ ] Message tracking middleware

### Phase 2: Core Bot - Clients & Servers (Week 2-3)
- [ ] `/start` handler + home screen keyboard
- [ ] Client menu + settings (create, edit, delete, test token)
- [ ] Server list + info display
- [ ] Server creation wizard (5 steps)
- [ ] Server actions (power, reboot, reset, rebuild, password, delete)
- [ ] Server access control (grant/list/revoke) - owner only
- [ ] Confirmation dialogs for destructive actions

### Phase 3: Resource Management (Week 3-4)
- [ ] Snapshots (list, info, create, delete)
- [ ] Primary IPs (list, info, create, assign/unassign, delete, DNS)
- [ ] Floating IPs (list, info, create, assign/unassign, DNS, delete)
- [ ] Volumes (list, info, create, resize, attach/detach, delete)
- [ ] Networks (list, info, create, subnets, routes, delete)
- [ ] Firewalls (list, info, create, apply/remove servers, delete)
- [ ] Load Balancers (list, info, create, targets, delete)
- [ ] SSH Keys (list, info, create, delete)
- [ ] Certificates (list, info, create uploaded/managed, delete)
- [ ] Placement Groups (list, info, create, delete)

### Phase 4: Admin & Monitoring (Week 4-5)
- [ ] Admin management (list, add, remove)
- [ ] Traffic monitoring background task
- [ ] Admin notifications
- [ ] Audit logging integration

### Phase 5: CLI Tool (Week 5-6)
- [ ] CLI entry point + shared output formatting
- [ ] Bot management commands (status, update, restart, stop, start, logs, install, uninstall)
- [ ] All resource commands per spec
- [ ] Client management commands

### Phase 6: Deployment & Polish (Week 6-7)
- [ ] Installation scripts (install.sh, update.sh, uninstall.sh)
- [ ] Docker health checks
- [ ] CI/CD pipelines
- [ ] Comprehensive testing
- [ ] Documentation (README, CLI help)

### Phase 7: Security Hardening & Review (Week 7-8)
- [ ] Security audit (self-review per production-grade guidelines)
- [ ] Penetration testing mindset review
- [ ] Load testing
- [ ] Final documentation

---

## 11. Testing Strategy

### 11.1 Test Categories

| Category | Coverage | Tools |
|----------|----------|-------|
| Unit Tests | >80% business logic | pytest, pytest-mock |
| Integration Tests | DB, Hetzner API (mocked) | pytest, testcontainers |
| CLI Tests | Command output, args | pytest, typer testing utils |
| Bot Handler Tests | FSM transitions, keyboards | pytest, aiogram test utils |
| Security Tests | AuthZ, input validation | Custom |
| E2E Tests | Full flows (staging) | Manual + scripted |

### 11.2 Critical Test Scenarios

- User role enforcement across all actions
- Server access control (grant/revoke)
- Multi-step flow state persistence
- Token encryption/decryption
- Confirmation dialog flow
- Message cleanup on navigation
- Rate limiting
- Audit log completeness
- Hetzner API error mapping
- CLI output formatting

---

## 12. Open Questions & Decisions Needed

### 12.1 Technical Decisions

1. **Redis for FSM storage?** Spec doesn't mention it, but aiogram 3.x recommends Redis for production. Should we add Redis container?
2. **Database connection pooling?** SQLAlchemy async pool settings needed for production.
3. **Hetzner API rate limits?** Need to implement respectful rate limiting (1 req/sec per token?).
4. **Action polling interval?** For async operations (create, power, etc.), what polling frequency?
5. **Timezone handling?** All timestamps UTC per Dockerfile, but display in user's local time?

### 12.2 Feature Clarifications

1. **Server console access** — CLI has `console` command. Bot doesn't mention it. Include in bot?
2. **Firewall rules management** — Spec only shows apply/remove servers. Need rule CRUD?
3. **Load balancer target types** — Only servers? Or also IPs/labels?
4. **Certificate renewal** — For managed certs, auto-renewal handling?
5. **Placement group types** — Only "spread" per spec. Future-proof for other types?
6. **Bulk operations** — Any need for bulk server actions?

### 12.3 Operational Decisions

1. **Backup strategy** — pg_dump in update script. Point-in-time recovery needed?
2. **Log retention** — How long keep audit logs? Application logs?
3. **Monitoring** — Health check endpoint for external monitoring?
4. **Horizontal scaling** — Host networking prevents multiple bot replicas. Acceptable?

---

## 13. Risk Assessment

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| Hetzner API changes | Medium | High | Version pinning, integration tests, monitoring |
| Telegram API limits | Low | Medium | Rate limiting, exponential backoff |
| Token encryption key loss | Low | FATAL | Document key rotation, backup strategy |
| Database corruption | Low | HIGH | Regular backups, replication (future) |
| Bot token compromise | Low | FATAL | Revoke via BotFather, short-lived tokens |
| User error (delete prod) | High | HIGH | Confirmation dialogs, audit trail, no force flags |

---

## 14. Success Criteria

- [ ] All spec features implemented and tested
- [ ] Zero FATAL/SEVERE security findings in self-audit
- [ ] CLI and bot parity for all resource operations
- [ ] Installation script works on clean Ubuntu 22.04+
- [ ] Update script rolls back on failure
- [ ] All CI pipelines pass
- [ ] Docker image < 500MB
- [ ] Bot responds < 2s for typical operations
- [ ] Handles 100+ concurrent users without degradation

---

## 15. Next Steps

1. **Review this plan** — Confirm architecture, tech stack, phases
2. **Decide on open questions** — Especially Redis, rate limits, console access
3. **Initialize repository** — Set up pyproject.toml, Docker, CI
4. **Begin Phase 1** — Foundation implementation

---

*This plan follows production-grade engineering principles: security-first, correctness over speed, explicit error handling, auditability, and operational simplicity.*