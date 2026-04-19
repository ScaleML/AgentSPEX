#!/bin/bash
# configure-keys.sh — CLI tool to configure API keys
# Usage: ~/configure-keys.sh
set -euo pipefail

VM_ENV="$HOME/controllable-sandbox/config/vm.env"

echo "============================================"
echo " AI Scientists — API Key Configuration"
echo "============================================"
echo ""

# Read OPENAI_API_KEY
read -rp "Enter OPENAI_API_KEY (required): " openai_key
if [ -z "$openai_key" ]; then
    echo "ERROR: OPENAI_API_KEY is required."
    exit 1
fi

# Read FIRECRAWL_API_KEY
read -rp "Enter FIRECRAWL_API_KEY (optional, Enter to skip): " firecrawl_key

# Update vm.env
sed -i "s|^OPENAI_API_KEY=.*|OPENAI_API_KEY=${openai_key}|" "$VM_ENV"
if [ -n "$firecrawl_key" ]; then
    sed -i "s|^FIRECRAWL_API_KEY=.*|FIRECRAWL_API_KEY=${firecrawl_key}|" "$VM_ENV"
fi

echo ""
echo "API keys saved to $VM_ENV"

# Mark setup as complete (disables the setup portal on next boot)
touch "$HOME/.setup-complete"

# Restart services to pick up new keys
echo "Restarting services..."
sudo systemctl stop ai-scientists-setup.service 2>/dev/null || true
sudo systemctl restart sandbox-vm.service
sudo systemctl restart ai-scientists-web.service

echo ""
echo "Done! Access the Web UI at http://localhost:5001 (from host machine)"
