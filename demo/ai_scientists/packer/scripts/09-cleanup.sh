#!/bin/bash
# 09-cleanup.sh — Clean caches and reduce image size
set -euxo pipefail

export DEBIAN_FRONTEND=noninteractive

# Clean apt caches
apt-get clean
apt-get autoremove -y
rm -rf /var/lib/apt/lists/*

# Clean conda caches
/home/aiscientist/miniconda3/bin/conda clean -a -y
rm -rf /home/aiscientist/.cache/pip

# Clean Docker build cache (keep the built image)
docker builder prune -f

# Remove temporary files
rm -rf /tmp/packer-files
rm -rf /tmp/*

# Clear shell history
: > /home/aiscientist/.bash_history

# Zero-fill free space for better VMDK compression
dd if=/dev/zero of=/EMPTY bs=1M 2>/dev/null || true
rm -f /EMPTY
sync
