#!/bin/bash
#
# Installation script for Xbox 360 Controller Emulator
#
# This script installs all dependencies and configures the system
# for running the Xbox 360 controller emulator on a Raspberry Pi Zero.
#
# Usage: sudo ./install.sh
#
# What this script does:
#   1. Updates system packages
#   2. Installs build dependencies (gcc, headers, etc.)
#   3. Installs Python packages (evdev, pyusb)
#   4. Configures /boot/config.txt for USB gadget mode (dtoverlay=dwc2)
#   5. Configures /etc/modules for auto-loading dwc2 and raw_gadget
#   6. Builds and installs the raw-gadget kernel module
#   7. Builds the C emulator binary
#   8. Optionally installs and enables the systemd service
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

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
INSTALL_DIR="$(dirname "${SCRIPT_DIR}")"
KERNEL_VERSION=$(uname -r)

echo "Installation directory: ${INSTALL_DIR}"
echo "Kernel version: ${KERNEL_VERSION}"
echo ""

# Check for Raspberry Pi
if [ ! -f /proc/device-tree/model ]; then
    echo "Warning: This doesn't appear to be a Raspberry Pi"
    read -p "Continue anyway? [y/N] " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
else
    MODEL=$(tr -d '\0' < /proc/device-tree/model)
    echo "Detected: ${MODEL}"
    if [[ ! "${MODEL}" =~ "Zero" ]]; then
        echo "Warning: This is designed for Raspberry Pi Zero"
        echo "Other models may work but are not tested."
        echo ""
    fi
fi

echo ""
echo "Step 1: Updating system packages..."
echo "======================================="
apt-get update

echo ""
echo "Step 2: Installing build dependencies..."
echo "======================================="
apt-get install -y \
    python3 \
    python3-pip \
    python3-dev \
    git \
    build-essential \
    bc \
    bison \
    flex \
    libssl-dev

# Install kernel headers (try both methods)
if ! apt-get install -y linux-headers-${KERNEL_VERSION} 2>/dev/null; then
    echo "linux-headers-${KERNEL_VERSION} not available, trying raspberrypi-kernel-headers..."
    apt-get install -y raspberrypi-kernel-headers || echo "Warning: Could not install kernel headers"
fi

echo ""
echo "Step 3: Installing Python packages..."
echo "======================================="
pip3 install evdev pyusb --break-system-packages 2>/dev/null || pip3 install evdev pyusb

echo ""
echo "Step 4: Configuring USB gadget mode (boot options)..."
echo "======================================="

# Check /boot/config.txt for dwc2 overlay
CONFIG_TXT="/boot/config.txt"
if [ -f "/boot/firmware/config.txt" ]; then
    CONFIG_TXT="/boot/firmware/config.txt"
fi
echo "Config file: ${CONFIG_TXT}"

if ! grep -q "^dtoverlay=dwc2" "${CONFIG_TXT}" 2>/dev/null; then
    echo "Adding dwc2 overlay to ${CONFIG_TXT}..."
    echo "" >> "${CONFIG_TXT}"
    echo "# Enable USB gadget mode (dwc2) for Xbox 360 emulator" >> "${CONFIG_TXT}"
    echo "dtoverlay=dwc2" >> "${CONFIG_TXT}"
    echo "[OK] dwc2 overlay added"
else
    echo "[OK] dwc2 overlay already configured"
fi

echo ""
echo "Step 5: Configuring kernel modules for auto-load at boot..."
echo "======================================="

# Add dwc2 to /etc/modules for auto-loading at boot
if ! grep -q "^dwc2" /etc/modules 2>/dev/null; then
    echo "dwc2" >> /etc/modules
    echo "[OK] Added dwc2 to /etc/modules"
else
    echo "[OK] dwc2 already in /etc/modules"
fi

# Add raw_gadget to /etc/modules (will work after module is properly installed)
if ! grep -q "^raw_gadget" /etc/modules 2>/dev/null; then
    echo "raw_gadget" >> /etc/modules
    echo "[OK] Added raw_gadget to /etc/modules"
else
    echo "[OK] raw_gadget already in /etc/modules"
fi

# Try to load dwc2 module now (may fail if overlay not active yet)
echo ""
echo "Attempting to load dwc2 module..."
if modprobe dwc2 2>/dev/null; then
    echo "[OK] dwc2 module loaded"
else
    echo "[INFO] dwc2 will be available after reboot"
fi

echo ""
echo "Step 6: Building and installing raw-gadget module..."
echo "======================================="

# Check if raw-gadget is already properly installed
if modprobe raw_gadget 2>/dev/null && [ -c /dev/raw-gadget ]; then
    echo "[OK] raw-gadget module already installed and working"
    RAWGADGET_OK=true
