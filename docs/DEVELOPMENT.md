# Development Guide

This guide is for developers who want to contribute to or modify the Xbox 360 Controller Emulator.

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                    xbox360_emulator.py                          │
│                    (Main Application)                           │
├─────────────────┬──────────────────────┬───────────────────────┤
│                 │                      │                       │
│  input_handler  │   report_formatter   │  Xbox360GadgetConfigFS│
│  .py            │   .py                │  (USB Gadget)         │
│                 │                      │                       │
│  ┌───────────┐  │  ┌────────────────┐  │  ┌─────────────────┐  │
│  │ evdev     │  │  │ InputReport    │  │  │ configfs        │  │
│  │ reading   │  │  │ OutputReport   │  │  │ /dev/hidgX      │  │
│  └───────────┘  │  └────────────────┘  │  └─────────────────┘  │
│                 │                      │                       │
└─────────────────┴──────────────────────┴───────────────────────┘
         │                   │                      │
         ▼                   ▼                      ▼
┌─────────────────┐ ┌────────────────┐ ┌───────────────────────────┐
│ Xbox One/Series │ │ 20-byte report │ │ USB Device (to Xbox 360)  │
│ Controller      │ │ formatting     │ │ VID:045E PID:028E         │
└─────────────────┘ └────────────────┘ └───────────────────────────┘
```

## Module Descriptions

### xbox360_descriptors.py

Contains all USB descriptor definitions for the Xbox 360 controller:
- Device descriptor
- Configuration descriptor
- Interface descriptor
- Endpoint descriptors
- String descriptors
- Button/axis constants

### report_formatter.py

Handles input/output report formatting:
- `InputReport`: Builds 20-byte input reports
- `OutputReport`: Parses rumble and LED commands
- Helper functions for report manipulation

### input_handler.py

Reads from source controllers via Linux evdev:
- Auto-detection of Xbox controllers
- Event processing
- Axis calibration and scaling
- Callback-based state updates

### xbox360_emulator.py

Main application that ties everything together:
- USB gadget setup via configfs
- Main event loop
- Input-to-output mapping
- Signal handling

## Development Setup

### Prerequisites

```bash
# Development dependencies
sudo apt install python3-pip python3-venv

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install evdev pyusb pylint pytest
```

### Running Tests

```bash
# Basic tests (no hardware required)
make test

# Or manually
python3 src/xbox360_descriptors.py
python3 src/report_formatter.py

# Dry-run mode (doesn't configure actual gadget)
python3 src/xbox360_emulator.py --dry-run --debug
```

### Code Style

- Python 3.6+ compatible
- Follow PEP 8
- Document all public functions
- Keep modules self-contained

```bash
# Lint check
make lint

