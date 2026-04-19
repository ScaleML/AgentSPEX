#!/bin/bash
# 01-base-system.sh — System updates and base packages
set -euxo pipefail

export DEBIAN_FRONTEND=noninteractive

apt-get update
apt-get upgrade -y

apt-get install -y \
    build-essential gcc g++ make \
    git curl wget \
    ca-certificates gnupg lsb-release \
    software-properties-common \
    openssh-server \
    htop tmux vim nano \
    jq unzip zip \
    net-tools iproute2

# Set timezone
timedatectl set-timezone UTC
