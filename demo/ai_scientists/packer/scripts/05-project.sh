#!/bin/bash
# 05-project.sh — Set up the project repository and configuration
set -euxo pipefail

PROJECT_DIR="/home/exouser/controllable-sandbox"
TARGET_DIR="/home/aiscientist/controllable-sandbox"

# If running inside Packer, copy the project from the build host.
# If the project is already at TARGET_DIR (e.g. pre-cloned), skip the copy.
if [ ! -d "$TARGET_DIR" ]; then
    # Clone from git (replace with your actual repo URL)
    # git clone https://github.com/<org>/controllable-sandbox.git "$TARGET_DIR"

    # Or copy from the current server
    if [ -d "$PROJECT_DIR" ]; then
        cp -a "$PROJECT_DIR" "$TARGET_DIR"
    else
        echo "ERROR: Project source not found at $PROJECT_DIR or $TARGET_DIR"
        exit 1
    fi
fi

# Ensure correct ownership
chown -R aiscientist:aiscientist "$TARGET_DIR"

# Create vm.env with empty API keys (user fills in via setup portal)
cat > "$TARGET_DIR/config/vm.env" << 'VMENV'
## set user password to access VNC and user account
USER_PASSWORD=agent2k

VM_HOSTNAME=sandbox

## x11
DISPLAY=:100
SCREEN_SIZE=1680x1050x24

# the following x11 port is for vm internal use, and will not be exposed
RDP_PORT=5900

## VNC / noVNC remote desktop port which will be exposed
VNC_PORT=6080

## playwright browser control
CDP_PORT=9222
BROWSER_NAV_ON_FETCH=True
BROWSER_NAV_OPEN_TAB=False
URL_DOWNLOAD_DIR=browser/url_downloads

# controllable TMUX session
TMUX_SESSION=vs-control

## MCP server
MCP_TRANSPORT=streamable-http
MCP_PORT=7002
MCP_BASEPATH=/mcp
MCP_HOST=0.0.0.0

# VM_WORKSPACE mapped to HOST_WORKSPACE
VM_WORKSPACE=/workspace

#### Tool specific env variables (filled by setup portal or configure-keys.sh)
OPENAI_API_KEY=
GOOGLE_CSE_ID=
GOOGLE_CSE_API_KEY=
FIRECRAWL_API_KEY=
VMENV

# Create host.env
cat > "$TARGET_DIR/config/host.env" << 'HOSTENV'
# local workspace shared with docker's VM_WORKSPACE
HOST_WORKSPACE=$(pwd)/workspace

# Global persistent backup location for workspace files
WORKSPACE_PERSISTENT=$(pwd)/workspace_persistent
HOSTENV

# Create necessary runtime directories
sudo -u aiscientist mkdir -p "$TARGET_DIR/workspace"
sudo -u aiscientist mkdir -p "$TARGET_DIR/workspace_persistent"
sudo -u aiscientist mkdir -p "$TARGET_DIR/outputs"
