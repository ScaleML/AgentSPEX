#!/bin/bash
# 02-docker.sh — Install Docker Engine
set -euxo pipefail

export DEBIAN_FRONTEND=noninteractive

# Add Docker official GPG key
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
    | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
chmod a+r /etc/apt/keyrings/docker.gpg

# Add Docker repository
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
    https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" \
    > /etc/apt/sources.list.d/docker.list

apt-get update
apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# Add aiscientist user to docker group (no nested virt needed — Docker uses
# kernel cgroups/namespaces, runs natively inside VirtualBox)
usermod -aG docker aiscientist

# Enable Docker to start on boot
systemctl enable docker
