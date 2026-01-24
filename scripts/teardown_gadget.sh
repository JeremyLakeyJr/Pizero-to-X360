#!/bin/bash
#
# Teardown script for Xbox 360 Controller USB Gadget
#
# This script removes the USB gadget configuration created by setup_gadget.sh
#
# Usage: sudo ./teardown_gadget.sh
#

set -e

GADGET_NAME="xbox360"
GADGET_PATH="/sys/kernel/config/usb_gadget/${GADGET_NAME}"

# Check for root
if [ "$(id -u)" -ne 0 ]; then
    echo "Error: This script must be run as root"
    exit 1
fi

if [ ! -d "${GADGET_PATH}" ]; then
    echo "Gadget ${GADGET_NAME} does not exist"
    exit 0
fi

echo "Removing USB gadget: ${GADGET_NAME}"

cd "${GADGET_PATH}"

# Unbind from UDC
if [ -f "UDC" ] && [ -n "$(cat UDC 2>/dev/null)" ]; then
    echo "Unbinding from UDC..."
    echo "" > UDC
fi

# Remove function symlinks from configs
for config in configs/*/; do
    if [ -d "${config}" ]; then
        echo "Cleaning config: ${config}"
        for link in "${config}"*; do
            if [ -L "${link}" ]; then
                echo "  Removing link: ${link}"
                rm -f "${link}"
            fi
        done
        
        # Remove config strings
        if [ -d "${config}strings/0x409" ]; then
            rmdir "${config}strings/0x409"
        fi
        
        rmdir "${config}" 2>/dev/null || true
    fi
done

# Remove functions
for func in functions/*/; do
    if [ -d "${func}" ]; then
        echo "Removing function: ${func}"
        rmdir "${func}"
    fi
done

# Remove strings
if [ -d "strings/0x409" ]; then
    rmdir strings/0x409
fi

# Remove gadget
cd /
rmdir "${GADGET_PATH}"

echo "USB gadget removed successfully"
