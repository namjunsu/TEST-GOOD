#!/bin/bash
# systemd service installation script for AI-CHAT
set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
APP_USER="ai-chat"
APP_DIR="/opt/ai-chat"
LOG_DIR="/var/log/ai-chat"
SERVICE_DIR="/etc/systemd/system"

echo -e "${GREEN}AI-CHAT systemd Service Installer${NC}"
echo "====================================="

# Check if running as root
if [[ $EUID -ne 0 ]]; then
   echo -e "${RED}This script must be run as root (use sudo)${NC}"
   exit 1
fi

# Step 1: Create system user
echo -e "\n${YELLOW}Step 1: Creating system user${NC}"
if ! id -u "$APP_USER" &>/dev/null; then
    useradd -r -s /bin/bash -d "$APP_DIR" -m "$APP_USER"
    echo -e "${GREEN}✅ User $APP_USER created${NC}"
else
    echo -e "${GREEN}✅ User $APP_USER already exists${NC}"
fi

# Step 2: Create directories
echo -e "\n${YELLOW}Step 2: Creating directories${NC}"
mkdir -p "$APP_DIR"
mkdir -p "$LOG_DIR"
echo -e "${GREEN}✅ Directories created${NC}"

# Step 3: Copy application files
echo -e "\n${YELLOW}Step 3: Copying application files${NC}"
if [ -d "../../.git" ]; then
    # We're in deployment/systemd, copy from repo root
    rsync -av --exclude='.git' --exclude='__pycache__' --exclude='.venv' \
          --exclude='logs' --exclude='*.pyc' \
          ../../ "$APP_DIR/"
    echo -e "${GREEN}✅ Application files copied${NC}"
else
    echo -e "${RED}❌ Not in correct directory. Run from deployment/systemd/${NC}"
    exit 1
fi

# Step 4: Setup Python virtual environment
echo -e "\n${YELLOW}Step 4: Setting up Python environment${NC}"
cd "$APP_DIR"
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
echo -e "${GREEN}✅ Python environment ready${NC}"

# Step 5: Set permissions
echo -e "\n${YELLOW}Step 5: Setting permissions${NC}"
chown -R "$APP_USER:$APP_USER" "$APP_DIR"
chown -R "$APP_USER:$APP_USER" "$LOG_DIR"
chmod 755 "$APP_DIR"
chmod 755 "$LOG_DIR"
echo -e "${GREEN}✅ Permissions set${NC}"

# Step 6: Copy service files
echo -e "\n${YELLOW}Step 6: Installing service files${NC}"
cp backend.service "$SERVICE_DIR/"
cp ui.service "$SERVICE_DIR/"
echo -e "${GREEN}✅ Service files installed${NC}"

# Step 7: Reload systemd
echo -e "\n${YELLOW}Step 7: Reloading systemd${NC}"
systemctl daemon-reload
echo -e "${GREEN}✅ systemd reloaded${NC}"

# Step 8: Enable services
echo -e "\n${YELLOW}Step 8: Enabling services${NC}"
systemctl enable backend.service
systemctl enable ui.service
echo -e "${GREEN}✅ Services enabled${NC}"

# Installation complete
echo -e "\n${GREEN}================================${NC}"
echo -e "${GREEN}Installation Complete!${NC}"
echo -e "${GREEN}================================${NC}"

echo -e "\nTo start services:"
echo "  sudo systemctl start backend.service"
echo "  sudo systemctl start ui.service"

echo -e "\nTo check status:"
echo "  sudo systemctl status backend.service"
echo "  sudo systemctl status ui.service"

echo -e "\nTo view logs:"
echo "  sudo journalctl -u backend.service -f"
echo "  sudo journalctl -u ui.service -f"
echo "  tail -f $LOG_DIR/*.log"

echo -e "\nTo stop services:"
echo "  sudo systemctl stop ui.service"
echo "  sudo systemctl stop backend.service"