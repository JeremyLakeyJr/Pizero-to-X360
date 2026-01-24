#!/bin/bash
#
# Setup script for Xbox 360 Controller USB Gadget
#
# This script configures the Raspberry Pi Zero's USB gadget subsystem
# to emulate an Xbox 360 wired controller.
#
# Usage: sudo ./setup_gadget.sh
#
# Requirements:
#   - Raspberry Pi Zero (or Zero 2 W)
#   - USB gadget mode enabled in /boot/config.txt
#   - libcomposite kernel module
#

set -e

# Configuration
GADGET_NAME="xbox360"
GADGET_PATH="/sys/kernel/config/usb_gadget/${GADGET_NAME}"

# Xbox 360 Controller identifiers
VENDOR_ID="0x045e"      # Microsoft
PRODUCT_ID="0x028e"     # Xbox 360 Controller
DEVICE_BCD="0x0114"     # Device version 1.14
USB_BCD="0x0200"        # USB 2.0

# Strings
MANUFACTURER="©Microsoft Corporation"
PRODUCT="Controller"
SERIAL=""

# Check for root
if [ "$(id -u)" -ne 0 ]; then
    echo "Error: This script must be run as root"
    exit 1
fi

# Check for configfs
if [ ! -d "/sys/kernel/config" ]; then
    echo "Mounting configfs..."
    mount -t configfs none /sys/kernel/config
fi

if [ ! -d "/sys/kernel/config/usb_gadget" ]; then
    echo "Error: USB gadget configfs not available"
    echo "Make sure libcomposite module is loaded:"
    echo "  modprobe libcomposite"
    exit 1
fi

# Load required modules
echo "Loading kernel modules..."
modprobe libcomposite 2>/dev/null || true
modprobe usb_f_hid 2>/dev/null || true

# Clean up existing gadget
if [ -d "${GADGET_PATH}" ]; then
    echo "Removing existing gadget configuration..."
    ./teardown_gadget.sh 2>/dev/null || {
        # Manual cleanup
        echo "" > "${GADGET_PATH}/UDC" 2>/dev/null || true
        rm -f "${GADGET_PATH}/configs/c.1/hid.usb0" 2>/dev/null || true
        rmdir "${GADGET_PATH}/configs/c.1/strings/0x409" 2>/dev/null || true
        rmdir "${GADGET_PATH}/configs/c.1" 2>/dev/null || true
        rmdir "${GADGET_PATH}/functions/hid.usb0" 2>/dev/null || true
        rmdir "${GADGET_PATH}/strings/0x409" 2>/dev/null || true
        rmdir "${GADGET_PATH}" 2>/dev/null || true
    }
fi

echo "Creating USB gadget: ${GADGET_NAME}"

# Create gadget
mkdir -p "${GADGET_PATH}"
cd "${GADGET_PATH}"

# Set device identifiers
echo "${VENDOR_ID}" > idVendor
echo "${PRODUCT_ID}" > idProduct
echo "${DEVICE_BCD}" > bcdDevice
echo "${USB_BCD}" > bcdUSB

# Set device class (vendor specific for Xbox 360)
echo "0xff" > bDeviceClass
echo "0xff" > bDeviceSubClass
echo "0xff" > bDeviceProtocol

# Create English strings
mkdir -p strings/0x409
echo "${MANUFACTURER}" > strings/0x409/manufacturer
echo "${PRODUCT}" > strings/0x409/product
echo "${SERIAL}" > strings/0x409/serialnumber

# Create configuration
mkdir -p configs/c.1/strings/0x409
echo "500" > configs/c.1/MaxPower
echo "Xbox 360 Controller" > configs/c.1/strings/0x409/configuration

# Create HID function
mkdir -p functions/hid.usb0
echo "0" > functions/hid.usb0/protocol
echo "0" > functions/hid.usb0/subclass
echo "20" > functions/hid.usb0/report_length

# Write HID report descriptor
# This is a minimal vendor-specific descriptor for 20-byte reports
# For actual Xbox 360 compatibility, raw-gadget may be needed
cat > /tmp/xbox360_hid_desc.bin << 'HEXEOF'
HEXEOF

# Binary HID descriptor (hex encoded, then decoded)
printf '\x05\x01\x09\x05\xa1\x01\x15\x00\x26\xff\x00\x75\x08\x95\x14\x09\x00\x81\x02\x09\x00\x91\x02\xc0' > functions/hid.usb0/report_desc

# Link function to configuration
ln -sf functions/hid.usb0 configs/c.1/

# Get UDC name
UDC=$(ls /sys/class/udc 2>/dev/null | head -1)

if [ -n "${UDC}" ]; then
    echo "Binding to UDC: ${UDC}"
    echo "${UDC}" > UDC
    
    echo ""
    echo "USB gadget configured successfully!"
    echo ""
    echo "Device: ${GADGET_PATH}"
    echo "HID device: /dev/hidg0"
    echo ""
    echo "The Pi Zero should now appear as an Xbox 360 controller"
    echo "when connected to a host via USB."
else
    echo ""
    echo "Warning: No UDC available"
    echo "The USB gadget is configured but not bound to any UDC."
    echo ""
    echo "Make sure:"
    echo "  1. dwc2 overlay is enabled in /boot/config.txt:"
    echo "     dtoverlay=dwc2"
    echo "  2. The Pi is connected via the USB data port (not power)"
    echo ""
fi

# Show status
echo "Current gadget status:"
echo "  VID: $(cat idVendor)"
echo "  PID: $(cat idProduct)"
echo "  Manufacturer: $(cat strings/0x409/manufacturer)"
echo "  Product: $(cat strings/0x409/product)"

if [ -f "UDC" ] && [ -n "$(cat UDC)" ]; then
    echo "  UDC: $(cat UDC)"
else
    echo "  UDC: (not bound)"
fi

echo ""
echo "Next steps:"
echo "  1. Run: sudo python3 src/xbox360_emulator.py"
echo "  2. Connect an Xbox One controller via USB or Bluetooth"
echo "  3. Test by connecting Pi Zero to Xbox 360 or PC"
