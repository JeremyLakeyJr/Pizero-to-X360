# Troubleshooting Guide

This guide covers common issues and their solutions when using the Xbox 360 Controller Emulator.

## Quick Checklist

Before diving into specific issues, verify these basics:

- [ ] Raspberry Pi Zero (or Zero 2 W) with OTG-capable USB port
- [ ] `dtoverlay=dwc2` in `/boot/config.txt` (or `/boot/firmware/config.txt`)
- [ ] `modules-load=dwc2` in `/boot/cmdline.txt`
- [ ] System rebooted after making boot changes
- [ ] Running scripts with `sudo`
- [ ] Using USB data port (not power-only port on Pi Zero)

## Common Issues

### 1. "configfs not mounted" Error

**Symptom:**
```
Error: USB gadget configfs not available
```

**Solution:**
```bash
# Mount configfs manually
sudo mount -t configfs none /sys/kernel/config

# Or load libcomposite which mounts it automatically
sudo modprobe libcomposite
```

**Permanent fix:** Add to `/etc/fstab`:
```
configfs    /sys/kernel/config    configfs    defaults    0    0
```

### 2. "No UDC available" Warning

**Symptom:**
```
Warning: No UDC available
The USB gadget is configured but not bound to any UDC.
```

**Cause:** The dwc2 driver isn't loaded in USB device mode.

**Solutions:**

1. Check if dwc2 overlay is enabled:
   ```bash
   cat /boot/config.txt | grep dwc2
   # Should show: dtoverlay=dwc2
   ```

2. Check kernel command line:
   ```bash
   cat /proc/cmdline | grep dwc2
   # Should contain: modules-load=dwc2
   ```

3. Manually load module:
   ```bash
   sudo modprobe dwc2
   ```

4. Check for UDC:
   ```bash
   ls /sys/class/udc
   # Should show something like: 20980000.usb
   ```

### 3. No `/dev/hidg0` Device

**Symptom:** Gadget setup completes but `/dev/hidg0` doesn't appear.

**Solutions:**

1. Check for usb_f_hid module:
   ```bash
   sudo modprobe usb_f_hid
   ```

2. Check dmesg for errors:
   ```bash
   dmesg | tail -30 | grep -i usb
   ```

3. Verify gadget is bound:
   ```bash
   cat /sys/kernel/config/usb_gadget/xbox360/UDC
   ```

### 4. Permission Denied Errors

**Symptom:**
```
PermissionError: [Errno 13] Permission denied
```

**Solution:** Run with sudo or adjust permissions:
```bash
# Option 1: Run as root
sudo python3 src/xbox360_emulator.py

# Option 2: Add udev rule for HID gadget
echo 'KERNEL=="hidg*", MODE="0666"' | sudo tee /etc/udev/rules.d/99-hidg.rules
sudo udevadm control --reload-rules
sudo udevadm trigger
```

### 5. Input Controller Not Detected

**Symptom:**
```
RuntimeError: No Xbox controller found
```

**Solutions:**

1. List available devices:
   ```bash
   sudo python3 src/xbox360_emulator.py --list-devices
   ```

2. Check if controller is connected:
   ```bash
   lsusb | grep -i xbox
   # Or for any controllers
   lsusb | grep -i microsoft
   ```

3. Check evdev devices:
   ```bash
   ls -la /dev/input/event*
   cat /proc/bus/input/devices
   ```

4. Manually specify device:
   ```bash
   sudo python3 src/xbox360_emulator.py --input /dev/input/event0
   ```

5. Install xpad driver (if not loaded):
   ```bash
   sudo modprobe xpad
   ```

### 6. Xbox 360 Doesn't Recognize Controller

**Symptom:** LED on Pi shows activity but Xbox 360 doesn't detect controller.

**Possible Causes:**

1. **Wrong USB port**: Make sure you're using the micro USB data port, not the power port.

2. **Descriptor mismatch**: The Xbox 360 is very picky about USB descriptors. Check:
   ```bash
   # On a PC, verify the device appears correctly
   lsusb -v -d 045e:028e
   ```

