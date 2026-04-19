#!/bin/bash
# 08-setup-portal.sh — Install the first-boot API key setup portal
set -euxo pipefail

SETUP_DIR="/home/aiscientist/setup-portal"

# Create setup portal directory
mkdir -p "$SETUP_DIR/templates"

# Copy setup portal files from Packer upload directory
cp /tmp/packer-files/setup_server.py "$SETUP_DIR/"
cp /tmp/packer-files/setup_template.html "$SETUP_DIR/templates/index.html"

# Copy CLI fallback script
cp /tmp/packer-files/configure-keys.sh /home/aiscientist/configure-keys.sh
chmod +x /home/aiscientist/configure-keys.sh

# Fix ownership
chown -R aiscientist:aiscientist "$SETUP_DIR"
chown aiscientist:aiscientist /home/aiscientist/configure-keys.sh
