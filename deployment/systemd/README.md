# systemd Service Configuration for AI-CHAT

This directory contains systemd service files for production deployment of the AI-CHAT system.

## Files

- `backend.service` - FastAPI RAG backend service (port 7860)
- `ui.service` - Streamlit UI service (port 8501)
- `install.sh` - Automated installation script
- `manage.sh` - Service management helper script

## Installation

### Automated Installation

```bash
cd deployment/systemd
sudo ./install.sh
```

### Manual Installation

1. **Create system user:**
```bash
sudo useradd -r -s /bin/bash -d /opt/ai-chat -m ai-chat
```

2. **Copy application:**
```bash
sudo mkdir -p /opt/ai-chat
sudo cp -r /path/to/ai-chat/* /opt/ai-chat/
sudo chown -R ai-chat:ai-chat /opt/ai-chat
```

3. **Install services:**
```bash
sudo cp *.service /etc/systemd/system/
sudo systemctl daemon-reload
```

4. **Enable services:**
```bash
sudo systemctl enable backend.service ui.service
```

## Service Management

### Start Services
```bash
# Start both services
sudo systemctl start backend.service ui.service

# Or individually
sudo systemctl start backend.service
sudo systemctl start ui.service
```

### Check Status
```bash
sudo systemctl status backend.service
sudo systemctl status ui.service
```

### View Logs
```bash
# Real-time logs
sudo journalctl -u backend.service -f
sudo journalctl -u ui.service -f

# Last 100 lines
sudo journalctl -u backend.service -n 100
sudo journalctl -u ui.service -n 100

# Application logs
tail -f /var/log/ai-chat/*.log
```

### Stop Services
```bash
# Stop both services
sudo systemctl stop ui.service backend.service

# Or individually
sudo systemctl stop ui.service
sudo systemctl stop backend.service
```

### Restart Services
```bash
sudo systemctl restart backend.service ui.service
```

### Disable Services
```bash
sudo systemctl disable backend.service ui.service
```

## Health Checks

Both services include automatic health checks:

- **Backend**: http://localhost:7860/_healthz
- **UI**: http://localhost:8501

Check manually:
```bash
curl http://localhost:7860/_healthz
curl http://localhost:8501
```

## Troubleshooting

### Service Won't Start

1. Check logs:
```bash
sudo journalctl -xe -u backend.service
sudo journalctl -xe -u ui.service
```

2. Verify permissions:
```bash
ls -la /opt/ai-chat
ls -la /var/log/ai-chat
```

3. Check port availability:
```bash
sudo lsof -i :7860
sudo lsof -i :8501
```

### Database Issues

1. Check database files:
```bash
ls -la /opt/ai-chat/*.db
```

2. Verify write permissions:
```bash
sudo -u ai-chat touch /opt/ai-chat/test.txt
```

### Dependency Issues

1. Check Python environment:
```bash
sudo -u ai-chat /opt/ai-chat/.venv/bin/pip list
```

2. Reinstall dependencies:
```bash
sudo -u ai-chat /opt/ai-chat/.venv/bin/pip install -r /opt/ai-chat/requirements.txt
```

## Configuration

### Environment Variables

Edit `/opt/ai-chat/.env`:
```bash
sudo -u ai-chat nano /opt/ai-chat/.env
```

Then restart services:
```bash
sudo systemctl restart backend.service ui.service
```

### Service Configuration

To modify service settings, edit the service files:
```bash
sudo systemctl edit backend.service
sudo systemctl edit ui.service
```

### Resource Limits

Current limits:
- Max open files: 65535
- Max processes: 4096

To adjust, edit service files and add under `[Service]`:
```ini
LimitNOFILE=100000
LimitNPROC=8192
```

## Security

Services run with:
- Dedicated system user (`ai-chat`)
- Private /tmp directory
- No new privileges
- Protected system and home directories
- Write access only to:
  - `/opt/ai-chat/logs`
  - `/opt/ai-chat/*.db`
  - `/var/log/ai-chat`

## Monitoring

### Basic Monitoring
```bash
# CPU and memory usage
systemctl status backend.service ui.service

# Detailed resource usage
systemd-cgtop
```

### Prometheus Integration
Both services expose metrics:
- Backend: http://localhost:7860/metrics
- UI: http://localhost:8501/metrics (if configured)

## Backup

Regular backup script:
```bash
#!/bin/bash
# /etc/cron.daily/backup-ai-chat
tar -czf /backup/ai-chat-$(date +%Y%m%d).tar.gz \
    /opt/ai-chat/*.db \
    /opt/ai-chat/.env \
    /opt/ai-chat/logs
```

## Updates

To update the application:

1. Stop services:
```bash
sudo systemctl stop ui.service backend.service
```

2. Backup current state:
```bash
sudo tar -czf /backup/ai-chat-pre-update.tar.gz /opt/ai-chat
```

3. Update code:
```bash
cd /opt/ai-chat
sudo -u ai-chat git pull
sudo -u ai-chat .venv/bin/pip install -r requirements.txt
```

4. Start services:
```bash
sudo systemctl start backend.service ui.service
```

5. Verify:
```bash
curl http://localhost:7860/_healthz
curl http://localhost:8501
```

## Performance Tuning

### Backend Workers
Edit `backend.service` and adjust:
```ini
ExecStart=/opt/ai-chat/.venv/bin/python -m uvicorn app.api.main:app --workers 4
```

### Memory Limits
Add to service files:
```ini
MemoryMax=2G
MemoryHigh=1500M
```

### CPU Affinity
Pin to specific CPUs:
```ini
CPUAffinity=0-3
```

## License

See main repository for license information.