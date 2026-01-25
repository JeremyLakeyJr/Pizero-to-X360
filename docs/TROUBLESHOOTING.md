# Troubleshooting Guide

This guide covers common issues and their solutions when using the Xbox 360 Controller Emulator.

## Quick Checklist

Before diving into specific issues, verify these basics:

- [ ] Raspberry Pi Zero (or Zero 2 W) with OTG-capable USB port
- [ ] `dtoverlay=dwc2` in `/boot/config.txt` (or `/boot/firmware/config.txt`)
- [ ] `dwc2` in `/etc/modules` for auto-load at boot
- [ ] `raw_gadget` in `/etc/modules` for auto-load at boot
- [ ] System rebooted after making boot changes
- [ ] Running scripts with `sudo`
- [ ] Using USB data port (not power-only port on Pi Zero)

**Important:** Do NOT modify `/boot/cmdline.txt` - this can cause boot failures. Use only `/boot/config.txt` and `/etc/modules`.

## Common Issues

### 1. "USB_RAW_IOCTL_INIT failed: Invalid argument" Error

**Symptom:**
```
USB_RAW_IOCTL_INIT failed: Invalid argument
```

**Cause:** The `driver_name` and/or `device_name` in the raw-gadget initialization are incorrect for your hardware.

**Understanding UDC Names:**

| Platform | UDC Name |
|----------|----------|
| Pi Zero / Zero W / Zero 2 W | `20980000.usb` |
| Pi 4 | `fe980000.usb` |
| Dummy (testing) | `dummy_udc.0` |

**Solutions:**

1. **Check your UDC name:**
   ```bash
   ls /sys/class/udc/
   # Should show: 20980000.usb (on Pi Zero)
   ```

2. **Verify dwc2 module is loaded:**
   ```bash
   lsmod | grep dwc2
   # Should show dwc2 in the output
   ```

3. **Verify raw-gadget is loaded:**
   ```bash
   lsmod | grep raw_gadget
   ls -l /dev/raw-gadget
   ```

4. **If UDC is missing:**
   - Ensure `dtoverlay=dwc2` is in `/boot/config.txt`
   - Add `dwc2` to `/etc/modules`
   - Reboot the system

5. **Manual verification (the C code now auto-detects):**
   ```bash
   # The emulator auto-detects the UDC name from /sys/class/udc/
   # If auto-detection fails, it falls back to "20980000.usb"
   ```

**Technical Details:**

The `20980000.usb` name comes from the BCM2835 USB controller's memory-mapped address (0x20980000) on Raspberry Pi Zero. The raw-gadget kernel module requires:
- `driver_name`: "dwc2" (the USB device controller driver)
- `device_name`: The UDC name from `/sys/class/udc/` (e.g., "20980000.usb")

### 2. "configfs not mounted" Error

**Symptom:**
```
Error: USB gadget configfs not available
```

**Note:** This error is from the old libcomposite method. If using raw-gadget (recommended), you should not see this error. If you do, make sure you're running the raw-gadget emulator (`./bin/xbox360_raw_emulator`), not the Python configfs version.

**Solution (if using legacy configfs method):**
```bash
# Mount configfs manually
sudo mount -t configfs none /sys/kernel/config

# Or load libcomposite which mounts it automatically
sudo modprobe libcomposite
```

### 3. "No UDC available" Warning

**Symptom:**
```
Warning: No UDC available
The USB gadget is configured but not bound to any UDC.
```

**Cause:** The dwc2 driver isn't loaded or the USB port isn't in device mode.

**Solutions:**

1. Check if dwc2 overlay is enabled:
   ```bash
   grep dtoverlay=dwc2 /boot/config.txt
   # Or for newer systems:
   grep dtoverlay=dwc2 /boot/firmware/config.txt
   # Should show: dtoverlay=dwc2
   ```

2. Check if dwc2 is in /etc/modules:
   ```bash
   grep dwc2 /etc/modules
   # Should show: dwc2
   ```

