# Pi Zero to Xbox 360 Controller Emulator

This project turns a Raspberry Pi Zero (or Zero 2 W) into a USB adapter that reads input from a modern Xbox One/Series controller and emulates a genuine wired Xbox 360 controller. This allows you to use newer controllers with an original Xbox 360 console.

## Supported Inputs

This emulator supports **all Xbox 360 controller inputs**:

| Input Type | Supported Inputs |
|------------|------------------|
| **Face Buttons** | A, B, X, Y |
| **Bumpers** | Left Bumper (LB), Right Bumper (RB) |
| **Triggers** | Left Trigger (LT), Right Trigger (RT) - Full 8-bit analog (0-255) |
| **D-Pad** | Up, Down, Left, Right |
| **Analog Sticks** | Left Stick (X/Y), Right Stick (X/Y) - Full 16-bit precision |
| **Stick Clicks** | Left Stick Click (LS), Right Stick Click (RS) |
| **System Buttons** | Start, Back, Xbox Guide |

## Overview

```
┌─────────────────────┐     ┌──────────────────┐     ┌──────────────────┐
│   Xbox One/Series   │────▶│   Raspberry Pi   │────▶│   Xbox 360       │
│   Controller        │ USB │   Zero           │ USB │   Console        │
│   (or Bluetooth)    │     │   (Gadget Mode)  │     │                  │
└─────────────────────┘     └──────────────────┘     └──────────────────┘
```

The Pi Zero acts as a translator:
- **Input side**: Reads from Xbox One/Series controller via USB (using a USB hub) or Bluetooth
- **Output side**: Emulates a genuine wired Xbox 360 controller using USB gadget mode

## Why Raw-Gadget?

