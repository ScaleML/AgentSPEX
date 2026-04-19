#!/bin/bash
# 03-conda.sh — Install Miniconda + yaml_agent environment with all Python packages
set -euxo pipefail

INSTALL_DIR="/home/aiscientist/miniconda3"
CONDA_ENV="yaml_agent"
PROJECT_DIR="/home/aiscientist/controllable-sandbox"

# Download and install Miniconda (auto-detect architecture: x86_64 or aarch64)
ARCH=$(uname -m)
wget -q "https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-${ARCH}.sh" -O /tmp/miniconda.sh
bash /tmp/miniconda.sh -b -p "$INSTALL_DIR"
rm /tmp/miniconda.sh

# Fix ownership
chown -R aiscientist:aiscientist "$INSTALL_DIR"

# Initialize conda for the user's bash shell
sudo -u aiscientist "$INSTALL_DIR/bin/conda" init bash

# Create yaml_agent environment with Python 3.12
sudo -u aiscientist "$INSTALL_DIR/bin/conda" create -y -n "$CONDA_ENV" python=3.12

# Install CPU-only PyTorch (saves ~1.5 GB vs full CUDA version)
# All LLM inference is via OpenAI API — local GPU is not needed
# On aarch64, the CPU wheel is on the default index; on x86_64, use the CPU-only index
ARCH=$(uname -m)
if [ "$ARCH" = "aarch64" ]; then
    sudo -u aiscientist "$INSTALL_DIR/envs/$CONDA_ENV/bin/pip" install torch==2.8.0
else
    sudo -u aiscientist "$INSTALL_DIR/envs/$CONDA_ENV/bin/pip" install \
        torch==2.8.0 --index-url https://download.pytorch.org/whl/cpu
fi

# Install remaining requirements (skip torch since we installed CPU version)
sudo -u aiscientist "$INSTALL_DIR/envs/$CONDA_ENV/bin/pip" install \
    -r "$PROJECT_DIR/requirements.txt"

# Install the project itself in dev mode
sudo -u aiscientist "$INSTALL_DIR/envs/$CONDA_ENV/bin/pip" install \
    -e "$PROJECT_DIR/"

# Install extra web UI dependencies
sudo -u aiscientist "$INSTALL_DIR/envs/$CONDA_ENV/bin/pip" install \
    flask litellm
