# Xbox 360 USB Controller Protocol Documentation

This document describes the USB protocol used by the wired Xbox 360 controller, based on reverse engineering and public documentation.

## USB Device Descriptors

### Device Descriptor

| Field | Value | Description |
|-------|-------|-------------|
| bLength | 18 | Descriptor length |
| bDescriptorType | 0x01 | Device descriptor |
| bcdUSB | 0x0200 | USB 2.0 |
| bDeviceClass | 0xFF | Vendor Specific |
| bDeviceSubClass | 0xFF | Vendor Specific |
| bDeviceProtocol | 0xFF | Vendor Specific |
| bMaxPacketSize0 | 8 | Max packet size for EP0 |
| idVendor | 0x045E | Microsoft Corporation |
| idProduct | 0x028E | Xbox 360 Controller |
| bcdDevice | 0x0114 | Device version 1.14 |
| iManufacturer | 1 | "©Microsoft Corporation" |
| iProduct | 2 | "Controller" |
| iSerialNumber | 3 | "" (empty) |
| bNumConfigurations | 1 | Single configuration |

### Configuration Descriptor

The Xbox 360 controller has a single configuration with multiple interfaces:

- **Interface 0**: Main controller interface (input/output)
- **Interface 1**: Headset interface (optional)
- **Interface 2**: Security interface (for wireless/authentication)
- **Interface 3**: Unknown (possibly reserved)

For basic wired operation, only Interface 0 is needed.

### Interface 0 (Main Controller)

| Field | Value | Description |
|-------|-------|-------------|
| bInterfaceNumber | 0 | |
| bAlternateSetting | 0 | |
| bNumEndpoints | 2 | IN and OUT |
| bInterfaceClass | 0xFF | Vendor Specific |
| bInterfaceSubClass | 0x5D | Xbox 360 specific |
| bInterfaceProtocol | 0x01 | Input interface |

### Endpoint 1 IN (Input Reports)

| Field | Value | Description |
|-------|-------|-------------|
| bEndpointAddress | 0x81 | EP 1 IN |
| bmAttributes | 0x03 | Interrupt |
| wMaxPacketSize | 32 | |
| bInterval | 4 | 4ms polling |

### Endpoint 2 OUT (Output Reports)

| Field | Value | Description |
|-------|-------|-------------|
| bEndpointAddress | 0x02 | EP 2 OUT |
| bmAttributes | 0x03 | Interrupt |
| wMaxPacketSize | 32 | |
| bInterval | 8 | 8ms polling |

## Input Report Format

The Xbox 360 controller sends 20-byte input reports via Endpoint 1 IN at ~125Hz (every 8ms).

### Report Structure

```
Offset  Size  Type     Description
------  ----  ----     -----------
0       1     uint8    Report type (always 0x00)
1       1     uint8    Report size (always 0x14 = 20)
2       2     uint16   Button bitmap (little endian)
4       1     uint8    Left trigger (0-255)
5       1     uint8    Right trigger (0-255)
6       2     int16    Left stick X (-32768 to 32767)
8       2     int16    Left stick Y (-32768 to 32767)
10      2     int16    Right stick X (-32768 to 32767)
12      2     int16    Right stick Y (-32768 to 32767)
14      6     -        Reserved (zeros)
```

### Button Bitmap (Bytes 2-3)

```
Bit   Button              Byte.Bit
---   ------              --------
0     D-pad Up            2.0
1     D-pad Down          2.1
2     D-pad Left          2.2
3     D-pad Right         2.3
4     Start               2.4
5     Back                2.5
6     Left Stick Click    2.6
7     Right Stick Click   2.7
8     Left Bumper (LB)    3.0
9     Right Bumper (RB)   3.1
10    Xbox Guide          3.2
11    (Reserved)          3.3
12    A                   3.4
13    B                   3.5
14    X                   3.6
15    Y                   3.7
```

### Analog Values

- **Triggers**: 8-bit unsigned (0 = released, 255 = fully pressed)
- **Sticks**: 16-bit signed (-32768 = full left/down, 0 = center, 32767 = full right/up)
  - Note: Y-axis is typically inverted (positive = up) compared to some other controllers

### Example Reports

**Idle (all neutral):**
```
00 14 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00
```

**A button pressed:**
```
00 14 00 10 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00
        ^^-- Bit 12 (A) set
```

**Left stick full right:**
```
00 14 00 00 00 00 FF 7F 00 00 00 00 00 00 00 00 00 00 00 00
                  ^^^^^-- 0x7FFF = 32767
```

## Output Report Format

The Xbox 360 console sends output reports via Endpoint 2 OUT for rumble and LED control.

### Rumble Report

```
Offset  Size  Description
------  ----  -----------
0       1     Report type (0x00)
1       1     Report size (0x08)
2       1     Reserved (0x00)
3       1     Left motor (big, low frequency, 0-255)
4       1     Right motor (small, high frequency, 0-255)
5       3     Reserved (0x00)
```

### LED Control Report

```
Offset  Size  Description
------  ----  -----------
0       1     Report type (0x01)
1       1     Report size (0x03)
2       1     LED pattern (see below)
```

### LED Patterns

| Value | Pattern |
|-------|---------|
| 0x00 | All off |
| 0x01 | All blinking |
| 0x02 | Flash 1 then on |
| 0x03 | Flash 2 then on |
| 0x04 | Flash 3 then on |
| 0x05 | Flash 4 then on |
| 0x06 | Player 1 on |
| 0x07 | Player 2 on |
| 0x08 | Player 3 on |
| 0x09 | Player 4 on |
| 0x0A | Rotating |
| 0x0B | Fast blinking |
| 0x0C | Slow blinking |
| 0x0D | Alternating |

## Control Transfers

The Xbox 360 console sends various vendor-specific control requests during enumeration and operation.

### Known Control Requests

| bmRequestType | bRequest | wValue | wIndex | Description |
|---------------|----------|--------|--------|-------------|
| 0xC1 | 0x01 | 0x0100 | 0x0000 | Get device capabilities |
| 0x41 | 0x00 | 0x0000 | 0x0000 | Set LED pattern |

Most control requests are optional and the controller will work without implementing them. The console may send these for advanced features like wireless authentication.

## Timing Requirements

- **Input reports**: Should be sent at ~125Hz (every 8ms)
- **Idle reports**: Must continue sending even when no buttons pressed
- **Startup**: Console expects first report within ~100ms of enumeration

## References

1. [Understanding the Xbox 360 Wired Controller's USB Data](https://www.partsnotincluded.com/understanding-the-xbox-360-wired-controllers-usb-data/)
2. [Linux xpad driver source](https://github.com/torvalds/linux/blob/master/drivers/input/joystick/xpad.c)
3. [USB HID Specification](https://www.usb.org/hid)
