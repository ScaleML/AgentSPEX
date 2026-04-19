#!/bin/bash
# 06-docker-image.sh — Pre-build the sandbox Docker image
# This saves users ~15 min of build time on first boot
set -euxo pipefail

PROJECT_DIR="/home/aiscientist/controllable-sandbox"

cd "$PROJECT_DIR"

# Build the sandbox Docker image (uses config/Dockerfile)
docker build -t virtual-sandbox:latest -f config/Dockerfile .

echo "Docker image built successfully:"
docker images virtual-sandbox:latest
