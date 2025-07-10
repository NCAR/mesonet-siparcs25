#!/bin/bash
# LoRa Gateway Installer and Runner

set -euo pipefail

# Constants
PYTHON_SCRIPT="pi_lora.py"
VENV_DIR="/home/ncar/mesonet-siparcs25/edge-servers/.venv"  # Full absolute path
REQUIREMENTS="requirements.txt"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m'

# Only run setup if virtualenv doesn't exist
if [ ! -d "$VENV_DIR" ]; then
    echo -e "${GREEN}=== Initial Setup ==="
    echo -e "[1/4] Enabling I2C/SPI...${NC}"
    sudo raspi-config nonint do_i2c 0 || true
    sudo raspi-config nonint do_spi 0 || true

    echo -e "${GREEN}[2/4] Installing system packages...${NC}"
    sudo apt update && sudo apt install -y \
        python3-venv \
        python3-dev \
        i2c-tools \
        libatlas-base-dev

    echo -e "${GREEN}[3/4] Creating virtual environment...${NC}"
    python3 -m venv "$VENV_DIR"
fi

# Always activate environment
source "$VENV_DIR/bin/activate"

# Install/update dependencies
echo -e "${GREEN}[4/4] Ensuring dependencies...${NC}"
pip install --upgrade pip
pip install -r "$REQUIREMENTS"

# Run application
echo -e "${GREEN}=== Starting LoRa Gateway ===${NC}"
exec python3 "$PYTHON_SCRIPT"