3. Manually load module:
   ```bash
   sudo modprobe dwc2
   ```

4. Check for UDC:
   ```bash
   ls /sys/class/udc
   # Should show: 20980000.usb (on Pi Zero)
   ```

5. Verify you're using the USB data port:
   - Pi Zero has two micro USB ports
   - Use the port labeled "USB" (not "PWR")
   - The data port is the one closer to the center of the board

### 4. No `/dev/hidg0` Device

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
lsmod | grep -E "(dwc2|raw_gadget|libcomposite|usb_f_hid|xpad)"

# UDC status
ls -la /sys/class/udc/
```

### Raw-Gadget Status
```bash
# Check if raw-gadget module is loaded
lsmod | grep raw_gadget

# Check if raw-gadget device exists
ls -l /dev/raw-gadget

# Check emulator process
ps aux | grep xbox360_raw_emulator

# Check systemd service status
sudo systemctl status xbox360-emulator

# View service logs
sudo journalctl -u xbox360-emulator -n 50 --no-pager
```

### Legacy Gadget Status (configfs)
```bash
# Gadget configuration (only for legacy configfs method)
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

## Raw-Gadget Specific Issues

### raw_gadget module won't load

**Symptom:**
```
modprobe: FATAL: Module raw_gadget not found
```

**Solutions:**

1. **Rebuild for current kernel:**
   ```bash
   cd /tmp/raw-gadget
   make clean
   make
   sudo make install
   sudo depmod -a
   sudo modprobe raw_gadget
   ```

2. **Check if module file exists:**
   ```bash
   # Check system modules directory
   find /lib/modules/$(uname -r) -name "raw_gadget.ko"
   
   # Check project directory
   ls -l /path/to/Pizero-to-X360/raw_gadget.ko
   ```

3. **Load manually with insmod:**
   ```bash
   sudo insmod /path/to/raw_gadget.ko
   ```

### /dev/raw-gadget not created

**Symptom:** Module loads but `/dev/raw-gadget` doesn't appear.

**Solutions:**

1. Check dmesg for errors:
   ```bash
   dmesg | tail -20 | grep -i raw
   ```

2. Check if device was created with wrong name:
   ```bash
   ls -la /dev/ | grep raw
   ```

3. Reload the module:
   ```bash
   sudo rmmod raw_gadget
   sudo modprobe raw_gadget
   ```

### Emulator exits immediately

**Symptom:** `xbox360_raw_emulator` starts but exits with error.

**Debug steps:**

1. Run manually to see error output:
   ```bash
   sudo ./bin/xbox360_raw_emulator
   ```

2. Check for "Invalid argument" error (see issue #1 above)

3. Verify all prerequisites:
   ```bash
   # UDC available?
   ls /sys/class/udc/
   
   # raw-gadget device available?
   ls -l /dev/raw-gadget
   
   # dwc2 loaded?
   lsmod | grep dwc2
   ```

## Getting Help

If you're still stuck:

1. Check the [GitHub Issues](https://github.com/JeremyLakeyJr/Pizero-to-X360/issues)
2. Create a new issue with:
   - Pi model and OS version
   - Output of `make status`
   - Output of `ls /sys/class/udc/`
   - Output of `lsmod | grep -E "(dwc2|raw_gadget)"`
   - Full error messages
   - Steps to reproduce

## Known Limitations

1. **Authentication**: Real Xbox 360 controllers have authentication chips. The console doesn't enforce this for wired controllers, but wireless/some games might.

2. **USB Hubs**: Not all hubs work correctly with USB gadget mode. Try different hubs if you have issues.

3. **Kernel Updates**: After a kernel update, you may need to rebuild the raw-gadget module. Run `sudo ./scripts/install.sh` again to rebuild.

4. **UDC Timing**: On some systems, the UDC may not be immediately available after boot. The systemd service has a brief delay to handle this.
