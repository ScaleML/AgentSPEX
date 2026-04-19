#!/bin/bash
# 07-services.sh — Install and enable systemd service units
set -euxo pipefail

# Copy service files from Packer upload directory
cp /tmp/packer-files/sandbox-vm.service /etc/systemd/system/
cp /tmp/packer-files/ai-scientists-web.service /etc/systemd/system/
cp /tmp/packer-files/ai-scientists-setup.service /etc/systemd/system/

# Set permissions
chmod 644 /etc/systemd/system/sandbox-vm.service
chmod 644 /etc/systemd/system/ai-scientists-web.service
chmod 644 /etc/systemd/system/ai-scientists-setup.service

# Reload systemd
systemctl daemon-reload

# Enable all services to start on boot
# Startup order is handled by After=/Requires= in the unit files:
#   docker.service -> sandbox-vm.service -> ai-scientists-web.service
#   ai-scientists-setup.service runs only on first boot (ConditionPathExists)
systemctl enable sandbox-vm.service
systemctl enable ai-scientists-web.service
systemctl enable ai-scientists-setup.service

# Add MOTD banner for SSH users
cat > /etc/motd << 'MOTD'
============================================
 AI Scientists Web UI VM
============================================
 Web UI:    http://localhost:5001  (from host)
 VNC:       http://localhost:6080  (from host)
 SSH:       ssh -p 2222 aiscientist@localhost

 Configure API keys: ~/configure-keys.sh
 Service status:     sudo systemctl status ai-scientists-web
 View logs:          journalctl -u ai-scientists-web -f
============================================
MOTD