This project uses [raw-gadget](https://github.com/xairy/raw-gadget) for low-level USB emulation instead of the standard libcomposite/g_hid approach. Here's why:

**The Problem with libcomposite/g_hid:**
- Standard HID gadget mode creates a device that appears in `lsusb` with the correct VID/PID (0x045E:0x028E)
- However, the Linux `xpad` driver (used on PCs) and Xbox 360 consoles **do not recognize it**
- No `/dev/input/js*` device is created, and the controller doesn't work

**Why xpad doesn't bind:**
- Xbox 360 wired controllers use a **vendor-specific class** (0xFF), not standard HID
- They require specific **control transfers** during initialization (vendor requests)
- The **report descriptor format** is non-standard (not a typical HID descriptor)
- The **input report format** must be exactly 20 bytes with a specific structure
- **Periodic keep-alive** messages are needed
- **Endpoint behavior** must match the original controller precisely

**The raw-gadget solution:**
- Provides low-level control over USB descriptors, endpoints, and control transfers
- Allows implementation of the exact Xbox 360 wired protocol
- Based on [CasperVM/360-raw-gadget](https://github.com/CasperVM/360-raw-gadget), proven to work with xpad
- Enables proper binding on both Linux PCs and Xbox 360 consoles

## Hardware Requirements

- **Raspberry Pi Zero** or **Pi Zero 2 W** (with OTG-capable USB port)
- **Micro USB OTG cable** or **USB-C cable** (depending on Pi model)
- **USB Hub** (optional, but recommended for connecting source controller via USB)
- **Xbox One or Series controller**
- **MicroSD card** with Raspberry Pi OS Lite

### Wiring Diagram

```
For USB input method (recommended):

    ┌─────────────────────────────────────┐
    │            USB OTG Hub              │
    │  (with both host and device ports)  │
    └─────────┬─────────────┬─────────────┘
              │             │
    ┌─────────▼─────┐       │
    │ Xbox One/     │       │ USB Device
    │ Series Ctrl   │       │ to Xbox 360
    └───────────────┘       ▼
                        Xbox 360 Console

Alternative: Single USB port (Bluetooth input)

    Pi Zero ──USB──▶ Xbox 360 Console
      │
      └── Bluetooth ──▶ Xbox One/Series Controller
```

## Software Installation

### 1. Enable USB Gadget Mode

**IMPORTANT**: Only modify `/boot/config.txt` - DO NOT modify `/boot/cmdline.txt` as this can cause boot failures.

Add to `/boot/config.txt` (or `/boot/firmware/config.txt` on newer systems):
```bash
dtoverlay=dwc2
```

This is the safe, modern method recommended for Raspberry Pi OS Bookworm and newer.

### 2. Configure Modules to Load at Boot

Add kernel modules to `/etc/modules` to auto-load at boot:
```bash
echo "dwc2" | sudo tee -a /etc/modules
```

**Why this method?**: 
- Editing `/boot/cmdline.txt` can easily cause syntax errors leading to initramfs emergency shell
- Using `/etc/modules` is safer and more maintainable
- The `dtoverlay=dwc2` in `config.txt` properly enables the USB OTG hardware

### 3. Install System Dependencies

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install dependencies for raw-gadget and compilation
sudo apt install -y \
    python3-pip \
    python3-dev \
    git \
    build-essential \
    linux-headers-$(uname -r) \
    raspberrypi-kernel-headers

# Install Python packages
sudo pip3 install evdev pyusb

# Optional: For Bluetooth support
sudo apt install -y bluetooth bluez python3-dbus
```

### 4. Build and Install raw-gadget Module

The raw-gadget kernel module provides low-level USB gadget control:

```bash
# Clone raw-gadget repository
cd /tmp
git clone https://github.com/xairy/raw-gadget.git
cd raw-gadget

# Build the module
make

# Install the module
sudo make install

# Load the module
sudo modprobe raw_gadget

# Add to /etc/modules for auto-loading
echo "raw_gadget" | sudo tee -a /etc/modules
```

**Verify installation:**
```bash
# Check if module is loaded
lsmod | grep raw_gadget

# Check if device is available
ls -l /dev/raw-gadget
```

### 5. Clone and Install Project

```bash
git clone https://github.com/JeremyLakeyJr/Pizero-to-X360.git
cd Pizero-to-X360

# Build the C emulator
make build

# Run installation script
sudo ./scripts/install.sh
```

The `install.sh` script will:
- Configure boot settings safely (no cmdline.txt modifications)
- Verify raw-gadget installation
- Build the raw-gadget emulator binary
- Install all dependencies
- Optionally create and enable a systemd service for automatic startup

### 5. Enable Automatic Startup (Optional)

To make the emulator start automatically on boot:

```bash
# The systemd service is created during install.sh
# If you skipped it, you can enable it manually:
sudo systemctl enable xbox360-emulator.service
sudo systemctl start xbox360-emulator.service

# Check status
sudo systemctl status xbox360-emulator.service

# View logs
sudo journalctl -u xbox360-emulator.service -f
```

### 6. Manual Operation

If you prefer to run manually instead of using the systemd service:

```bash
# After reboot, the raw-gadget module should auto-load
# Run the emulator (it will set up the USB gadget automatically)
sudo ./bin/xbox360_raw_emulator

# The Python input handler runs automatically within the emulator
# Connect Pi Zero to Xbox 360 or PC via USB
```

## Project Structure

```
Pizero-to-X360/
├── README.md                    # This file
├── LICENSE                      # GPL v3 License
├── Makefile                     # Build and install automation
├── src/
│   ├── 360_raw_emulator.c       # C emulator using raw-gadget
│   ├── xbox360_emulator.py      # Python input bridge (reads source controller)
│   ├── xbox360_descriptors.py   # USB descriptors for Xbox 360 controller
│   ├── input_handler.py         # Input reading from source controller
│   └── report_formatter.py      # Format input reports
├── bin/
│   └── xbox360_raw_emulator     # Compiled C emulator binary
├── scripts/
│   ├── setup_gadget.sh          # Load raw-gadget module
│   ├── teardown_gadget.sh       # Unload raw-gadget module
│   └── install.sh               # Full installation script
└── docs/
    ├── USB_PROTOCOL.md          # Xbox 360 USB protocol documentation
    ├── TROUBLESHOOTING.md       # Common issues and solutions
    └── DEVELOPMENT.md           # Development guide
```

## Xbox 360 Controller USB Protocol

### USB Descriptors

The Xbox 360 wired controller uses these identifiers:
- **Vendor ID**: `0x045E` (Microsoft)
- **Product ID**: `0x028E` (Xbox 360 Controller)
- **Device Class**: `0xFF` (Vendor Specific)
- **Device SubClass**: `0xFF`
- **Device Protocol**: `0xFF`

### Input Report Format (20 bytes)

```
Offset  Size  Description
------  ----  -----------
0       1     Report type (0x00)
1       1     Report size (0x14 = 20)
2-3     2     Button bitmap
4       1     Left trigger (0-255)
5       1     Right trigger (0-255)
6-7     2     Left stick X (signed 16-bit)
8-9     2     Left stick Y (signed 16-bit)
10-11   2     Right stick X (signed 16-bit)
12-13   2     Right stick Y (signed 16-bit)
14-19   6     Reserved (padding)
```

### Button Bitmap (bytes 2-3)

```
Bit   Button
---   ------
0     D-pad Up
1     D-pad Down
2     D-pad Left
3     D-pad Right
4     Start
5     Back
6     Left Stick Click
7     Right Stick Click
8     Left Bumper (LB)
9     Right Bumper (RB)
10    Xbox Guide
11    (Reserved)
12    A
13    B
14    X
15    Y
```

## Testing

### Step 1: Verify raw-gadget Module

```bash
# Check if raw-gadget module is loaded
lsmod | grep raw_gadget

# Check if device node exists
ls -l /dev/raw-gadget

# Expected output:
# crw------- 1 root root 10, XX MMM DD HH:MM /dev/raw-gadget
```

### Step 2: Test on PC First (Recommended)

Before connecting to an Xbox 360 console, **always test on a Linux PC first**. PCs provide much better diagnostic output via dmesg and sysfs.

**Connect and check:**
```bash
# On the Pi Zero, run the emulator
sudo ./bin/xbox360_raw_emulator

# On PC, after connecting Pi Zero via USB:
# Check USB device enumeration
lsusb | grep "Microsoft.*Xbox"
# Expected: Bus XXX Device XXX: ID 045e:028e Microsoft Corp. Xbox 360 Controller

# Check xpad driver binding (CRITICAL TEST)
dmesg | grep -i xpad
# Expected output:
# [   XX.XXXXXX] usb X-X: new full-speed USB device number X using xhci_hcd
# [   XX.XXXXXX] input: Microsoft X-Box 360 pad as /dev/input/eventX
# [   XX.XXXXXX] xpad X-X:1.0: Xbox 360 controller

# Verify input device created
cat /proc/bus/input/devices | grep -A 10 "Xbox"
# Should show "Xbox 360" device with event handler

# List event devices
ls -l /dev/input/event*
# One of these should be the Xbox 360 controller

# Find the correct event device
cat /proc/bus/input/devices | grep -B 5 "Xbox"
# Note the event number (e.g., event4)
```

**Test input events:**
```bash
# Install evtest if not available
sudo apt install evtest

# Test the Xbox 360 controller
sudo evtest /dev/input/eventX  # Replace X with your event number

# Press buttons on source Xbox One controller
# You should see events appearing in evtest output

# Alternative: Test with jstest (for joystick interface)
sudo apt install joystick
sudo jstest /dev/input/js0
```

**Test in a game or online tester:**
- Open https://html5gamepad.com in browser
- Press buttons on source controller
- Gamepad should appear and respond

**If xpad doesn't bind:**
- Check dmesg for USB errors
- Verify raw-gadget module is loaded
- Ensure C emulator is running (check with `ps aux | grep xbox360`)
- See [TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) for detailed diagnostics

### Step 3: Test on Xbox 360 Console

Only after PC testing succeeds:

1. **Power off Xbox 360 completely**
2. Connect Pi Zero to Xbox 360 USB port
3. Power on Xbox 360
4. Controller LED should light up and show player number (1-4)
5. Test button inputs in Xbox 360 dashboard or game

**Note:** Xbox 360 consoles are more strict than PCs about timing and protocol compliance. Always verify on PC first.

## Traffic Capture

To reverse-engineer or debug the USB protocol:

### On Linux:
```bash
# Load usbmon
sudo modprobe usbmon

# Capture with Wireshark
wireshark -i usbmon1
```

### On Windows:
Use USBPcap with Wireshark to capture traffic from a real Xbox 360 controller.

## Known Limitations

1. **Single USB Port**: Pi Zero has one USB port in OTG mode. Use Bluetooth input or a special hub.
2. **Timing Critical**: Xbox 360 expects reports every ~8ms. High system load may cause issues.
3. **PC Testing First**: Always test on a Linux PC before trying with Xbox 360 console.
4. **Raw-gadget Required**: Standard libcomposite/g_hid does not work for xpad binding.

## Troubleshooting

### Boot Issues

**Problem**: Pi Zero boots into initramfs emergency shell after configuration

**Solution**: This was caused by older installation methods that modified `/boot/cmdline.txt`. The fix:

1. **DO NOT** modify `/boot/cmdline.txt` - use only `/boot/config.txt`
2. Add `dtoverlay=dwc2` to `/boot/config.txt` instead
3. Use `/etc/modules` to auto-load kernel modules (not cmdline.txt)

**Why the old method failed**: 
- Adding `modules-load=dwc2` to cmdline.txt can create parsing errors
- Any typo, extra newline, or formatting issue in cmdline.txt causes boot failure
- Modern Raspberry Pi OS (Bookworm/Trixie) is more sensitive to cmdline.txt syntax

**Recovery from boot failure**:
```bash
# If stuck in initramfs, check cmdline.txt
cat /boot/cmdline.txt
# or
cat /boot/firmware/cmdline.txt

# Remove any modules-load= parameters if present
# The entire cmdline.txt should be a single line with no newlines
```

### USB Gadget Not Working

**Problem**: USB gadget doesn't appear when connected

**Checklist**:
1. Verify `dtoverlay=dwc2` is in `/boot/config.txt`
2. Check raw-gadget module is loaded: `lsmod | grep raw_gadget`
3. Verify UDC is available: `ls /sys/class/udc/`
4. Check emulator is running: `ps aux | grep xbox360`
5. Review logs: `sudo journalctl -u xbox360-emulator -n 50`

**Problem**: Device appears in lsusb but xpad doesn't bind

**This is the main issue that raw-gadget solves!** Check:
1. Run `dmesg | grep -i xpad` - should show "Xbox 360 controller" messages
2. Run `ls /dev/input/js*` - should show joystick device(s)
3. Verify raw-gadget module is loaded (not libcomposite)
4. Check emulator binary is running: `ps aux | grep 360_raw_emulator`
5. Test with `evtest` to confirm events work

**Problem**: "USB_RAW_IOCTL_INIT failed: Invalid argument" error

**Cause**: The UDC (USB Device Controller) name or driver name is incorrect.

**Solution**:
1. Check your UDC name: `ls /sys/class/udc/` (should show `20980000.usb` on Pi Zero)
2. The C emulator now auto-detects the UDC name
3. If still failing, verify dwc2 is loaded: `lsmod | grep dwc2`

**UDC Names by Platform**:
| Platform | UDC Name |
|----------|----------|
| Pi Zero / Zero W / Zero 2 W | `20980000.usb` |
| Pi 4 | `fe980000.usb` |

For more troubleshooting, see [TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md).

## Contributing

Contributions are welcome! Please see [DEVELOPMENT.md](docs/DEVELOPMENT.md) for guidelines.

## References

- [Xbox 360 Controller USB Data](https://www.partsnotincluded.com/understanding-the-xbox-360-wired-controllers-usb-data/)
- [Linux USB Gadget](https://www.kernel.org/doc/html/latest/usb/gadget.html)
- [ConfigFS Composite USB Gadgets](https://www.kernel.org/doc/Documentation/usb/gadget_configfs.txt)
- [CasperVM/360-raw-gadget](https://github.com/CasperVM/360-raw-gadget)

## License

This project is licensed under the GNU General Public License v3.0 - see the [LICENSE](LICENSE) file for details.

## Disclaimer

This project is for educational and personal use only. Xbox, Xbox 360, and Xbox One are trademarks of Microsoft Corporation. This project is not affiliated with or endorsed by Microsoft.
