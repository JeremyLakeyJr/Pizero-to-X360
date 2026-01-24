#!/bin/bash
#
# Installation script for Xbox 360 Controller Emulator
#
# This script installs all dependencies and configures the system
# for running the Xbox 360 controller emulator on a Raspberry Pi Zero.
#
# Usage: sudo ./install.sh
#

set -e

echo "====================================="
echo "Xbox 360 Controller Emulator Installer"
echo "====================================="
echo ""

# Check for root
if [ "$(id -u)" -ne 0 ]; then
    echo "Error: This script must be run as root"
    echo "Usage: sudo ./install.sh"
    exit 1
fi

# Check for Raspberry Pi
if [ ! -f /proc/device-tree/model ]; then
    echo "Warning: This doesn't appear to be a Raspberry Pi"
    read -p "Continue anyway? [y/N] " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
else
    MODEL=$(cat /proc/device-tree/model)
    echo "Detected: ${MODEL}"
    if [[ ! "${MODEL}" =~ "Zero" ]]; then
        echo "Warning: This is designed for Raspberry Pi Zero"
        echo "Other models may work but are not tested."
    fi
fi

echo ""
echo "Step 1: Updating system packages..."
apt-get update

echo ""
echo "Step 2: Installing dependencies..."
apt-get install -y \
    python3 \
    python3-pip \
    python3-dev \
    git

echo ""
echo "Step 3: Installing Python packages..."
pip3 install evdev pyusb

echo ""
echo "Step 4: Configuring boot options..."

# Check /boot/config.txt for dwc2 overlay
CONFIG_TXT="/boot/config.txt"
if [ -f "/boot/firmware/config.txt" ]; then
    CONFIG_TXT="/boot/firmware/config.txt"
fi

if ! grep -q "^dtoverlay=dwc2" "${CONFIG_TXT}" 2>/dev/null; then
    echo "Adding dwc2 overlay to ${CONFIG_TXT}..."
    echo "" >> "${CONFIG_TXT}"
    echo "# Enable USB gadget mode (dwc2)" >> "${CONFIG_TXT}"
    echo "dtoverlay=dwc2" >> "${CONFIG_TXT}"
else
    echo "dwc2 overlay already configured in ${CONFIG_TXT}"
fi

echo ""
echo "Step 5: Configuring kernel modules to load at boot..."

# Add modules to /etc/modules for auto-loading at boot
# This is the safe method - no modification of cmdline.txt needed
if ! grep -q "^dwc2" /etc/modules 2>/dev/null; then
    echo "dwc2" >> /etc/modules
    echo "Added dwc2 to /etc/modules"
fi
if ! grep -q "^libcomposite" /etc/modules 2>/dev/null; then
    echo "libcomposite" >> /etc/modules
    echo "Added libcomposite to /etc/modules"
fi
if ! grep -q "^usb_f_hid" /etc/modules 2>/dev/null; then
    echo "usb_f_hid" >> /etc/modules
    echo "Added usb_f_hid to /etc/modules"
fi

# Try to load modules now (may fail if dwc2 overlay not active yet)
echo "Attempting to load kernel modules..."
if modprobe dwc2 2>/dev/null; then
    echo "✓ dwc2 module loaded"
else
    echo "! dwc2 will be available after reboot"
fi
if modprobe libcomposite 2>/dev/null; then
    echo "✓ libcomposite module loaded"
else
    echo "! libcomposite will be available after reboot"
fi
if modprobe usb_f_hid 2>/dev/null; then
    echo "✓ usb_f_hid module loaded"
else
    echo "! usb_f_hid will be available after reboot"
fi

echo ""
echo "Step 6: Setting up scripts..."
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
INSTALL_DIR=$(dirname "${SCRIPT_DIR}")

# Make scripts executable
chmod +x "${SCRIPT_DIR}/setup_gadget.sh"
chmod +x "${SCRIPT_DIR}/teardown_gadget.sh"

# Create systemd service (optional)
echo ""
read -p "Install systemd service for auto-start on boot? [y/N] " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo "Installing systemd service..."
    
    # Use the template and substitute paths
    sed -e "s|/home/pi/Pizero-to-X360|${INSTALL_DIR}|g" \
        "${SCRIPT_DIR}/xbox360-emulator.service" > /etc/systemd/system/xbox360-emulator.service
    
    systemctl daemon-reload
    
    echo ""
    read -p "Enable service to start automatically on boot? [y/N] " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        systemctl enable xbox360-emulator.service
        echo "✓ Service enabled - will start automatically on boot"
    else
        echo "Service installed but not enabled"
        echo "Enable later with: sudo systemctl enable xbox360-emulator.service"
    fi
    
    echo ""
    echo "Service commands:"
    echo "  Start:   sudo systemctl start xbox360-emulator"
    echo "  Stop:    sudo systemctl stop xbox360-emulator"
    echo "  Status:  sudo systemctl status xbox360-emulator"
    echo "  Logs:    sudo journalctl -u xbox360-emulator -f"
fi

echo ""
echo "====================================="
echo "Installation complete!"
echo "====================================="
echo ""
echo "IMPORTANT: A reboot is required for USB gadget mode to work."
echo ""
echo "After reboot:"
echo "  1. Run: sudo ${SCRIPT_DIR}/setup_gadget.sh"
echo "  2. Run: sudo python3 $(dirname "${SCRIPT_DIR}")/src/xbox360_emulator.py"
echo "  3. Connect Pi Zero to Xbox 360 via USB"
echo ""
read -p "Reboot now? [y/N] " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    reboot
fi