# Or manually
python3 -m py_compile src/*.py
pylint src/*.py
```

## Implementing Raw-Gadget Support

For better Xbox 360 compatibility, raw-gadget provides lower-level USB control. Here's how to add it:

### Why Raw-Gadget?

The configfs HID gadget has limitations:
- Can't customize low-level USB descriptors
- Can't handle arbitrary vendor control requests
- May not match Xbox 360's exact expectations

Raw-gadget allows:
- Custom device descriptors
- Handling of vendor-specific control transfers
- Precise endpoint management

### Raw-Gadget Prerequisites

```bash
# Build and install raw-gadget kernel module
git clone https://github.com/xairy/raw-gadget.git
cd raw-gadget/raw_gadget
make
sudo insmod raw_gadget.ko
```

### Raw-Gadget Example

```python
"""
Example raw-gadget implementation skeleton.
"""

import os
import struct
import fcntl

# IOCTL commands (from raw_gadget.h)
USB_RAW_IOCTL_INIT = 0x40085500
USB_RAW_IOCTL_RUN = 0x5501
USB_RAW_IOCTL_EVENT_FETCH = 0x80085502
USB_RAW_IOCTL_EP0_WRITE = 0x40085503
USB_RAW_IOCTL_EP0_READ = 0x80085504
USB_RAW_IOCTL_EP_ENABLE = 0xC0105505
USB_RAW_IOCTL_EP_DISABLE = 0x40045506
USB_RAW_IOCTL_EP_WRITE = 0x40105507
USB_RAW_IOCTL_EP_READ = 0x80105508

class RawGadget:
    """Raw-gadget interface for low-level USB control."""
    
    def __init__(self, device="/dev/raw-gadget"):
        self.fd = os.open(device, os.O_RDWR)
    
    def init(self, driver_name, device_name):
        """Initialize the gadget."""
        # Pack init struct: driver_name(128) + device_name(128) + speed(1)
        data = struct.pack("128s128sB", 
                          driver_name.encode(),
                          device_name.encode(),
                          3)  # USB_SPEED_HIGH
        fcntl.ioctl(self.fd, USB_RAW_IOCTL_INIT, data)
    
    def run(self):
        """Start the gadget."""
        fcntl.ioctl(self.fd, USB_RAW_IOCTL_RUN)
    
    def fetch_event(self):
        """Fetch the next USB event."""
        buf = bytearray(256)
        fcntl.ioctl(self.fd, USB_RAW_IOCTL_EVENT_FETCH, buf)
        return buf
    
    def ep0_write(self, data):
        """Write to endpoint 0."""
        # Pack: length(4) + data
        buf = struct.pack("I", len(data)) + data + bytes(256 - len(data))
        fcntl.ioctl(self.fd, USB_RAW_IOCTL_EP0_WRITE, buf)
    
    def close(self):
        os.close(self.fd)
```

## USB Traffic Capture

### On Linux (with real Xbox 360 controller)

```bash
# Load usbmon
sudo modprobe usbmon

# Find the bus number
lsusb | grep Xbox
# Example output: Bus 001 Device 005: ID 045e:028e Microsoft Corp. Xbox360 Controller

# Capture traffic
sudo cat /sys/kernel/debug/usb/usbmon/1u > traffic.txt

# Or with Wireshark
sudo wireshark -i usbmon1
```

### On Windows

1. Install [USBPcap](https://desowin.org/usbpcap/)
2. Open Wireshark
3. Select USBPcap interface
4. Filter: `usb.idVendor == 0x045e && usb.idProduct == 0x028e`

### Analyzing Captures

Look for:
- Enumeration sequence (descriptors, set address, set configuration)
- Control transfers (vendor-specific requests)
- Input reports (interrupt IN transfers)
- Output reports (interrupt OUT transfers)

## Adding New Input Sources

To add support for a new controller type:

1. Create a new handler class in `input_handler.py`:

```python
class PS4InputHandler:
    """Handle input from PS4 controller."""
    
    # PS4 vendor ID
    VENDOR_ID = 0x054C
    
    def __init__(self, device_path=None):
        # Similar to InputHandler
        pass
    
    def _process_event(self, event):
        # Map PS4 button codes to ControllerState
        pass
```

2. Add detection in the main emulator:

```python
def _detect_input_handler(self):
    """Auto-detect and create appropriate input handler."""
    # Try Xbox first
    try:
        return InputHandler()
    except RuntimeError:
        pass
    
    # Try PS4
    try:
        return PS4InputHandler()
    except RuntimeError:
        pass
    
    return None
```

## Testing Without Hardware

### Dry-Run Mode

```bash
python3 src/xbox360_emulator.py --dry-run --debug
```

This simulates the gadget without actually configuring USB.

### Mock Input

Create a test script that generates fake input events:

```python
"""Generate test input for the emulator."""
import time
from input_handler import ControllerState

def generate_test_pattern(callback):
    """Simulate button presses."""
    state = ControllerState()
    
    # Press A
    state.a = True
    callback(state)
    time.sleep(0.5)
    
    # Release A, press B
    state.a = False
    state.b = True
    callback(state)
    time.sleep(0.5)
```

## Performance Optimization

### Current Bottlenecks

1. **Python GIL**: Single-threaded input/output
2. **File I/O**: Writing to `/dev/hidgX`
3. **evdev polling**: Event loop overhead

### Optimization Ideas

1. **Separate threads**: Use threading for input and output
2. **Native extension**: Write critical path in C with ctypes
3. **Async I/O**: Use asyncio for non-blocking operations
4. **Report rate limiting**: Only send when changed (with keepalive)

### C Extension Example

For maximum performance, write the report loop in C:

```c
/* report_loop.c - Native report sender */
#include <Python.h>
#include <fcntl.h>
#include <unistd.h>

static PyObject* send_report(PyObject* self, PyObject* args) {
    const char* device;
    const char* data;
    Py_ssize_t len;
    
    if (!PyArg_ParseTuple(args, "sy#", &device, &data, &len))
        return NULL;
    
    int fd = open(device, O_WRONLY);
    if (fd < 0) {
        PyErr_SetFromErrno(PyExc_OSError);
        return NULL;
    }
    
    ssize_t written = write(fd, data, len);
    close(fd);
    
    return PyLong_FromSsize_t(written);
}
```

## Contributing

1. Fork the repository
2. Create a feature branch
3. Write tests for new functionality
4. Ensure all tests pass
5. Submit a pull request

### Pull Request Guidelines

- Keep changes focused and minimal
- Update documentation for user-facing changes
- Add tests for bug fixes
- Follow existing code style

## Resources

- [Linux USB Gadget Documentation](https://www.kernel.org/doc/html/latest/usb/gadget.html)
- [ConfigFS Composite Gadgets](https://www.kernel.org/doc/Documentation/usb/gadget_configfs.txt)
- [raw-gadget Project](https://github.com/xairy/raw-gadget)
- [xpad Driver Source](https://github.com/torvalds/linux/blob/master/drivers/input/joystick/xpad.c)
- [evdev Documentation](https://python-evdev.readthedocs.io/)
