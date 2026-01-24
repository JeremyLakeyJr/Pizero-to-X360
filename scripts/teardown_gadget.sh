#!/bin/bash
#
# Teardown script for Xbox 360 Controller USB Gadget (raw-gadget)
#
# This script unloads the raw-gadget module.
#
# Usage: sudo ./teardown_gadget.sh
#

set -e

# Check for root
if [ "$(id -u)" -ne 0 ]; then
    echo "Error: This script must be run as root"
    exit 1
fi

echo "Removing Xbox 360 raw-gadget emulator..."

# Kill any running emulator processes
if pgrep -x "xbox360_raw_emu" > /dev/null; then
    echo "Stopping running emulator..."
    pkill -x "xbox360_raw_emu" || true
    sleep 1
fi

# Unload raw-gadget module
if lsmod | grep -q raw_gadget; then
    echo "Unloading raw_gadget module..."
    rmmod raw_gadget || echo "Warning: Failed to unload raw_gadget"
else
    echo "raw_gadget module not loaded"
fi

echo "Teardown complete"
