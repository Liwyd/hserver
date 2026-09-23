#!/bin/bash
set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

INSTALL_DIR="/opt/servermanagerbot"
BACKUP_DIR="/opt/servermanagerbot_backups"

log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

rollback() {
    log_error "Update failed. Rolling back..."
    if [[ -f "$BACKUP_DIR/latest/.env" ]]; then
        cp "$BACKUP_DIR/latest/.env" "$INSTALL_DIR/.env"
    fi
    if [[ -f "$BACKUP_DIR/latest/db_backup.sql" ]]; then
        log_info "Restoring database..."
        docker compose -f "$INSTALL_DIR/docker/docker-compose.yml" exec -T postgres psql -U smbuser -d servermanagerbot < "$BACKUP_DIR/latest/db_backup.sql"
    fi
    docker compose -f "$INSTALL_DIR/docker/docker-compose.yml" up -d
    log_info "Rollback complete"
    exit 1
}

trap rollback ERR

main() {
    log_info "Starting update..."

    TIMESTAMP=$(date +%Y%m%d_%H%M%S)
    BACKUP_PATH="$BACKUP_DIR/$TIMESTAMP"
    mkdir -p "$BACKUP_PATH"
    ln -sfn "$BACKUP_PATH" "$BACKUP_DIR/latest"

    log_info "Backing up .env..."
    cp "$INSTALL_DIR/.env" "$BACKUP_PATH/.env"

    log_info "Backing up database..."
    docker compose -f "$INSTALL_DIR/docker/docker-compose.yml" exec -T postgres pg_dump -U smbuser servermanagerbot > "$BACKUP_PATH/db_backup.sql"

    log_info "Stopping bot..."
    docker compose -f "$INSTALL_DIR/docker/docker-compose.yml" stop servermanagerbot

    log_info "Pulling latest code..."
    cd "$INSTALL_DIR"
    git pull || {
        log_warn "Git pull failed, re-cloning..."
        cd ..
        rm -rf "$INSTALL_DIR"
        git clone https://github.com/yourusername/hserver.git "$INSTALL_DIR"
        cp "$BACKUP_PATH/.env" "$INSTALL_DIR/.env"
    }

    log_info "Rebuilding Docker image..."
    docker compose -f "$INSTALL_DIR/docker/docker-compose.yml" build

    log_info "Starting database and running migrations..."
    docker compose -f "$INSTALL_DIR/docker/docker-compose.yml" up -d postgres
    sleep 5
    docker compose -f "$INSTALL_DIR/docker/docker-compose.yml" exec -T servermanagerbot uv run alembic upgrade head

    log_info "Starting all services..."
    docker compose -f "$INSTALL_DIR/docker/docker-compose.yml" up -d

    log_info "Verifying health..."
    sleep 10
    if ! docker compose -f "$INSTALL_DIR/docker/docker-compose.yml" exec -T servermanagerbot python -c "import bot.config; print('OK')"; then
        log_error "Health check failed"
        exit 1
    fi

    log_info "Cleaning up old Docker images..."
    docker image prune -f --filter "until=24h"

    log_info "Keeping last 5 backups..."
    ls -dt "$BACKUP_DIR"/*/ | tail -n +6 | xargs rm -rf

    log_info "Update complete!"
}

main "$@"