#!/bin/bash
# Installation script for Smart Health Monitoring Mirror
# For Raspberry Pi OS (Debian-based)

set -e

echo "========================================"
echo "Smart Health Mirror - Installation"
echo "========================================"

# Check if running on Raspberry Pi
if [ ! -f /proc/device-tree/model ] || ! grep -q "Raspberry Pi" /proc/device-tree/model; then
    echo "WARNING: This script is designed for Raspberry Pi"
    read -p "Continue anyway? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# Update system
echo "Updating system packages..."
sudo apt-get update

# Install system dependencies
echo "Installing system dependencies..."
sudo apt-get install -y \
    python3 \
    python3-pip \
    python3-dev \
    cmake \
    build-essential \
    libopencv-dev \
    python3-opencv \
    libasound2-dev \
    portaudio19-dev \
    libttspico-utils \
    alsa-utils \
    libzmq3-dev \
    git

# Install Python packages
echo "Installing Python packages..."
pip3 install --upgrade pip
pip3 install -r requirements.txt

# Download models
echo "Downloading AI models..."
./scripts/download_models.sh

# Create log directory
mkdir -p logs

# Set permissions
chmod +x main.py
chmod +x scripts/*.sh

echo "========================================"
echo "Installation complete!"
echo "========================================"
echo ""
echo "Next steps:"
echo "1. Configure your Porcupine API key in config.yaml"
echo "2. Test hardware: python3 main.py --test-hardware"
echo "3. Test audio: python3 main.py --test-audio"
echo "4. Run the system: python3 main.py"
echo ""
