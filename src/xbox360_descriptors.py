#!/usr/bin/env python3
"""
Xbox 360 Controller USB Descriptors

This module contains all USB descriptors needed to emulate a genuine
wired Xbox 360 controller. Based on reverse engineering data from:
https://www.partsnotincluded.com/understanding-the-xbox-360-wired-controllers-usb-data/

The Xbox 360 wired controller uses vendor-specific class with custom HID-like reports.
"""

# USB Vendor and Product IDs for Xbox 360 Controller
VENDOR_ID = 0x045E   # Microsoft Corporation
PRODUCT_ID = 0x028E  # Xbox 360 Controller

# USB descriptor constants
USB_BCD = 0x0200     # USB 2.00
DEVICE_BCD = 0x0114  # Device release 1.14

# Device class codes (vendor-specific)
DEVICE_CLASS = 0xFF
DEVICE_SUBCLASS = 0xFF
DEVICE_PROTOCOL = 0xFF

# String descriptors
MANUFACTURER_STRING = "©Microsoft Corporation"
PRODUCT_STRING = "Controller"
SERIAL_STRING = ""

# Interface class codes
INTERFACE_CLASS = 0xFF      # Vendor Specific
INTERFACE_SUBCLASS = 0x5D   # Xbox 360 specific
INTERFACE_PROTOCOL = 0x01   # Input interface

# Interface 1 (headset) - if needed
INTERFACE_SUBCLASS_HEADSET = 0x5D
INTERFACE_PROTOCOL_HEADSET = 0x03

# Endpoint addresses
EP_IN_ADDR = 0x81     # Endpoint 1 IN (input reports)
EP_OUT_ADDR = 0x02    # Endpoint 2 OUT (rumble/LED commands)

# Endpoint attributes
EP_TYPE_INTERRUPT = 0x03
EP_INTERVAL_IN = 4    # 4ms polling interval
EP_INTERVAL_OUT = 8   # 8ms polling interval
EP_MAX_PACKET = 32    # Maximum packet size