3. **Missing initialization sequence**: The Xbox 360 may send vendor-specific control requests that need proper responses.

4. **Timing issues**: Reports must be sent regularly (~8ms intervals).

**Debug steps:**
- First test on a PC to verify basic USB enumeration
- Use Wireshark with USB capture to compare with real controller

### 7. Buttons/Sticks Not Working Correctly

**Symptom:** Controller is recognized but inputs are wrong.

**Solutions:**

1. Run in debug mode to see input values:
   ```bash
   sudo python3 src/xbox360_emulator.py --debug
   ```

2. Test input handler directly:
   ```bash
   sudo python3 src/input_handler.py
   ```

3. Check axis calibration - different drivers report different ranges

4. Check button mapping - Xbox One uses slightly different codes than Xbox 360

### 8. Pi Zero Single USB Port Limitation

**Problem:** Pi Zero has only one micro USB port for both data and power.

**Solutions:**

1. **USB OTG Hub**: Use a hub that supports both host and device mode:
   - Connect power to hub
   - Connect Xbox One controller to hub
   - Connect hub to Pi data port
   - Pi data port to Xbox 360

2. **Bluetooth input**: Use a Pi Zero W with Bluetooth:
   - Install xpadneo: `sudo apt install dkms && git clone https://github.com/atar-axis/xpadneo && cd xpadneo && sudo ./install.sh`
   - Pair Xbox One controller via Bluetooth
   - Use USB port for Xbox 360 connection only

3. **Powered USB Hub**: 
   - Some hubs can power the Pi while still allowing gadget mode
   - This is hardware-dependent and may not work with all hubs

### 9. High CPU Usage

**Symptom:** Pi runs hot or becomes unresponsive.

**Solutions:**

1. Increase polling interval (may affect responsiveness):
   ```python
   # In xbox360_emulator.py, change:
   REPORT_INTERVAL = 0.010  # 10ms instead of 8ms
   ```

2. Disable debug logging:
   ```bash
   sudo python3 src/xbox360_emulator.py  # Without --debug
   ```

3. Use Python 3 (not Python 2)

4. Consider rewriting critical paths in C for production use

### 10. evdev Import Error

**Symptom:**
```
ImportError: No module named 'evdev'
```

**Solution:**
```bash
sudo pip3 install evdev
# Or with apt
sudo apt install python3-evdev
```

## Diagnostic Commands

### System Information
```bash
# Pi model
cat /proc/device-tree/model

# Kernel version
uname -r

# USB status
lsusb
lsusb -t

# Loaded modules
lsmod | grep -E "(dwc2|libcomposite|usb_f_hid|xpad)"

# UDC status
ls -la /sys/class/udc/
```

### Gadget Status
```bash
# Gadget configuration
ls -la /sys/kernel/config/usb_gadget/

# Device descriptors
cat /sys/kernel/config/usb_gadget/xbox360/idVendor
cat /sys/kernel/config/usb_gadget/xbox360/idProduct
cat /sys/kernel/config/usb_gadget/xbox360/UDC
```

### USB Capture (on PC)
```bash
# Install usbmon
sudo modprobe usbmon

# List USB buses
lsusb

# Capture with tcpdump
sudo tcpdump -i usbmon1 -w capture.pcap

# Or use Wireshark directly
sudo wireshark -i usbmon1
```

## Getting Help

If you're still stuck:

1. Check the [GitHub Issues](https://github.com/JeremyLakeyJr/Pizero-to-X360/issues)
2. Create a new issue with:
   - Pi model and OS version
   - Output of `make status`
   - Full error messages
   - Steps to reproduce

## Known Limitations

1. **Authentication**: Real Xbox 360 controllers have authentication chips. The console doesn't enforce this for wired controllers, but wireless/some games might.

2. **USB Hubs**: Not all hubs work correctly with USB gadget mode. Try different hubs if you have issues.

3. **Raw-gadget**: The configfs approach may not handle all vendor-specific requests. For full compatibility, raw-gadget may be needed (see DEVELOPMENT.md).
