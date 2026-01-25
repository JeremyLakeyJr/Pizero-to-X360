#!/bin/bash
#
# Setup script for Xbox 360 Controller USB Gadget (raw-gadget)
#
# This script loads the raw-gadget kernel module needed for
# low-level USB gadget emulation on Raspberry Pi Zero.
#
# Usage: sudo ./setup_gadget.sh
#
# Requirements:
#   - Raspberry Pi Zero (or Zero 2 W)
#   - USB gadget mode enabled in /boot/config.txt (dtoverlay=dwc2)
#   - raw-gadget kernel module installed
#
# UDC Names by Platform:
#   - Pi Zero / Zero W / Zero 2 W: 20980000.usb
#   - Pi 4: fe980000.usb
#

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
INSTALL_DIR="$(dirname "${SCRIPT_DIR}")"

# Check for root
if [ "$(id -u)" -ne 0 ]; then
    echo "Error: This script must be run as root"
    exit 1
fi

echo "Setting up Xbox 360 raw-gadget emulator..."
echo ""

# Step 1: Check dwc2 overlay is configured
echo "[1/5] Checking dwc2 overlay configuration..."
CONFIG_TXT="/boot/config.txt"
if [ -f "/boot/firmware/config.txt" ]; then
    CONFIG_TXT="/boot/firmware/config.txt"
fi

if grep -q "^dtoverlay=dwc2" "${CONFIG_TXT}" 2>/dev/null; then
    echo "  [OK] dtoverlay=dwc2 found in ${CONFIG_TXT}"
else
    echo "  [WARNING] dtoverlay=dwc2 not found in ${CONFIG_TXT}"
    echo "  You may need to add it and reboot for USB gadget mode to work."
fi

# Step 2: Load dwc2 (USB OTG controller driver)
echo ""
echo "[2/5] Loading dwc2 module..."
if lsmod | grep -q "^dwc2"; then
    echo "  [OK] dwc2 module already loaded"
else
    if modprobe dwc2 2>/dev/null; then
        echo "  [OK] dwc2 module loaded"
    else
        echo "  [WARNING] Failed to load dwc2 module"
        echo "  Make sure dtoverlay=dwc2 is set in ${CONFIG_TXT}"
        echo "  and reboot the system."
    fi
fi

# Step 3: Load raw-gadget module
echo ""
echo "[3/5] Loading raw-gadget module..."
if lsmod | grep -q "^raw_gadget"; then
    echo "  [OK] raw_gadget module already loaded"
else
    # Try modprobe first (for properly installed module)
    if modprobe raw_gadget 2>/dev/null; then
        echo "  [OK] raw_gadget module loaded via modprobe"
    # Fallback to insmod if .ko exists in project directory
    elif [ -f "${INSTALL_DIR}/raw_gadget.ko" ]; then
        if insmod "${INSTALL_DIR}/raw_gadget.ko" 2>/dev/null; then
            echo "  [OK] raw_gadget module loaded via insmod from ${INSTALL_DIR}"
        else
            echo "  [ERROR] Failed to load raw_gadget module"
            echo "  Try: sudo insmod ${INSTALL_DIR}/raw_gadget.ko"
            exit 1
        fi
    # Check /tmp/raw-gadget build location
    elif [ -f "/tmp/raw-gadget/raw_gadget/raw_gadget.ko" ]; then
        if insmod "/tmp/raw-gadget/raw_gadget/raw_gadget.ko" 2>/dev/null; then
            echo "  [OK] raw_gadget module loaded from /tmp/raw-gadget"
        else
            echo "  [ERROR] Failed to load raw_gadget module"
            exit 1
        fi
    else
        echo "  [ERROR] raw_gadget module not found"
        echo ""
        echo "  Please install raw-gadget:"
        echo "    1. Run: make build-rawgadget"
        echo "    2. Run: sudo make install-rawgadget"
        echo ""
        echo "  Or manually:"
        echo "    cd /tmp"
        echo "    git clone https://github.com/xairy/raw-gadget.git"
        echo "    cd raw-gadget"
        echo "    make && sudo make install"
        echo "    sudo modprobe raw_gadget"
        exit 1
    fi
fi

# Step 4: Check if raw-gadget device is available
echo ""
echo "[4/5] Checking raw-gadget device..."
if [ -c /dev/raw-gadget ]; then
    echo "  [OK] /dev/raw-gadget exists"
    echo "  Permissions: $(ls -l /dev/raw-gadget | awk '{print $1, $3, $4}')"
else
    echo "  [ERROR] /dev/raw-gadget device not found"
    echo "  The raw_gadget module loaded but device node is missing."
    echo "  Check dmesg for errors: dmesg | tail -20"
    exit 1
fi

# Step 5: Check UDC availability and display name
echo ""
echo "[5/5] Checking UDC (USB Device Controller)..."
UDC_DIR="/sys/class/udc"
if [ -d "${UDC_DIR}" ]; then
    UDC=$(ls "${UDC_DIR}" 2>/dev/null | head -1)
    if [ -n "${UDC}" ]; then
        echo "  [OK] UDC available: ${UDC}"
        
        # Verify it's the expected Pi Zero UDC
        case "${UDC}" in
            "20980000.usb")
                echo "  Platform: Raspberry Pi Zero / Zero W / Zero 2 W"
                ;;
            "fe980000.usb")
                echo "  Platform: Raspberry Pi 4"
                ;;
            "dummy_udc"*)
                echo "  Platform: Dummy UDC (for testing)"
                ;;
            *)
                echo "  Platform: Unknown (UDC name: ${UDC})"
                ;;
        esac
    else
        echo "  [WARNING] No UDC available"
        echo ""
        echo "  Troubleshooting:"
        echo "    1. Ensure dtoverlay=dwc2 is in ${CONFIG_TXT}"
        echo "    2. Ensure dwc2 is in /etc/modules"
        echo "    3. Make sure Pi is connected via USB data port (not power port)"
        echo "    4. Reboot after configuration changes"
        echo ""
    fi
else
    echo "  [WARNING] ${UDC_DIR} not found"
fi

echo ""
echo "=========================================="
echo "raw-gadget setup complete!"
echo "=========================================="
echo ""
echo "Device:  /dev/raw-gadget"
echo "UDC:     ${UDC:-Not available (check dwc2 configuration)}"
echo ""
echo "Next steps:"
echo "  1. Build the emulator (if not built): make build"
echo "  2. Run: sudo ./bin/xbox360_raw_emulator"
echo "  3. Connect Pi Zero to Xbox 360 or PC via USB"
echo ""
echo "Or use systemd service:"
echo "  sudo systemctl start xbox360-emulator"
echo "  sudo journalctl -u xbox360-emulator -f"
echo ""
