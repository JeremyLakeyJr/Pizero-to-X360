#!/bin/bash
#
# Teardown script for Xbox 360 Controller USB Gadget (raw-gadget)
#
# This script safely stops any running emulator processes and
# optionally unloads the raw-gadget module.
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
echo ""

# Step 1: Stop any running emulator processes using PID files or process search
echo "[1/3] Stopping running emulator processes..."

# Find emulator process PIDs (using pgrep with full match on the binary name)
EMULATOR_PIDS=$(pgrep -f "xbox360_raw_emulator" 2>/dev/null || true)

if [ -n "${EMULATOR_PIDS}" ]; then
    echo "  Found emulator process(es): ${EMULATOR_PIDS}"
    for PID in ${EMULATOR_PIDS}; do
        echo "  Sending SIGTERM to PID ${PID}..."
        kill -TERM "${PID}" 2>/dev/null || true
    done
    
    # Wait for graceful shutdown
    sleep 2
    
    # Check if any processes are still running
    for PID in ${EMULATOR_PIDS}; do
        if kill -0 "${PID}" 2>/dev/null; then
            echo "  Process ${PID} still running, sending SIGKILL..."
            kill -KILL "${PID}" 2>/dev/null || true
        fi
    done
    echo "  [OK] Emulator processes stopped"
else
    echo "  [OK] No emulator processes running"
fi

# Step 2: Check and optionally unload raw-gadget module
echo ""
echo "[2/3] Checking raw_gadget module..."
if lsmod | grep -q "^raw_gadget"; then
    echo "  raw_gadget module is loaded"
    
    # Check if module is in use
    USED_BY=$(lsmod | grep "^raw_gadget" | awk '{print $3}')
    if [ "${USED_BY}" = "0" ]; then
        read -p "  Unload raw_gadget module? [y/N] " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            if rmmod raw_gadget 2>/dev/null; then
                echo "  [OK] raw_gadget module unloaded"
            else
                echo "  [WARNING] Failed to unload raw_gadget module"
            fi
        else
            echo "  [OK] raw_gadget module kept loaded"
        fi
    else
        echo "  [INFO] raw_gadget is in use (${USED_BY} references), not unloading"
    fi
else
    echo "  [OK] raw_gadget module not loaded"
fi

# Step 3: Verify cleanup
echo ""
echo "[3/3] Verifying cleanup..."

# Check for any remaining processes
REMAINING=$(pgrep -f "xbox360_raw_emulator" 2>/dev/null || true)
if [ -n "${REMAINING}" ]; then
    echo "  [WARNING] Some emulator processes may still be running: ${REMAINING}"
else
    echo "  [OK] No emulator processes running"
fi

# Check raw-gadget device
if [ -c /dev/raw-gadget ]; then
    echo "  [INFO] /dev/raw-gadget device still exists (module loaded)"
else
    echo "  [INFO] /dev/raw-gadget device removed (module unloaded)"
fi

echo ""
echo "Teardown complete!"
echo ""
echo "To restart the emulator:"
echo "  sudo ./scripts/setup_gadget.sh"
echo "  sudo ./bin/xbox360_raw_emulator"
echo ""
echo "Or via systemd:"
echo "  sudo systemctl start xbox360-emulator"
echo ""
