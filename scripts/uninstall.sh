#!/bin/bash
set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

INSTALL_DIR="/opt/servermanagerbot"

log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

main() {
    echo -e "${RED}WARNING: This will completely remove the Server Manager Bot!${NC}"
    echo "All data including database, configuration, and backups will be deleted."
    echo
    read -rp "Type 'DELETE' to confirm: " CONFIRM

    if [[ "$CONFIRM" != "DELETE" ]]; then
        log_info "Uninstall cancelled"
        exit 0
    fi

    log_info "Stopping and removing containers..."
    if [[ -f "$INSTALL_DIR/docker/docker-compose.yml" ]]; then
        docker compose -f "$INSTALL_DIR/docker/docker-compose.yml" down -v
    fi

    log_info "Removing Docker images..."
    docker images --format "{{.Repository}}:{{.Tag}}" | grep -E "servermanagerbot|hserver" | xargs -r docker rmi -f

    log_info "Removing installation directory..."
    rm -rf "$INSTALL_DIR"

    log_info "Removing CLI..."
    rm -f /usr/local/bin/hserver

    log_info "Removing backups..."
    rm -rf /opt/servermanagerbot_backups

    log_info "Uninstall complete!"
}

main "$@"