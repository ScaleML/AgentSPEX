#!/bin/bash
# build-ova.sh — Build the AI Scientists VirtualBox VM image (.ova)
#
# Prerequisites:
#   - Packer (https://developer.hashicorp.com/packer/install)
#   - VirtualBox (https://www.virtualbox.org/wiki/Downloads)
#
# Usage:
#   ./build-ova.sh [version]
#
# Examples:
#   ./build-ova.sh           # builds v1.0.0
#   ./build-ova.sh 1.2.0     # builds v1.2.0
set -euo pipefail

VERSION="${1:-1.0.0}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PACKER_DIR="$SCRIPT_DIR/packer"
OUTPUT_DIR="$SCRIPT_DIR/output"

echo "============================================"
echo " AI Scientists VM Builder"
echo " Version: ${VERSION}"
echo "============================================"
echo ""

# Check prerequisites
if ! command -v packer &>/dev/null; then
    echo "ERROR: Packer is not installed."
    echo "Install it from: https://developer.hashicorp.com/packer/install"
    exit 1
fi

if ! command -v VBoxManage &>/dev/null; then
    echo "ERROR: VirtualBox is not installed."
    echo "Install it from: https://www.virtualbox.org/wiki/Downloads"
    exit 1
fi

echo "Packer version:     $(packer version)"
echo "VirtualBox version: $(VBoxManage --version)"
echo "Output directory:   ${OUTPUT_DIR}"
echo ""

# Initialize Packer plugins
echo "[1/3] Initializing Packer plugins..."
cd "$PACKER_DIR"
packer init .

# Validate template
echo "[2/3] Validating Packer template..."
packer validate \
    -var "version=${VERSION}" \
    -var "output_directory=${OUTPUT_DIR}" \
    .

# Build the VM
echo "[3/3] Building VM image (this will take 30-60 minutes)..."
echo ""
packer build \
    -var "version=${VERSION}" \
    -var "output_directory=${OUTPUT_DIR}" \
    .

echo ""
echo "============================================"
echo " Build complete!"
echo "============================================"
echo ""
echo "OVA file:"
ls -lh "${OUTPUT_DIR}/"*.ova
echo ""
echo "To test: import the .ova into VirtualBox, start the VM,"
echo "then open http://localhost:5001 in your browser."