else
    RAWGADGET_OK=false
    echo "Building raw-gadget from source..."
    
    # Clone if not exists
    RAW_GADGET_DIR="/tmp/raw-gadget"
    if [ ! -d "${RAW_GADGET_DIR}" ]; then
        cd /tmp
        git clone https://github.com/xairy/raw-gadget.git
    fi
    
    # Build the module
    cd "${RAW_GADGET_DIR}"
    make clean 2>/dev/null || true
    
    if make; then
        echo "[OK] raw-gadget module built successfully"
        
        # Install the module properly for persistent loading
        echo ""
        echo "Installing raw-gadget module for persistent loading..."
        
        # Create the extra modules directory if it doesn't exist
        MODULES_DIR="/lib/modules/${KERNEL_VERSION}/extra"
        mkdir -p "${MODULES_DIR}"
        
        # Copy the module
        if [ -f "${RAW_GADGET_DIR}/raw_gadget/raw_gadget.ko" ]; then
            cp "${RAW_GADGET_DIR}/raw_gadget/raw_gadget.ko" "${MODULES_DIR}/"
        elif [ -f "${RAW_GADGET_DIR}/raw_gadget.ko" ]; then
            cp "${RAW_GADGET_DIR}/raw_gadget.ko" "${MODULES_DIR}/"
        else
            echo "[WARNING] Could not find raw_gadget.ko"
        fi
        
        # Update module dependencies
        echo "Running depmod to update module dependencies..."
        depmod -a
        
        # Also copy to install directory as fallback
        find "${RAW_GADGET_DIR}" -name "raw_gadget.ko" -exec cp {} "${INSTALL_DIR}/" \; 2>/dev/null || true
        
        # Try to load the module
        if modprobe raw_gadget 2>/dev/null; then
            echo "[OK] raw_gadget module loaded successfully"
            RAWGADGET_OK=true
        elif [ -f "${INSTALL_DIR}/raw_gadget.ko" ] && insmod "${INSTALL_DIR}/raw_gadget.ko" 2>/dev/null; then
            echo "[OK] raw_gadget module loaded via insmod"
            RAWGADGET_OK=true
        else
            echo "[WARNING] raw_gadget will be available after reboot"
        fi
    else
        echo "[ERROR] Failed to build raw-gadget module"
        echo "This may be due to missing kernel headers."
        echo "Try: sudo apt install raspberrypi-kernel-headers"
    fi
fi

# Verify raw-gadget device
if [ -c /dev/raw-gadget ]; then
    echo "[OK] /dev/raw-gadget device is available"
else
    echo "[INFO] /dev/raw-gadget will be available after reboot"
fi

echo ""
echo "Step 7: Building C emulator..."
echo "======================================="

cd "${INSTALL_DIR}"

# Create bin directory if needed
mkdir -p "${INSTALL_DIR}/bin"

if make build; then
    echo "[OK] C emulator built: ${INSTALL_DIR}/bin/xbox360_raw_emulator"
else
    echo "[WARNING] Failed to build C emulator"
    echo "You can build manually later with: make build"
fi

echo ""
echo "Step 8: Setting up scripts..."
echo "======================================="

# Make scripts executable
chmod +x "${SCRIPT_DIR}/setup_gadget.sh"
chmod +x "${SCRIPT_DIR}/teardown_gadget.sh"
echo "[OK] Scripts made executable"

# Install systemd service
echo ""
echo "Step 9: Systemd service setup..."
echo "======================================="
read -p "Install systemd service for auto-start on boot? [y/N] " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo "Installing systemd service..."
    
    # Substitute paths in the service file
    sed -e "s|/home/pi/Pizero-to-X360|${INSTALL_DIR}|g" \
        -e "s|/home/lakey/Pizero-to-X360|${INSTALL_DIR}|g" \
        "${SCRIPT_DIR}/xbox360-emulator.service" > /etc/systemd/system/xbox360-emulator.service
    
    systemctl daemon-reload
    echo "[OK] Service file installed"
    
    echo ""
    read -p "Enable service to start automatically on boot? [y/N] " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        systemctl enable xbox360-emulator.service
        echo "[OK] Service enabled - will start automatically on boot"
    else
        echo "[INFO] Service installed but not enabled"
        echo "Enable later with: sudo systemctl enable xbox360-emulator.service"
    fi
    
    echo ""
    echo "Systemd service commands:"
    echo "  Start:   sudo systemctl start xbox360-emulator"
    echo "  Stop:    sudo systemctl stop xbox360-emulator"
    echo "  Status:  sudo systemctl status xbox360-emulator"
    echo "  Logs:    sudo journalctl -u xbox360-emulator -f"
else
    echo "[INFO] Skipped systemd service installation"
fi

echo ""
echo "====================================="
echo "Installation Summary"
echo "====================================="
echo ""
echo "Installation directory: ${INSTALL_DIR}"
echo "Config file: ${CONFIG_TXT}"
echo ""
echo "Module status:"
if lsmod | grep -q "^dwc2"; then
    echo "  dwc2:       [LOADED]"
else
    echo "  dwc2:       [Will load after reboot]"
fi
if lsmod | grep -q "^raw_gadget"; then
    echo "  raw_gadget: [LOADED]"
else
    echo "  raw_gadget: [Will load after reboot]"
fi
echo ""
echo "UDC status:"
UDC=$(ls /sys/class/udc 2>/dev/null | head -1)
if [ -n "${UDC}" ]; then
    echo "  Available:  ${UDC}"
else
    echo "  Not available (will be after reboot)"
fi

echo ""
echo "====================================="
echo "IMPORTANT: A reboot is recommended!"
echo "====================================="
echo ""
echo "After reboot:"
echo "  1. Verify raw-gadget: ls -l /dev/raw-gadget"
echo "  2. Check UDC name: ls /sys/class/udc/"
echo "  3. Run emulator: sudo ${INSTALL_DIR}/bin/xbox360_raw_emulator"
echo "  4. Connect Pi Zero to Xbox 360 or PC via USB"
echo "  5. On PC: Check 'dmesg | grep xpad' for driver binding"
echo ""
read -p "Reboot now? [y/N] " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    reboot
fi
