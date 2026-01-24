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

# Check /boot/cmdline.txt for dwc2 module
CMDLINE_TXT="/boot/cmdline.txt"
if [ -f "/boot/firmware/cmdline.txt" ]; then
    CMDLINE_TXT="/boot/firmware/cmdline.txt"
fi

if ! grep -q "modules-load=dwc2" "${CMDLINE_TXT}" 2>/dev/null; then
    echo "Adding dwc2 module to ${CMDLINE_TXT}..."
    sed -i 's/rootwait/rootwait modules-load=dwc2/' "${CMDLINE_TXT}"
else
    echo "dwc2 module already configured in ${CMDLINE_TXT}"
fi

echo ""
echo "Step 5: Loading kernel modules..."
modprobe libcomposite 2>/dev/null || echo "libcomposite will be available after reboot"
modprobe usb_f_hid 2>/dev/null || echo "usb_f_hid will be available after reboot"

# Add modules to load at boot
if ! grep -q "^libcomposite" /etc/modules 2>/dev/null; then
    echo "libcomposite" >> /etc/modules
fi
if ! grep -q "^usb_f_hid" /etc/modules 2>/dev/null; then
    echo "usb_f_hid" >> /etc/modules
fi

echo ""
echo "Step 6: Setting up scripts..."
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# Make scripts executable
chmod +x "${SCRIPT_DIR}/setup_gadget.sh"
chmod +x "${SCRIPT_DIR}/teardown_gadget.sh"

# Create systemd service (optional)
echo ""
read -p "Create systemd service for auto-start? [y/N] " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    INSTALL_DIR=$(dirname "${SCRIPT_DIR}")
    
    cat > /etc/systemd/system/xbox360-emulator.service << EOF
[Unit]
Description=Xbox 360 Controller Emulator
After=network.target

[Service]
Type=simple
ExecStartPre=${SCRIPT_DIR}/setup_gadget.sh
ExecStart=/usr/bin/python3 ${INSTALL_DIR}/src/xbox360_emulator.py
ExecStopPost=${SCRIPT_DIR}/teardown_gadget.sh
Restart=on-failure
User=root

[Install]
WantedBy=multi-user.target
EOF

    systemctl daemon-reload
    echo ""
    echo "Systemd service created: xbox360-emulator.service"
    echo "Enable with: sudo systemctl enable xbox360-emulator"
    echo "Start with:  sudo systemctl start xbox360-emulator"
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