class Xbox360Descriptors:
    """
    Container for Xbox 360 controller USB descriptors.
    
    These descriptors mimic a genuine Microsoft Xbox 360 wired controller
    to ensure compatibility with Xbox 360 consoles.
    """
    
    # Device Descriptor (18 bytes)
    DEVICE_DESCRIPTOR = bytes([
        0x12,        # bLength: 18 bytes
        0x01,        # bDescriptorType: Device
        0x00, 0x02,  # bcdUSB: USB 2.00
        0xFF,        # bDeviceClass: Vendor Specific
        0xFF,        # bDeviceSubClass: Vendor Specific
        0xFF,        # bDeviceProtocol: Vendor Specific
        0x08,        # bMaxPacketSize0: 8 bytes
        0x5E, 0x04,  # idVendor: 0x045E (Microsoft) - little endian
        0x8E, 0x02,  # idProduct: 0x028E (Xbox 360 Controller) - little endian
        0x14, 0x01,  # bcdDevice: 1.14 - little endian
        0x01,        # iManufacturer: String index 1
        0x02,        # iProduct: String index 2
        0x03,        # iSerialNumber: String index 3
        0x01,        # bNumConfigurations: 1
    ])
    
    # Configuration Descriptor header (9 bytes)
    # Full configuration includes interfaces and endpoints
    CONFIG_DESCRIPTOR = bytes([
        0x09,        # bLength: 9 bytes
        0x02,        # bDescriptorType: Configuration
        0x30, 0x00,  # wTotalLength: 48 bytes (little endian)
        0x01,        # bNumInterfaces: 1
        0x01,        # bConfigurationValue: 1
        0x00,        # iConfiguration: None
        0xA0,        # bmAttributes: Bus powered, remote wakeup
        0xFA,        # bMaxPower: 500mA (250 * 2)
    ])
    
    # Interface Descriptor (9 bytes)
    INTERFACE_DESCRIPTOR = bytes([
        0x09,        # bLength: 9 bytes
        0x04,        # bDescriptorType: Interface
        0x00,        # bInterfaceNumber: 0
        0x00,        # bAlternateSetting: 0
        0x02,        # bNumEndpoints: 2
        0xFF,        # bInterfaceClass: Vendor Specific
        0x5D,        # bInterfaceSubClass: Xbox 360 specific
        0x01,        # bInterfaceProtocol: Input
        0x00,        # iInterface: None
    ])
    
    # Xbox 360 specific interface descriptor (vendor descriptor)
    # This is a 20-byte vendor-specific descriptor that follows the interface
    VENDOR_INTERFACE_DESCRIPTOR = bytes([
        0x10,        # bLength: 16 bytes (sometimes 0x14 = 20)
        0x21,        # bDescriptorType: Vendor (0x21)
        0x10, 0x01,  # Some version? 0x0110
        0x01,        # bCountryCode or similar
        0x25,        # Payload size indicator
        0x81,        # Endpoint address (EP1 IN)
        0x14,        # Report size (20 bytes)
        0x00,        # Reserved
        0x00,        # Reserved
        0x00,        # Reserved
        0x00,        # Reserved
        0x13,        # Payload size indicator
        0x02,        # Endpoint address (EP2 OUT)
        0x08,        # Report size
        0x00,        # Reserved
    ])
    
    # Endpoint Descriptor for EP1 IN (7 bytes)
    EP_IN_DESCRIPTOR = bytes([
        0x07,        # bLength: 7 bytes
        0x05,        # bDescriptorType: Endpoint
        0x81,        # bEndpointAddress: EP 1 IN
        0x03,        # bmAttributes: Interrupt
        0x20, 0x00,  # wMaxPacketSize: 32 bytes (little endian)
        0x04,        # bInterval: 4ms
    ])
    
    # Endpoint Descriptor for EP2 OUT (7 bytes)
    EP_OUT_DESCRIPTOR = bytes([
        0x07,        # bLength: 7 bytes
        0x05,        # bDescriptorType: Endpoint
        0x02,        # bEndpointAddress: EP 2 OUT
        0x03,        # bmAttributes: Interrupt
        0x20, 0x00,  # wMaxPacketSize: 32 bytes (little endian)
        0x08,        # bInterval: 8ms
    ])
    
    @classmethod
    def get_full_config_descriptor(cls):
        """
        Build the complete configuration descriptor including all
        interface and endpoint descriptors.
        
        Returns:
            bytes: Complete configuration descriptor
        """
        config = bytearray(cls.CONFIG_DESCRIPTOR)
        config.extend(cls.INTERFACE_DESCRIPTOR)
        config.extend(cls.VENDOR_INTERFACE_DESCRIPTOR)
        config.extend(cls.EP_IN_DESCRIPTOR)
        config.extend(cls.EP_OUT_DESCRIPTOR)
        
        # Update wTotalLength
        total_len = len(config)
        config[2] = total_len & 0xFF
        config[3] = (total_len >> 8) & 0xFF
        
        return bytes(config)
    
    @classmethod
    def get_string_descriptor(cls, index: int, langid: int = 0x0409) -> bytes:
        """
        Get a string descriptor by index.
        
        Args:
            index: String descriptor index (0 = languages, 1+ = strings)
            langid: Language ID (default: US English)
            
        Returns:
            bytes: String descriptor in USB format
        """
        if index == 0:
            # Language ID descriptor
            return bytes([0x04, 0x03, 0x09, 0x04])  # US English
        
        strings = {
            1: MANUFACTURER_STRING,
            2: PRODUCT_STRING,
            3: SERIAL_STRING,
        }
        
        string = strings.get(index, "")
        encoded = string.encode('utf-16-le')
        length = 2 + len(encoded)
        
        return bytes([length, 0x03]) + encoded


# Input report button bit positions
class Xbox360Buttons:
    """Button bit positions in the input report button bitmap."""
    DPAD_UP = 0
    DPAD_DOWN = 1
    DPAD_LEFT = 2
    DPAD_RIGHT = 3
    START = 4
    BACK = 5
    LEFT_STICK = 6
    RIGHT_STICK = 7
    LB = 8
    RB = 9
    GUIDE = 10
    # Bit 11 reserved
    A = 12
    B = 13
    X = 14
    Y = 15


# Output report types (from Xbox 360 to controller)
class Xbox360OutputReports:
    """Output report identifiers for rumble and LED control."""
    LED_CONTROL = 0x01
    RUMBLE = 0x00


# LED patterns
class Xbox360LEDPatterns:
    """LED animation patterns that can be sent to the controller."""
    OFF = 0x00
    BLINK_ALL = 0x01
    BLINK_1 = 0x02
    BLINK_2 = 0x03
    BLINK_3 = 0x04
    BLINK_4 = 0x05
    SOLID_1 = 0x06
    SOLID_2 = 0x07
    SOLID_3 = 0x08
    SOLID_4 = 0x09
    ROTATING = 0x0A
    BLINK_FAST = 0x0B
    BLINK_SLOW = 0x0C
    ALTERNATING = 0x0D


if __name__ == "__main__":
    # Debug: print descriptors in hex
    print("Device Descriptor:")
    print(" ".join(f"{b:02X}" for b in Xbox360Descriptors.DEVICE_DESCRIPTOR))
    
    print("\nFull Configuration Descriptor:")
    config = Xbox360Descriptors.get_full_config_descriptor()
    print(" ".join(f"{b:02X}" for b in config))
    
    print(f"\nTotal config length: {len(config)} bytes")
    
    print("\nString Descriptors:")
    for i in range(4):
        desc = Xbox360Descriptors.get_string_descriptor(i)
        print(f"  Index {i}: {' '.join(f'{b:02X}' for b in desc)}")
