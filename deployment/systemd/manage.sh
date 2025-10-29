#!/bin/bash
# AI-CHAT systemd service management helper
set -euo pipefail

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Service names
SERVICES=("backend.service" "ui.service")

# Functions
show_help() {
    echo -e "${BLUE}AI-CHAT Service Manager${NC}"
    echo "========================="
    echo ""
    echo "Usage: $0 [command]"
    echo ""
    echo "Commands:"
    echo "  start     - Start all services"
    echo "  stop      - Stop all services"
    echo "  restart   - Restart all services"
    echo "  status    - Show service status"
    echo "  logs      - Follow service logs"
    echo "  health    - Check service health"
    echo "  backup    - Backup databases and configs"
    echo "  update    - Update application code"
    echo "  help      - Show this help message"
    echo ""
}

start_services() {
    echo -e "${GREEN}Starting AI-CHAT services...${NC}"
    sudo systemctl start backend.service
    sleep 3
    sudo systemctl start ui.service
    sleep 3
    check_health
}

stop_services() {
    echo -e "${YELLOW}Stopping AI-CHAT services...${NC}"
    sudo systemctl stop ui.service
    sudo systemctl stop backend.service
    echo -e "${GREEN}✅ Services stopped${NC}"
}

restart_services() {
    echo -e "${YELLOW}Restarting AI-CHAT services...${NC}"
    stop_services
    sleep 2
    start_services
}

show_status() {
    echo -e "${BLUE}Service Status:${NC}"
    echo "==============="
    for service in "${SERVICES[@]}"; do
        echo -e "\n${YELLOW}$service:${NC}"
        sudo systemctl status "$service" --no-pager | head -n 10
    done
}

follow_logs() {
    echo -e "${BLUE}Following service logs (Ctrl+C to exit)...${NC}"
    sudo journalctl -u backend.service -u ui.service -f
}

check_health() {
    echo -e "${BLUE}Health Check:${NC}"
    echo "============="

    # Check backend
    echo -n "Backend (7860): "
    if curl -s -f http://localhost:7860/_healthz > /dev/null 2>&1; then
        echo -e "${GREEN}✅ Healthy${NC}"
    else
        echo -e "${RED}❌ Unhealthy${NC}"
    fi

    # Check UI
    echo -n "UI (8501): "
    if curl -s -f http://localhost:8501 > /dev/null 2>&1; then
        echo -e "${GREEN}✅ Healthy${NC}"
    else
        echo -e "${RED}❌ Unhealthy${NC}"
    fi

    # Check ports
    echo -e "\n${BLUE}Port Status:${NC}"
    sudo lsof -i :7860 2>/dev/null | grep LISTEN || echo "Port 7860: Not listening"
    sudo lsof -i :8501 2>/dev/null | grep LISTEN || echo "Port 8501: Not listening"
}

backup_data() {
    BACKUP_DIR="/backup/ai-chat"
    TIMESTAMP=$(date +%Y%m%d_%H%M%S)
    BACKUP_FILE="$BACKUP_DIR/backup_$TIMESTAMP.tar.gz"

    echo -e "${BLUE}Creating backup...${NC}"

    # Create backup directory
    sudo mkdir -p "$BACKUP_DIR"

    # Stop services for consistency
    echo -e "${YELLOW}Stopping services for backup...${NC}"
    stop_services

    # Create backup
    sudo tar -czf "$BACKUP_FILE" \
        /opt/ai-chat/*.db \
        /opt/ai-chat/.env \
        /opt/ai-chat/config.py \
        /opt/ai-chat/logs/ 2>/dev/null || true

    # Set permissions
    sudo chmod 600 "$BACKUP_FILE"

    # Restart services
    echo -e "${GREEN}Starting services...${NC}"
    start_services

    echo -e "${GREEN}✅ Backup created: $BACKUP_FILE${NC}"

    # Cleanup old backups (keep last 7)
    echo -e "${YELLOW}Cleaning old backups...${NC}"
    ls -t "$BACKUP_DIR"/backup_*.tar.gz 2>/dev/null | tail -n +8 | xargs -r sudo rm
}

update_app() {
    echo -e "${BLUE}Updating AI-CHAT application...${NC}"

    # Backup first
    echo -e "${YELLOW}Creating backup before update...${NC}"
    backup_data

    # Update code
    cd /opt/ai-chat
    echo -e "${YELLOW}Pulling latest code...${NC}"
    sudo -u ai-chat git pull

    echo -e "${YELLOW}Updating dependencies...${NC}"
    sudo -u ai-chat /opt/ai-chat/.venv/bin/pip install -r requirements.txt

    # Restart services
    echo -e "${YELLOW}Restarting services...${NC}"
    restart_services

    echo -e "${GREEN}✅ Update complete${NC}"
}

# Main logic
case "${1:-help}" in
    start)
        start_services
        ;;
    stop)
        stop_services
        ;;
    restart)
        restart_services
        ;;
    status)
        show_status
        ;;
    logs)
        follow_logs
        ;;
    health)
        check_health
        ;;
    backup)
        backup_data
        ;;
    update)
        update_app
        ;;
    help|*)
        show_help
        ;;
esac