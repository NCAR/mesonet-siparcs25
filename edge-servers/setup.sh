#!/bin/bash
# LoRa Gateway Installer - Runs from inside GitHub repo
# Ensures version-pinned dependencies and launches pi_lora.py

set -euo pipefail  # Strict error handling

# Constants
PYTHON_SCRIPT="pi_lora.py"
VENV_DIR=".venv"  # Local to repo
REQUIREMENTS="requirements.txt"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m' # No Color

echo -e "${GREEN}=== LoRa Gateway Setup ==="
echo -e "Running from GitHub repository${NC}"

# Check for root
if [ "$EUID" -eq 0 ]; then
  echo -e "${RED}Error: Do not run as root. Use regular user.${NC}" >&2
  exit 1
fi

# Enable hardware interfaces (non-interactive)
echo -e "[1/4] Enabling I2C/SPI..."
sudo raspi-config nonint do_i2c 0 || true
sudo raspi-config nonint do_spi 0 || true

# Install system dependencies
echo -e "[2/4] Installing system packages..."
sudo apt update && sudo apt install -y \
  python3-venv \
  python3-dev \
  i2c-tools \
  libatlas-base-dev  # For numpy

# Create virtual environment
echo -e "[3/4] Setting up Python environment..."
python3 -m venv "$VENV_DIR"
source "$VENV_DIR/bin/activate"

# Install pinned dependencies
echo -e "[4/4] Installing Python packages..."
pip install --upgrade pip
pip install -r "$REQUIREMENTS"

# Version verification
echo -e "${GREEN}=== Verifying Versions ==="
python -c "
import pkg_resources
required = {
    'adafruit-circuitpython-rfm9x': '4.1.4',
    'adafruit-circuitpython-ssd1306': '2.12.4',
    'paho-mqtt': '1.6.1',
    'psutil': '5.9.5',
    'numpy': '1.24.4'
}
for pkg, ver in required.items():
    try:
        installed = pkg_resources.get_distribution(pkg.split('-')[0]).version
        assert installed == ver, f'\\033[91m✗ {pkg} (expected {ver}, got {installed})\\033[0m'
        print(f'\\033[92m✓ {pkg: <30} {ver}\\033[0m')
    except Exception as e:
        print(f'\\033[91m✗ Version check failed: {e}\\033[0m')
        raise
" || exit 1

# Launch application
echo -e "${GREEN}=== Starting LoRa Gateway ===${NC}"
exec python "$PYTHON_SCRIPT"  # exec replaces shell process
