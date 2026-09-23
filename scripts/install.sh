#!/bin/bash
set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

INSTALL_DIR="/opt/servermanagerbot"
REPO_URL="https://github.com/yourusername/hserver.git"

log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

check_root() {
    if [[ $EUID -ne 0 ]]; then
        log_error "This script must be run as root (use sudo)"
        exit 1
    fi
}

install_docker() {
    if ! command -v docker &> /dev/null; then
        log_info "Installing Docker..."
        curl -fsSL https://get.docker.com | sh
    else
        log_info "Docker already installed"
    fi

    if ! docker compose version &> /dev/null; then
        log_info "Installing Docker Compose plugin..."
        mkdir -p /usr/local/lib/docker/cli-plugins
        curl -SL https://github.com/docker/compose/releases/download/v2.27.0/docker-compose-linux-x86_64 -o /usr/local/lib/docker/cli-plugins/docker-compose
        chmod +x /usr/local/lib/docker/cli-plugins/docker-compose
    else
        log_info "Docker Compose already available"
    fi
}

clone_repo() {
    if [[ -d "$INSTALL_DIR" ]]; then
        log_warn "Directory $INSTALL_DIR exists. Updating..."
        cd "$INSTALL_DIR"
        git pull
    else
        log_info "Cloning repository..."
        git clone "$REPO_URL" "$INSTALL_DIR"
        cd "$INSTALL_DIR"
    fi
}

prompt_config() {
    log_info "Configuration required:"
    read -rp "Telegram Bot Token (from BotFather): " TELEGRAM_API_TOKEN
    read -rp "Admin User IDs (comma-separated): " TELEGRAM_ADMINS_ID

    ENCRYPTION_KEY=$(python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")
    DATABASE_PASSWORD=$(openssl rand -base64 32 | tr -d "=+/" | cut -c1-32)
    POSTGRES_PASSWORD=$(openssl rand -base64 32 | tr -d "=+/" | cut -c1-32)
}

write_env() {
    cat > "$INSTALL_DIR/.env" <<EOF
# Database
DATABASE_USERNAME=smbuser
DATABASE_PASSWORD=$DATABASE_PASSWORD
DATABASE_NAME=servermanagerbot
DATABASE_HOST=localhost
DATABASE_PORT=5432

# PostgreSQL Container
POSTGRES_DB=servermanagerbot
POSTGRES_USER=smbuser
POSTGRES_PASSWORD=$POSTGRES_PASSWORD
PGPORT=5432

# Telegram Bot
TELEGRAM_API_TOKEN=$TELEGRAM_API_TOKEN
TELEGRAM_ADMINS_ID=$TELEGRAM_ADMINS_ID

# Encryption
ENCRYPTION_KEY=$ENCRYPTION_KEY

# Traffic Monitor
TRAFFIC_MONITOR_ENABLED=false
TRAFFIC_MONITOR_ALERT_PERCENT=80
TRAFFIC_MONITOR_INTERVAL_MINUTES=15

# Rate Limiting (Hetzner API)
HETZNER_MAX_REQUESTS_PER_SECOND=1
HETZNER_RATE_LIMIT_BUFFER=5
EOF
    chmod 600 "$INSTALL_DIR/.env"
    log_info "Configuration written to $INSTALL_DIR/.env"
}

build_and_start() {
    cd "$INSTALL_DIR/docker"
    log_info "Building Docker image..."
    docker compose build

    log_info "Starting services..."
    docker compose up -d

    log_info "Waiting for database to be ready..."
    timeout=60
    while ! docker compose exec -T postgres pg_isready -U smbuser -d servermanagerbot &> /dev/null; do
        sleep 2
        timeout=$((timeout - 2))
        if [[ $timeout -le 0 ]]; then
            log_error "Database failed to start in time"
            exit 1
        fi
    done

    log_info "Running database migrations..."
    docker compose exec -T servermanagerbot uv run alembic upgrade head
}

install_cli() {
    log_info "Installing hserver CLI..."
    cat > /usr/local/bin/hserver <<'CLIEOF'
#!/bin/bash
cd /opt/servermanagerbot
exec docker compose exec -T servermanagerbot uv run python -m bot.cli.main "$@"
CLIEOF
    chmod +x /usr/local/bin/hserver
    log_info "CLI installed at /usr/local/bin/hserver"
}

main() {
    check_root
    install_docker
    clone_repo
    prompt_config
    write_env
    build_and_start
    install_cli

    log_info "Installation complete!"
    log_info "Run 'hserver status' to verify"
    log_info "Check logs with 'hserver logs -f'"
}

main "$@"