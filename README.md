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

Add to `/boot/config.txt`:
```bash
dtoverlay=dwc2
```

Add to `/boot/cmdline.txt` (after `rootwait`):
```bash
modules-load=dwc2
```

### 2. Install Dependencies

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install dependencies
sudo apt install -y python3-pip python3-dev git
sudo pip3 install evdev pyusb

# Optional: For Bluetooth support
sudo apt install -y bluetooth bluez python3-dbus
```

### 3. Load Required Kernel Modules

```bash
sudo modprobe libcomposite
sudo modprobe usb_f_hid
```

### 4. Clone and Install

```bash
git clone https://github.com/JeremyLakeyJr/Pizero-to-X360.git
cd Pizero-to-X360
sudo ./scripts/setup_gadget.sh
sudo python3 src/xbox360_emulator.py
```

## Project Structure

```
Pizero-to-X360/
├── README.md                    # This file
├── LICENSE                      # GPL v3 License
├── Makefile                     # Build and install automation
├── src/
│   ├── xbox360_emulator.py      # Main emulator application
│   ├── xbox360_descriptors.py   # USB descriptors for Xbox 360 controller
│   ├── input_handler.py         # Input reading from source controller
│   └── report_formatter.py      # Format input reports
├── scripts/
│   ├── setup_gadget.sh          # Configure USB gadget via configfs
│   ├── teardown_gadget.sh       # Remove USB gadget configuration
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

### Step 1: Verify Gadget Setup

```bash
# Check if gadget is configured
ls /sys/kernel/config/usb_gadget/xbox360/

# Check if device is recognized
dmesg | tail -20
```

### Step 2: Test on PC First

Before connecting to an Xbox 360, test the emulator on a PC:
```bash
# On PC, check for new USB device
lsusb | grep Microsoft

# Check input events
cat /proc/bus/input/devices
```

### Step 3: Test on Xbox 360

1. Power off Xbox 360
2. Connect Pi Zero to Xbox 360 USB port
3. Power on Xbox 360
4. Controller LED should indicate player number

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
3. **Vendor Requests**: Xbox 360 sends specific vendor control requests that must be handled.
4. **Authentication**: Xbox 360 may perform authentication checks (typically not enforced for wired).

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
