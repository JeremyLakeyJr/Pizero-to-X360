#!/bin/bash
#
# Setup script for Xbox 360 Controller USB Gadget (raw-gadget)
#
# This script loads the raw-gadget kernel module needed for
# low-level USB gadget emulation.
#
# Usage: sudo ./setup_gadget.sh
#
# Requirements:
#   - Raspberry Pi Zero (or Zero 2 W)
#   - USB gadget mode enabled in /boot/config.txt
#   - raw-gadget kernel module installed
#

set -e

# Check for root
if [ "$(id -u)" -ne 0 ]; then
    echo "Error: This script must be run as root"
    exit 1
fi

echo "Setting up Xbox 360 raw-gadget emulator..."

# Load dwc2 (USB OTG controller driver)
echo "Loading dwc2 module..."
if ! modprobe dwc2 2>/dev/null; then
    echo "Warning: Failed to load dwc2 module"
    echo "Make sure dtoverlay=dwc2 is set in /boot/config.txt"
fi

# Load raw-gadget module
echo "Loading raw-gadget module..."
if ! modprobe raw_gadget 2>/dev/null; then
    echo "Error: Failed to load raw_gadget module"
    echo ""
    echo "Make sure raw-gadget is installed:"
    echo "  1. Run: make build-rawgadget"
    echo "  2. Run: sudo make install-rawgadget"
    echo ""
    echo "Or manually:"
    echo "  cd /tmp"
    echo "  git clone https://github.com/xairy/raw-gadget.git"
    echo "  cd raw-gadget"
    echo "  make && sudo make install"
    echo "  sudo modprobe raw_gadget"
    exit 1
fi

# Check if raw-gadget device is available
if [ ! -c /dev/raw-gadget ]; then
    echo "Error: /dev/raw-gadget device not found"
    echo "The raw_gadget module loaded but device node is missing."
    exit 1
fi

# Check UDC availability
UDC=$(ls /sys/class/udc 2>/dev/null | head -1)
if [ -z "${UDC}" ]; then
    echo "Warning: No UDC available"
    echo ""
    echo "Make sure:"
    echo "  1. dwc2 overlay is enabled in /boot/config.txt:"
    echo "     dtoverlay=dwc2"
    echo "  2. The Pi is connected via the USB data port (not power)"
    echo ""
else
    echo "UDC available: ${UDC}"
fi

echo ""
echo "raw-gadget setup complete!"
echo ""
echo "Device: /dev/raw-gadget"
echo "Permissions: $(ls -l /dev/raw-gadget)"
echo ""
echo "Next steps:"
echo "  1. Build the emulator: make build"
echo "  2. Run: sudo ./bin/xbox360_raw_emulator"
echo "  3. Connect Pi Zero to Xbox 360 or PC via USB"
echo ""
