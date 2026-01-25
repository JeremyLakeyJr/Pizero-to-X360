/*
 * Xbox 360 Controller Emulator using raw-gadget
 * 
 * Based on CasperVM/360-raw-gadget (https://github.com/CasperVM/360-raw-gadget)
 * Adapted for Pi Zero with Python input bridge integration
 * 
 * This emulator creates a USB device that properly emulates an Xbox 360 wired
 * controller. The xpad driver (on Linux) and Xbox 360 consoles will recognize
 * and bind to this device correctly.
 * 
 * Architecture:
 * - C program handles USB protocol via raw-gadget (descriptors, control transfers, endpoints)
 * - Python reads input from source controller (Xbox One/Series) via evdev
 * - Communication via pipe: Python writes 20-byte reports to stdin of C program
 * - C program sends reports to host via USB interrupt endpoint
 * 
 * Compilation:
 *   gcc -o xbox360_raw_emulator 360_raw_emulator.c -lpthread
 * 
 * Usage:
 *   sudo ./xbox360_raw_emulator
 *   # In another terminal (or via systemd):
 *   python3 xbox360_emulator.py | sudo ./xbox360_raw_emulator
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <stdbool.h>
#include <unistd.h>
#include <fcntl.h>
#include <errno.h>
#include <signal.h>
#include <pthread.h>
#include <dirent.h>
#include <sys/ioctl.h>
#include <sys/select.h>
#include <linux/usb/ch9.h>

/* Raw-gadget includes - definitions must match kernel's raw_gadget.h */
#define USB_RAW_IOCTL_INIT              _IOW('U', 0, struct usb_raw_init)
#define USB_RAW_IOCTL_RUN               _IO('U', 1)
#define USB_RAW_IOCTL_EVENT_FETCH       _IOR('U', 2, struct usb_raw_event)
#define USB_RAW_IOCTL_EP0_WRITE         _IOW('U', 3, struct usb_raw_ep_io)
#define USB_RAW_IOCTL_EP0_READ          _IOWR('U', 4, struct usb_raw_ep_io)
#define USB_RAW_IOCTL_EP_ENABLE         _IOW('U', 5, struct usb_endpoint_descriptor)
#define USB_RAW_IOCTL_EP_DISABLE        _IOW('U', 6, uint32_t)
#define USB_RAW_IOCTL_EP_WRITE          _IOW('U', 7, struct usb_raw_ep_io)
#define USB_RAW_IOCTL_EP_READ           _IOWR('U', 8, struct usb_raw_ep_io)
#define USB_RAW_IOCTL_CONFIGURE         _IO('U', 9)
#define USB_RAW_IOCTL_VBUS_DRAW         _IOW('U', 10, uint32_t)
#define USB_RAW_IOCTL_EPS_INFO          _IOR('U', 11, struct usb_raw_eps_info)

#define USB_RAW_IO_FLAGS_ZERO       0x0001
#define USB_RAW_IO_FLAGS_MASK       0x0001

/* Maximum number of non-control endpoints */
#define USB_RAW_EPS_NUM_MAX     30

/* Maximum length of UDC endpoint name */
#define USB_RAW_EP_NAME_MAX     16

/* Used as addr in struct usb_raw_ep_info if endpoint accepts any address */
#define USB_RAW_EP_ADDR_ANY     0xff

/* Raw-gadget event types */
enum usb_raw_event_type {
    USB_RAW_EVENT_INVALID = 0,
    USB_RAW_EVENT_CONNECT = 1,
    USB_RAW_EVENT_CONTROL = 2,
    USB_RAW_EVENT_SUSPEND = 3,
    USB_RAW_EVENT_RESUME = 4,
    USB_RAW_EVENT_RESET = 5,
    USB_RAW_EVENT_DISCONNECT = 6,
};

/* Raw-gadget event structure */
struct usb_raw_event {
    uint32_t type;
    uint32_t length;
    uint8_t data[0];
};

/* Endpoint capabilities from struct usb_ep_caps */
struct usb_raw_ep_caps {
    uint32_t type_control : 1;
    uint32_t type_iso     : 1;
    uint32_t type_bulk    : 1;
    uint32_t type_int     : 1;
    uint32_t dir_in       : 1;
    uint32_t dir_out      : 1;
};

/* Endpoint limits from struct usb_ep */
struct usb_raw_ep_limits {
    uint16_t maxpacket_limit;
    uint16_t max_streams;
    uint32_t reserved;
};

/* Information about a gadget endpoint */
struct usb_raw_ep_info {
    uint8_t name[USB_RAW_EP_NAME_MAX];
    uint32_t addr;
    struct usb_raw_ep_caps caps;
    struct usb_raw_ep_limits limits;
};

/* Container for all endpoint info */
struct usb_raw_eps_info {
    struct usb_raw_ep_info eps[USB_RAW_EPS_NUM_MAX];
};

/* Maximum length of driver_name/device_name in the usb_raw_init struct. */
#define UDC_NAME_LENGTH_MAX 128

struct usb_raw_init {
    uint8_t driver_name[UDC_NAME_LENGTH_MAX];
    uint8_t device_name[UDC_NAME_LENGTH_MAX];
    uint8_t speed;
};

struct usb_raw_ep_io {
    uint16_t ep;
    uint16_t flags;
    uint32_t length;
    uint8_t data[0];
};

/* Xbox 360 Controller USB Descriptors */
#define XBOX360_VENDOR_ID       0x045E  /* Microsoft */
#define XBOX360_PRODUCT_ID      0x028E  /* Xbox 360 Controller */
#define XBOX360_DEVICE_VERSION  0x0114  /* Version 1.14 */

#define XBOX360_REPORT_SIZE     20      /* 20-byte input report */

/* Vendor request response sizes */
#define XBOX360_CAPABILITIES_MAX_SIZE  20   /* Max size for capabilities response */
#define XBOX360_SECURITY_MAX_SIZE      32   /* Max size for security response */

/* Debug output interval (log every Nth report to avoid spam) */
#define DEBUG_REPORT_LOG_INTERVAL      1000

/*
 * Number of initial idle reports to send immediately after SET_CONFIGURATION.
 * Xbox 360 consoles expect the first input report within ~100ms of enumeration.
 * Sending multiple reports ensures reliable controller recognition.
 */
#define INITIAL_IDLE_REPORTS_COUNT     3

/*
 * Idle report constant - all buttons released, sticks centered.
 * 
 * Xbox 360 protocol requires the first input report to be sent within
 * ~100ms of SET_CONFIGURATION. This idle report is sent immediately
 * after endpoint configuration to satisfy this timing requirement.
 * 
 * Format (20 bytes):
 *   Byte 0: Report type (0x00)
 *   Byte 1: Report size (0x14 = 20)
 *   Bytes 2-19: All zeros (no buttons, centered sticks, no triggers)
 */
static const uint8_t idle_report[XBOX360_REPORT_SIZE] = {
    0x00, 0x14,  /* Report type and size */
    0x00, 0x00,  /* Button bitmap (no buttons pressed) */
    0x00, 0x00,  /* Left/Right triggers (released) */
    0x00, 0x00,  /* Left stick X (centered) */
    0x00, 0x00,  /* Left stick Y (centered) */
    0x00, 0x00,  /* Right stick X (centered) */
    0x00, 0x00,  /* Right stick Y (centered) */
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00  /* Reserved padding */
};

/* USB String Descriptor Indices */
#define STRING_ID_MANUFACTURER  1
#define STRING_ID_PRODUCT       2
#define STRING_ID_SERIAL_NUM    3
#define STRING_ID_IF3           4

/* Endpoint addresses - direction bits only, number assigned dynamically */
#define EP_IN_ADDRESS           USB_DIR_IN   /* Will be updated with actual endpoint number */
#define EP_OUT_ADDRESS          USB_DIR_OUT  /* Will be updated with actual endpoint number */

/* Device Descriptor */
static struct usb_device_descriptor device_descriptor = {
    .bLength            = USB_DT_DEVICE_SIZE,
    .bDescriptorType    = USB_DT_DEVICE,
    .bcdUSB             = __constant_cpu_to_le16(0x0200), /* USB 2.0 */
    .bDeviceClass       = 0xFF,  /* Vendor specific */
    .bDeviceSubClass    = 0xFF,
    .bDeviceProtocol    = 0xFF,
    .bMaxPacketSize0    = 64,    /* Max packet size for endpoint 0 (high-speed) */
    .idVendor           = __constant_cpu_to_le16(XBOX360_VENDOR_ID),
    .idProduct          = __constant_cpu_to_le16(XBOX360_PRODUCT_ID),
    .bcdDevice          = 0,     /* bcdDevice: 0 (as in CasperVM) */
    .iManufacturer      = STRING_ID_MANUFACTURER,
    .iProduct           = STRING_ID_PRODUCT,
    .iSerialNumber      = STRING_ID_SERIAL_NUM,  /* String ID 3 */
    .bNumConfigurations = 1,
};

/*
 * Xbox 360 Configuration Descriptor - Full descriptor matching CasperVM/360-raw-gadget
 * 
 * This is the complete configuration descriptor matching a real Xbox 360
 * wired controller. Using raw bytes ensures exact byte-for-byte match
 * with the expected format, avoiding any padding issues from C structs.
 * 
 * The descriptor includes all 4 interfaces as found on genuine Xbox 360 controllers:
 * - Configuration descriptor (9 bytes)
 * - Interface 0: Control data (9 + 17 + 7 + 7 = 40 bytes)
 * - Interface 1: Headset/Audio (9 + 27 + 7 + 7 + 7 + 7 = 64 bytes)
 * - Interface 2: Unknown (9 + 9 + 7 = 25 bytes)
 * - Interface 3: Security method (9 + 6 = 15 bytes)
 * Total: 153 bytes (0x99)
 * 
 * The vendor-specific descriptors (type 0x21 for IF0-IF2, 0x41 for IF3) are 
 * essential for the xpad driver and Xbox 360 console to recognize this as 
 * a valid Xbox 360 controller.
 * 
 * Based on CasperVM/360-raw-gadget (https://github.com/CasperVM/360-raw-gadget)
 */
#define CONFIG_DESC_SIZE 153

static uint8_t config_descriptor_raw[CONFIG_DESC_SIZE] = {
    /* Configuration Descriptor (9 bytes) */
    0x09,        /* bLength: 9 bytes */
    0x02,        /* bDescriptorType: Configuration */
    0x99, 0x00,  /* wTotalLength: 153 bytes (little endian) */
    0x04,        /* bNumInterfaces: 4 */
    0x01,        /* bConfigurationValue: 1 */
    0x00,        /* iConfiguration: None */
    0xA0,        /* bmAttributes: Bus powered, remote wakeup */
    0xFA,        /* bMaxPower: 500mA (250 * 2) */
    
    /* ========== Interface 0: Control Data ========== */
    /* Interface Descriptor (9 bytes) */
    0x09,        /* bLength: 9 bytes */
    0x04,        /* bDescriptorType: Interface */
    0x00,        /* bInterfaceNumber: 0 */
    0x00,        /* bAlternateSetting: 0 */
    0x02,        /* bNumEndpoints: 2 */
    0xFF,        /* bInterfaceClass: Vendor Specific */
    0x5D,        /* bInterfaceSubClass: Xbox 360 specific */
    0x01,        /* bInterfaceProtocol: Input interface */
    0x00,        /* iInterface: None */
    
    /* Xbox 360 IF0 Vendor-Specific Descriptor (17 bytes) */
    0x11,        /* bLength: 17 bytes */
    0x21,        /* bDescriptorType: Vendor (0x21) */
    0x00, 0x01,  /* Unknown1, Unknown2 */
    0x01,        /* Unknown3 */
    0x25,        /* Unknown4 */
    0x81,        /* bEndpointAddress: EP1 IN (0x81) */
    0x14,        /* bMaxDataSize: 20 bytes */
    0x00,        /* Unknown5 */
    0x00,        /* Unknown6 */
    0x00,        /* Unknown7 */
    0x00,        /* Unknown8 */
    0x13,        /* Unknown9 */
    0x01,        /* bEndpointAddress2: EP1 OUT (0x01) */
    0x08,        /* bMaxDataSize2: 8 bytes */
    0x00,        /* Unknown10 */
    0x00,        /* Unknown11 */
    
    /* Endpoint Descriptor for EP1 IN (7 bytes) */
    0x07,        /* bLength: 7 bytes */
    0x05,        /* bDescriptorType: Endpoint */
    0x81,        /* bEndpointAddress: EP 1 IN */
    0x03,        /* bmAttributes: Interrupt */
    0x20, 0x00,  /* wMaxPacketSize: 32 bytes (little endian) */
    0x04,        /* bInterval: 4ms */
    
    /* Endpoint Descriptor for EP1 OUT (7 bytes) */
    0x07,        /* bLength: 7 bytes */
    0x05,        /* bDescriptorType: Endpoint */
    0x01,        /* bEndpointAddress: EP 1 OUT */
    0x03,        /* bmAttributes: Interrupt */
    0x20, 0x00,  /* wMaxPacketSize: 32 bytes (little endian) */
    0x08,        /* bInterval: 8ms */
    
    /* ========== Interface 1: Headset/Audio ========== */
    /* Interface Descriptor (9 bytes) */
    0x09,        /* bLength: 9 bytes */
    0x04,        /* bDescriptorType: Interface */
    0x01,        /* bInterfaceNumber: 1 */
    0x00,        /* bAlternateSetting: 0 */
    0x04,        /* bNumEndpoints: 4 */
    0xFF,        /* bInterfaceClass: Vendor Specific */
    0x5D,        /* bInterfaceSubClass: Xbox 360 specific */
    0x03,        /* bInterfaceProtocol: Headset */
    0x00,        /* iInterface: None */
    
    /* Xbox 360 IF1 Vendor-Specific Descriptor (27 bytes) */
    0x1B,        /* bLength: 27 bytes */
    0x21,        /* bDescriptorType: Vendor (0x21) */
    0x00, 0x01,  /* Unknown1, Unknown2 */
    0x01,        /* Unknown3 */
    0x01,        /* Unknown4 */
    0x82,        /* bEndpointAddress: EP2 IN */
    0x40,        /* bMaxDataSize: 64 bytes */
    0x01,        /* Unknown5 */
    0x02,        /* bEndpointAddress2: EP2 OUT */
    0x20,        /* bMaxDataSize2: 32 bytes */
    0x16,        /* Unknown6 */
    0x83,        /* bEndpointAddress3: EP3 IN */
    0x00,        /* bMaxDataSize3: 0 bytes */
    0x00,        /* Unknown7 */
    0x00,        /* Unknown8 */
    0x00,        /* Unknown9 */
    0x00,        /* Unknown10 */
    0x00,        /* Unknown11 */
    0x16,        /* Unknown12 */
    0x03,        /* bEndpointAddress4: EP3 OUT */
    0x00,        /* bMaxDataSize4: 0 bytes */
    0x00,        /* Unknown13 */
    0x00,        /* Unknown14 */
    0x00,        /* Unknown15 */
    0x00,        /* Unknown16 */
    0x00,        /* Unknown17 */
    
    /* Endpoint Descriptor for EP2 IN (7 bytes) */
    0x07,        /* bLength: 7 bytes */
    0x05,        /* bDescriptorType: Endpoint */
    0x82,        /* bEndpointAddress: EP 2 IN */
    0x03,        /* bmAttributes: Interrupt */
    0x20, 0x00,  /* wMaxPacketSize: 32 bytes */
    0x02,        /* bInterval: 2ms */
    
    /* Endpoint Descriptor for EP2 OUT (7 bytes) */
    0x07,        /* bLength: 7 bytes */
    0x05,        /* bDescriptorType: Endpoint */
    0x02,        /* bEndpointAddress: EP 2 OUT */
    0x03,        /* bmAttributes: Interrupt */
    0x20, 0x00,  /* wMaxPacketSize: 32 bytes */
    0x04,        /* bInterval: 4ms */
    
    /* Endpoint Descriptor for EP3 IN (7 bytes) */
    0x07,        /* bLength: 7 bytes */
    0x05,        /* bDescriptorType: Endpoint */
    0x83,        /* bEndpointAddress: EP 3 IN */
    0x03,        /* bmAttributes: Interrupt */
    0x20, 0x00,  /* wMaxPacketSize: 32 bytes */
    0x08,        /* bInterval: 8 frames (was 64 which caused kernel warning; 8ms at full-speed) */
    
    /* Endpoint Descriptor for EP3 OUT (7 bytes) */
    0x07,        /* bLength: 7 bytes */
    0x05,        /* bDescriptorType: Endpoint */
    0x03,        /* bEndpointAddress: EP 3 OUT */
    0x03,        /* bmAttributes: Interrupt */
    0x20, 0x00,  /* wMaxPacketSize: 32 bytes */
    0x10,        /* bInterval: 16ms */
    
    /* ========== Interface 2: Unknown ========== */
    /* Interface Descriptor (9 bytes) */
    0x09,        /* bLength: 9 bytes */
    0x04,        /* bDescriptorType: Interface */
    0x02,        /* bInterfaceNumber: 2 */
    0x00,        /* bAlternateSetting: 0 */
    0x01,        /* bNumEndpoints: 1 */
    0xFF,        /* bInterfaceClass: Vendor Specific */
    0x5D,        /* bInterfaceSubClass: Xbox 360 specific */
    0x02,        /* bInterfaceProtocol: Unknown */
    0x00,        /* iInterface: None */
    
    /* Xbox 360 IF2 Vendor-Specific Descriptor (9 bytes) */
    0x09,        /* bLength: 9 bytes */
    0x21,        /* bDescriptorType: Vendor (0x21) */
    0x00, 0x01,  /* Unknown1, Unknown2 */
    0x01,        /* Unknown3 */
    0x22,        /* Unknown4 */
    0x84,        /* bEndpointAddress: EP4 IN */
    0x07,        /* bMaxDataSize: 7 bytes */
    0x00,        /* Unknown5 */
    
    /* Endpoint Descriptor for EP4 IN (7 bytes) */
    0x07,        /* bLength: 7 bytes */
    0x05,        /* bDescriptorType: Endpoint */
    0x84,        /* bEndpointAddress: EP 4 IN */
    0x03,        /* bmAttributes: Interrupt */
    0x20, 0x00,  /* wMaxPacketSize: 32 bytes */
    0x10,        /* bInterval: 16ms */
    
    /* ========== Interface 3: Security Method ========== */
    /* Interface Descriptor (9 bytes) */
    0x09,        /* bLength: 9 bytes */
    0x04,        /* bDescriptorType: Interface */
    0x03,        /* bInterfaceNumber: 3 */
    0x00,        /* bAlternateSetting: 0 */
    0x00,        /* bNumEndpoints: 0 */
    0xFF,        /* bInterfaceClass: Vendor Specific */
    0xFD,        /* bInterfaceSubClass: Security */
    0x13,        /* bInterfaceProtocol: Security method */
    0x04,        /* iInterface: String ID 4 */
    
    /* Xbox 360 IF3 Vendor-Specific Descriptor (6 bytes) */
    0x06,        /* bLength: 6 bytes */
    0x41,        /* bDescriptorType: Vendor (0x41) - Different for IF3! */
    0x00, 0x01,  /* Unknown1, Unknown2 */
    0x01,        /* Unknown3 */
    0x03,        /* Unknown4 */
};

/* 
 * Endpoint descriptors for USB_RAW_IOCTL_EP_ENABLE
 * These are kept as structures for the ioctl calls but the raw descriptor
 * above is used for GET_DESCRIPTOR responses.
 */
static struct usb_endpoint_descriptor ep_in_desc = {
    .bLength          = USB_DT_ENDPOINT_SIZE,
    .bDescriptorType  = USB_DT_ENDPOINT,
    .bEndpointAddress = EP_IN_ADDRESS,
    .bmAttributes     = USB_ENDPOINT_XFER_INT,
    .wMaxPacketSize   = __constant_cpu_to_le16(32),
    .bInterval        = 4,  /* Poll every 8ms (2^(4-1) = 8) */
};

static struct usb_endpoint_descriptor ep_out_desc = {
    .bLength          = USB_DT_ENDPOINT_SIZE,
    .bDescriptorType  = USB_DT_ENDPOINT,
    .bEndpointAddress = EP_OUT_ADDRESS,
    .bmAttributes     = USB_ENDPOINT_XFER_INT,
    .wMaxPacketSize   = __constant_cpu_to_le16(32),
    .bInterval        = 8,  /* Poll every 64ms */
};

/* String Descriptors */
static struct usb_string_descriptor_with_data {
    uint8_t bLength;
    uint8_t bDescriptorType;
    uint16_t wData[1];  /* English (US) */
} __attribute__((packed)) string_lang = {
    .bLength = 4,
    .bDescriptorType = USB_DT_STRING,
    .wData = {0x0409},
};

/* Manufacturer: "©Microsoft Corporation" */
static uint8_t manufacturer_string[] = {
    54, USB_DT_STRING,
    0xA9, 0x00,  /* © */
    'M', 0, 'i', 0, 'c', 0, 'r', 0, 'o', 0, 's', 0, 'o', 0, 'f', 0, 't', 0, ' ', 0,
    'C', 0, 'o', 0, 'r', 0, 'p', 0, 'o', 0, 'r', 0, 'a', 0, 't', 0, 'i', 0, 'o', 0, 'n', 0,
};

/* Product: "Controller" */
static uint8_t product_string[] = {
    24, USB_DT_STRING,
    'C', 0, 'o', 0, 'n', 0, 't', 0, 'r', 0, 'o', 0, 'l', 0, 'l', 0, 'e', 0, 'r', 0,
};

/* Serial Number: "08FEC93" */
static uint8_t serial_string[] = {
    18, USB_DT_STRING,
    '0', 0, '8', 0, 'F', 0, 'E', 0, 'C', 0, '9', 0, '3', 0,
};

/* Interface 3 String: Security method description */
static uint8_t if3_string[] = {
    182, USB_DT_STRING,
    'X', 0, 'b', 0, 'o', 0, 'x', 0, ' ', 0, 'S', 0, 'e', 0, 'c', 0, 'u', 0, 'r', 0, 'i', 0, 't', 0, 'y', 0, ' ', 0,
    'M', 0, 'e', 0, 't', 0, 'h', 0, 'o', 0, 'd', 0, ' ', 0, '3', 0, ',', 0, ' ', 0,
    'V', 0, 'e', 0, 'r', 0, 's', 0, 'i', 0, 'o', 0, 'n', 0, ' ', 0, '1', 0, '.', 0, '0', 0, '0', 0, ',', 0, ' ', 0,
    0xA9, 0x00, ' ', 0, '2', 0, '0', 0, '0', 0, '5', 0, ' ', 0, 
    'M', 0, 'i', 0, 'c', 0, 'r', 0, 'o', 0, 's', 0, 'o', 0, 'f', 0, 't', 0, ' ', 0,
    'C', 0, 'o', 0, 'r', 0, 'p', 0, 'o', 0, 'r', 0, 'a', 0, 't', 0, 'i', 0, 'o', 0, 'n', 0, '.', 0, ' ', 0,
    'A', 0, 'l', 0, 'l', 0, ' ', 0, 'r', 0, 'i', 0, 'g', 0, 'h', 0, 't', 0, 's', 0, ' ', 0,
    'r', 0, 'e', 0, 's', 0, 'e', 0, 'r', 0, 'v', 0, 'e', 0, 'd', 0, '.', 0,
};

/*
 * USB Device Qualifier Descriptor (for full-speed operation support)
 * 
 * Required for USB 2.0 high-speed devices to provide fallback for full-speed
 * operation. The Pi Zero dwc2 gadget is full-speed max (12 Mbps), so this
 * descriptor is essential to avoid enumeration timeouts (-110 errors).
 * 
 * Must match the device descriptor's class/subclass/protocol values (0xFF/0xFF/0xFF)
 * for the Xbox 360 controller. Without this, hosts requesting device qualifier
 * may fail enumeration.
 * 
 * Reference: CasperVM/360-raw-gadget uses USB_SPEED_HIGH but includes
 * Device Qualifier for fallback support.
 */
static struct usb_qualifier_descriptor device_qualifier = {
    .bLength            = sizeof(struct usb_qualifier_descriptor),
    .bDescriptorType    = USB_DT_DEVICE_QUALIFIER,
    .bcdUSB             = __constant_cpu_to_le16(0x0200),
    .bDeviceClass       = 0xFF,  /* Vendor specific (must match device descriptor) */
    .bDeviceSubClass    = 0xFF,  /* Vendor specific (must match device descriptor) */
    .bDeviceProtocol    = 0xFF,  /* Vendor specific (must match device descriptor) */
    .bMaxPacketSize0    = 64,    /* EP0 max packet size */
    .bNumConfigurations = 1,
    .bRESERVED          = 0,
};

/* Global state */
static int fd = -1;              /* raw-gadget file descriptor */
static int ep_in_fd = -1;        /* EP1 IN file descriptor */
static int ep_out_fd = -1;       /* EP1 OUT file descriptor */
static volatile bool running = true;
static volatile bool endpoints_configured = false;  /* Set when endpoints are ready */
static volatile bool usb_connected = false;         /* Set when USB is connected */

/* Dynamically assigned endpoint addresses */
static uint8_t actual_ep_in_addr = 0;
static uint8_t actual_ep_out_addr = 0;

/* Debug mode flag */
static bool debug_mode = false;

/* Forward declaration for send_report (used by enable_endpoints_and_configure) */
static int send_report(const uint8_t *report, size_t length);

/*
 * Try to assign an endpoint address from the UDC to our endpoint descriptor.
 * Returns true if assignment was successful, false otherwise.
 */
static bool assign_ep_address(struct usb_raw_ep_info *info,
                              struct usb_endpoint_descriptor *ep) {
    /* Check if endpoint number is already assigned (non-zero) */
    if (usb_endpoint_num(ep) != 0)
        return false;  /* Already assigned */
    
    /* Check direction matches */
    if (usb_endpoint_dir_in(ep) && !info->caps.dir_in)
        return false;
    if (usb_endpoint_dir_out(ep) && !info->caps.dir_out)
        return false;
    
    /* Check max packet size is supported */
    if (usb_endpoint_maxp(ep) > info->limits.maxpacket_limit)
        return false;
    
    /* Check transfer type matches */
    switch (usb_endpoint_type(ep)) {
    case USB_ENDPOINT_XFER_BULK:
        if (!info->caps.type_bulk)
            return false;
        break;
    case USB_ENDPOINT_XFER_INT:
        if (!info->caps.type_int)
            return false;
        break;
    case USB_ENDPOINT_XFER_ISOC:
        if (!info->caps.type_iso)
            return false;
        break;
    case USB_ENDPOINT_XFER_CONTROL:
        if (!info->caps.type_control)
            return false;
        break;
    default:
        return false;
    }
    
    /* Assign the endpoint address */
    if (info->addr == USB_RAW_EP_ADDR_ANY) {
        /* UDC doesn't have fixed addresses, use a counter.
         * USB endpoint numbers use bits 0-3, so valid range is 1-15.
         * Note: setup_endpoints() is called only once from main() before any threads
         * are created, so thread safety is not a concern for addr_counter.
         */
        static int addr_counter = 1;
        if (addr_counter > 15) {
            return false;  /* No more endpoint addresses available */
        }
        ep->bEndpointAddress |= (uint8_t)(addr_counter & 0x0F);
        addr_counter++;
    } else {
        /* Use the UDC's fixed address (mask to ensure only endpoint number bits) */
        ep->bEndpointAddress |= (uint8_t)(info->addr & 0x0F);
    }
    
    return true;
}

/*
 * Query available endpoints from the UDC and assign addresses to our endpoints.
 * This must be called AFTER receiving USB_RAW_EVENT_CONNECT (not just after INIT).
 * Calling before the connect event results in "Invalid argument" error.
 */
static int setup_endpoints(void) {
    struct usb_raw_eps_info eps_info;
    memset(&eps_info, 0, sizeof(eps_info));
    
    int num_eps = ioctl(fd, USB_RAW_IOCTL_EPS_INFO, &eps_info);
    if (num_eps < 0) {
        perror("USB_RAW_IOCTL_EPS_INFO failed");
        return -1;
    }
    
    if (debug_mode) {
        printf("UDC has %d available endpoints:\n", num_eps);
        for (int i = 0; i < num_eps; i++) {
            printf("  EP %d: name=%s, addr=%u, type=%s%s%s, dir=%s%s, maxpacket=%u\n",
                   i,
                   eps_info.eps[i].name,
                   eps_info.eps[i].addr,
                   eps_info.eps[i].caps.type_iso ? "iso " : "",
                   eps_info.eps[i].caps.type_bulk ? "bulk " : "",
                   eps_info.eps[i].caps.type_int ? "int " : "",
                   eps_info.eps[i].caps.dir_in ? "in " : "",
                   eps_info.eps[i].caps.dir_out ? "out" : "",
                   eps_info.eps[i].limits.maxpacket_limit);
        }
    }
    
    /* Track which endpoints have been used */
    bool ep_used[USB_RAW_EPS_NUM_MAX] = {false};
    
    /* Assign endpoint addresses - each endpoint can only be used once */
    bool ep_in_assigned = false;
    bool ep_out_assigned = false;
    
    /* First pass: assign EP IN */
    for (int i = 0; i < num_eps && !ep_in_assigned; i++) {
        if (!ep_used[i] && assign_ep_address(&eps_info.eps[i], &ep_in_desc)) {
            ep_used[i] = true;
            ep_in_assigned = true;
            actual_ep_in_addr = ep_in_desc.bEndpointAddress;
            if (debug_mode) {
                printf("Assigned EP IN address: 0x%02X (using UDC endpoint %d)\n", actual_ep_in_addr, i);
            }
        }
    }
    
    /* Second pass: assign EP OUT (skipping already-used endpoints) */
    for (int i = 0; i < num_eps && !ep_out_assigned; i++) {
        if (!ep_used[i] && assign_ep_address(&eps_info.eps[i], &ep_out_desc)) {
            ep_used[i] = true;
            ep_out_assigned = true;
            actual_ep_out_addr = ep_out_desc.bEndpointAddress;
            if (debug_mode) {
                printf("Assigned EP OUT address: 0x%02X (using UDC endpoint %d)\n", actual_ep_out_addr, i);
            }
        }
    }
    
    if (!ep_in_assigned) {
        fprintf(stderr, "Error: Could not find suitable endpoint for EP IN\n");
        return -1;
    }
    
    if (!ep_out_assigned) {
        fprintf(stderr, "Error: Could not find suitable endpoint for EP OUT\n");
        return -1;
    }
    
    return 0;
}

/*
 * Enable endpoints and configure the device.
 * This is called when we receive SET_CONFIGURATION from the host.
 * Returns 0 on success, -1 on error.
 */
static int enable_endpoints_and_configure(void) {
    if (endpoints_configured) {
        /* Already configured */
        if (debug_mode) {
            printf("DEBUG: Endpoints already configured, skipping\n");
        }
        return 0;
    }
    
    if (debug_mode) {
        printf("DEBUG: Enabling endpoints...\n");
        printf("  EP IN descriptor: addr=0x%02X, type=%d, maxPacket=%d, bInterval=%d\n",
               ep_in_desc.bEndpointAddress, ep_in_desc.bmAttributes,
               __le16_to_cpu(ep_in_desc.wMaxPacketSize), ep_in_desc.bInterval);
        printf("  EP OUT descriptor: addr=0x%02X, type=%d, maxPacket=%d, bInterval=%d\n",
               ep_out_desc.bEndpointAddress, ep_out_desc.bmAttributes,
               __le16_to_cpu(ep_out_desc.wMaxPacketSize), ep_out_desc.bInterval);
    }
    
    ep_in_fd = ioctl(fd, USB_RAW_IOCTL_EP_ENABLE, &ep_in_desc);
    if (ep_in_fd < 0) {
        perror("Failed to enable EP IN");
        fprintf(stderr, "DEBUG: EP IN enable failed - addr=0x%02X, errno=%d\n", 
                ep_in_desc.bEndpointAddress, errno);
        return -1;
    }
    if (debug_mode) {
        printf("DEBUG: EP IN enabled (addr=0x%02X, handle=%d)\n", actual_ep_in_addr, ep_in_fd);
    }
    
    ep_out_fd = ioctl(fd, USB_RAW_IOCTL_EP_ENABLE, &ep_out_desc);
    if (ep_out_fd < 0) {
        perror("Failed to enable EP OUT");
        fprintf(stderr, "DEBUG: EP OUT enable failed - addr=0x%02X, errno=%d\n",
                ep_out_desc.bEndpointAddress, errno);
        return -1;
    }
    if (debug_mode) {
        printf("DEBUG: EP OUT enabled (addr=0x%02X, handle=%d)\n", actual_ep_out_addr, ep_out_fd);
    }
    
    /* Set VBUS power draw (500mA) */
    uint32_t power = 500;
    int vbus_ret = ioctl(fd, USB_RAW_IOCTL_VBUS_DRAW, &power);
    if (vbus_ret < 0) {
        perror("USB_RAW_IOCTL_VBUS_DRAW failed");
        /* Non-fatal, continue */
    } else if (debug_mode) {
        printf("DEBUG: VBUS power draw set to %dmA\n", power);
    }
    
    /* Configure device - USB_RAW_IOCTL_CONFIGURE requires 0 as argument */
    if (ioctl(fd, USB_RAW_IOCTL_CONFIGURE, 0) < 0) {
        perror("USB_RAW_IOCTL_CONFIGURE failed");
        return -1;
    }
    
    endpoints_configured = true;
    printf("Device configured and endpoints enabled\n");
    if (debug_mode) {
        printf("DEBUG: USB_RAW_IOCTL_CONFIGURE succeeded\n");
        printf("DEBUG: Ready to send/receive reports via EP handles: IN=%d, OUT=%d\n", 
               ep_in_fd, ep_out_fd);
    }
    
    /*
     * Send initial idle reports immediately after configuration.
     * 
     * The Xbox 360 console expects the first input report within ~100ms of
     * SET_CONFIGURATION. Without this, the console may timeout and fail to
     * recognize the controller (even though PCs are more lenient).
     * 
     * We send a few idle reports to ensure the console sees the controller
     * as active immediately after enumeration completes.
     */
    printf("Sending initial idle reports for Xbox 360 compatibility...\n");
    for (int i = 0; i < INITIAL_IDLE_REPORTS_COUNT; i++) {
        int ret = send_report(idle_report, XBOX360_REPORT_SIZE);
        if (ret < 0) {
            if (debug_mode) {
                printf("DEBUG: Initial idle report %d failed, errno=%d\n", i, errno);
            }
            /* Non-fatal - continue anyway */
        } else if (debug_mode) {
            printf("DEBUG: Sent initial idle report %d (%d bytes)\n", i, ret);
        }
        usleep(8000);  /* 8ms between reports (125Hz) */
    }
    
    return 0;
}

/*
 * Clean up endpoints and reset state for re-enumeration.
 * This is called on USB reset and disconnect events to prepare
 * for potential reconnection.
 */
static void cleanup_endpoints(void) {
    /* Disable endpoints if they were configured */
    if (endpoints_configured) {
        if (ep_in_fd >= 0) {
            ioctl(fd, USB_RAW_IOCTL_EP_DISABLE, ep_in_fd);
        }
        if (ep_out_fd >= 0) {
            ioctl(fd, USB_RAW_IOCTL_EP_DISABLE, ep_out_fd);
        }
    }
    endpoints_configured = false;
    ep_in_fd = -1;
    ep_out_fd = -1;
    
    /* Reset endpoint addresses so they can be reassigned.
     * EP_IN_ADDRESS and EP_OUT_ADDRESS are direction bits only (0x80, 0x00).
     * The endpoint number will be assigned dynamically when we receive
     * the next CONNECT event. */
    ep_in_desc.bEndpointAddress = EP_IN_ADDRESS;
    ep_out_desc.bEndpointAddress = EP_OUT_ADDRESS;
    actual_ep_in_addr = 0;
    actual_ep_out_addr = 0;
}

/* Signal handler for clean shutdown */
static void signal_handler(int sig) {
    printf("Received signal %d, shutting down...\n", sig);
    running = false;
}

/* Setup signal handlers */
static void setup_signals(void) {
    signal(SIGINT, signal_handler);
    signal(SIGTERM, signal_handler);
}

/* Open raw-gadget device */
static int open_raw_gadget(void) {
    fd = open("/dev/raw-gadget", O_RDWR);
    if (fd < 0) {
        perror("Failed to open /dev/raw-gadget");
        return -1;
    }
    printf("Opened raw-gadget device\n");
    return 0;
}

/* 
 * Detect the UDC (USB Device Controller) name for the current hardware.
 * 
 * On Raspberry Pi Zero / Zero 2 W, the UDC name is "20980000.usb" which
 * corresponds to the BCM2835 USB controller at memory address 0x20980000.
 * 
 * The UDC name can be found at runtime in /sys/class/udc/ directory.
 * 
 * Returns: pointer to static buffer containing UDC name, or NULL on error
 */
static const char* detect_udc_name(void) {
    static char udc_name[64];
    DIR *dir;
    struct dirent *entry;
    
    /* Try to read from /sys/class/udc directory using opendir/readdir */
    dir = opendir("/sys/class/udc");
    if (dir != NULL) {
        while ((entry = readdir(dir)) != NULL) {
            /* Skip . and .. entries */
            if (entry->d_name[0] == '.') {
                continue;
            }
            /* Found a UDC entry - copy the name safely */
            strncpy(udc_name, entry->d_name, sizeof(udc_name) - 1);
            udc_name[sizeof(udc_name) - 1] = '\0';  /* Ensure null termination */
            closedir(dir);
            return udc_name;
        }
        closedir(dir);
    }
    
    /*
     * Fallback to known Pi Zero UDC name.
     * 
     * "20980000.usb" is the UDC name for Raspberry Pi Zero, Zero W, and Zero 2 W.
     * This corresponds to the BCM2835/BCM2837 USB controller at:
     *   - Memory address: 0x20980000 (Pi Zero/Zero W with BCM2835)
     *   - Or 0x3f980000 on Pi 2/3 (BCM2836/BCM2837) but named consistently
     * 
     * The dwc2 driver must be loaded (dtoverlay=dwc2 in /boot/config.txt) 
     * for this UDC to be available.
     * 
     * Common UDC names by platform:
     *   - Pi Zero / Zero W / Zero 2 W: "20980000.usb"
     *   - Pi 4: "fe980000.usb" 
     *   - Virtual/testing: "dummy_udc.0"
     */
    printf("Warning: Could not detect UDC from /sys/class/udc, using default\n");
    return "20980000.usb";
}

/* Initialize raw-gadget with UDC */
static int init_raw_gadget(void) {
    const char *udc_name = detect_udc_name();
    
    if (udc_name == NULL) {
        fprintf(stderr, "Error: No UDC available. Make sure:\n");
        fprintf(stderr, "  1. dtoverlay=dwc2 is in /boot/config.txt\n");
        fprintf(stderr, "  2. dwc2 module is loaded (modprobe dwc2)\n");
        fprintf(stderr, "  3. Pi Zero is connected via USB data port\n");
        return -1;
    }
    
    printf("Using UDC: %s\n", udc_name);
    
    /*
     * Initialize raw-gadget with the detected UDC.
     * 
     * For the dwc2 driver on Raspberry Pi Zero, BOTH driver_name and device_name
     * should be set to the UDC name (e.g., "20980000.usb").
     * 
     * From raw_gadget.h documentation:
     * "At the same time the dwc2 driver that is used on Raspberry Pi Zero, has
     *  '20980000.usb' as both driver_name and device_name."
     * 
     * speed: USB_SPEED_HIGH (480 Mbps) - Matching CasperVM/360-raw-gadget
     * 
     * Note: Using wrong driver_name or device_name causes "Invalid argument" error
     * from USB_RAW_IOCTL_INIT.
     */
    struct usb_raw_init init;
    memset(&init, 0, sizeof(init));
    strncpy((char*)init.driver_name, udc_name, sizeof(init.driver_name) - 1);
    init.driver_name[sizeof(init.driver_name) - 1] = '\0';  /* Ensure null termination */
    strncpy((char*)init.device_name, udc_name, sizeof(init.device_name) - 1);
    init.device_name[sizeof(init.device_name) - 1] = '\0';  /* Ensure null termination */
    init.speed = USB_SPEED_HIGH;
    
    if (debug_mode) {
        printf("DEBUG: USB_RAW_IOCTL_INIT parameters:\n");
        printf("  driver_name: %s\n", init.driver_name);
        printf("  device_name: %s\n", init.device_name);
        printf("  speed: USB_SPEED_HIGH (%d)\n", init.speed);
        printf("DEBUG: Device descriptor: VID=0x%04X, PID=0x%04X, bMaxPacketSize0=%d\n",
               XBOX360_VENDOR_ID, XBOX360_PRODUCT_ID, device_descriptor.bMaxPacketSize0);
        printf("DEBUG: Device qualifier: class=0x%02X, subclass=0x%02X, protocol=0x%02X\n",
               device_qualifier.bDeviceClass, device_qualifier.bDeviceSubClass, 
               device_qualifier.bDeviceProtocol);
    }
    
    int ret = ioctl(fd, USB_RAW_IOCTL_INIT, &init);
    if (ret < 0) {
        perror("USB_RAW_IOCTL_INIT failed");
        fprintf(stderr, "\nTroubleshooting:\n");
        fprintf(stderr, "  - Check /sys/class/udc/ for available UDC names\n");
        fprintf(stderr, "  - Make sure dwc2 driver is loaded: lsmod | grep dwc2\n");
        fprintf(stderr, "  - Verify raw-gadget module is loaded: lsmod | grep raw_gadget\n");
        fprintf(stderr, "  - Expected UDC for Pi Zero: 20980000.usb\n");
        return -1;
    }
    printf("Initialized raw-gadget (driver: %s, device: %s, speed: high)\n", udc_name, udc_name);
    if (debug_mode) {
        printf("DEBUG: USB_RAW_IOCTL_INIT succeeded, ret=%d\n", ret);
    }
    return 0;
}

/* Handle control endpoint (EP0) requests */
static int handle_control_request(struct usb_ctrlrequest *setup) {
    uint8_t buffer[512];
    int length = 0;
    
    if (debug_mode) {
        printf("Control request: bRequestType=0x%02X, bRequest=0x%02X, wValue=0x%04X, wIndex=0x%04X, wLength=%d\n",
               setup->bRequestType, setup->bRequest, 
               __le16_to_cpu(setup->wValue), __le16_to_cpu(setup->wIndex),
               __le16_to_cpu(setup->wLength));
    }
    
    /* Handle standard requests */
    if ((setup->bRequestType & USB_TYPE_MASK) == USB_TYPE_STANDARD) {
        switch (setup->bRequest) {
            case USB_REQ_GET_DESCRIPTOR: {
                uint8_t desc_type = __le16_to_cpu(setup->wValue) >> 8;
                uint8_t desc_index = __le16_to_cpu(setup->wValue) & 0xFF;
                
                switch (desc_type) {
                    case USB_DT_DEVICE:
                        if (debug_mode) printf("  -> GET_DESCRIPTOR: DEVICE\n");
                        memcpy(buffer, &device_descriptor, sizeof(device_descriptor));
                        length = sizeof(device_descriptor);
                        break;
                        
                    case USB_DT_CONFIG:
                        if (debug_mode) printf("  -> GET_DESCRIPTOR: CONFIG\n");
                        memcpy(buffer, config_descriptor_raw, CONFIG_DESC_SIZE);
                        length = CONFIG_DESC_SIZE;
                        break;
                        
                    case USB_DT_STRING:
                        if (debug_mode) printf("  -> GET_DESCRIPTOR: STRING (index %d)\n", desc_index);
                        if (desc_index == 0) {
                            memcpy(buffer, &string_lang, 4);
                            length = 4;
                        } else if (desc_index == STRING_ID_MANUFACTURER) {
                            memcpy(buffer, manufacturer_string, manufacturer_string[0]);
                            length = manufacturer_string[0];
                        } else if (desc_index == STRING_ID_PRODUCT) {
                            memcpy(buffer, product_string, product_string[0]);
                            length = product_string[0];
                        } else if (desc_index == STRING_ID_SERIAL_NUM) {
                            memcpy(buffer, serial_string, serial_string[0]);
                            length = serial_string[0];
                        } else if (desc_index == STRING_ID_IF3) {
                            memcpy(buffer, if3_string, if3_string[0]);
                            length = if3_string[0];
                        } else {
                            if (debug_mode) printf("  -> Unknown string index %d\n", desc_index);
                            return -1;
                        }
                        break;
                    
                    case USB_DT_DEVICE_QUALIFIER:
                        if (debug_mode) printf("  -> GET_DESCRIPTOR: DEVICE_QUALIFIER\n");
                        memcpy(buffer, &device_qualifier, sizeof(device_qualifier));
                        length = sizeof(device_qualifier);
                        break;
                    
                    case USB_DT_OTHER_SPEED_CONFIG:
                        if (debug_mode) printf("  -> GET_DESCRIPTOR: OTHER_SPEED_CONFIG\n");
                        /* Return same config but with different descriptor type */
                        memcpy(buffer, config_descriptor_raw, CONFIG_DESC_SIZE);
                        buffer[1] = USB_DT_OTHER_SPEED_CONFIG;  /* Change descriptor type */
                        length = CONFIG_DESC_SIZE;
                        break;
                        
                    default:
                        if (debug_mode) printf("  -> Unknown descriptor type 0x%02X\n", desc_type);
                        return -1;
                }
                break;
            }
            
            case USB_REQ_SET_CONFIGURATION: {
                int config_value = __le16_to_cpu(setup->wValue);
                if (debug_mode) printf("  -> SET_CONFIGURATION: %d\n", config_value);
                
                /* Enable endpoints and configure device when configuration is set */
                if (config_value > 0) {
                    if (enable_endpoints_and_configure() < 0) {
                        fprintf(stderr, "Failed to enable endpoints on SET_CONFIGURATION\n");
                        return -1;
                    }
                }
                /* Acknowledge with zero-length packet */
                length = 0;
                break;
            }
            
            case USB_REQ_GET_INTERFACE:
                if (debug_mode) printf("  -> GET_INTERFACE\n");
                /* Return current alternate setting (always 0) */
                buffer[0] = 0;
                length = 1;
                break;
                
            case USB_REQ_SET_INTERFACE:
                if (debug_mode) printf("  -> SET_INTERFACE\n");
                length = 0;
                break;
                
            default:
                if (debug_mode) printf("  -> Unsupported standard request 0x%02X\n", setup->bRequest);
                return -1;
        }
    }
    /* 
     * Handle vendor-specific requests (Xbox 360 init)
     * 
     * Xbox 360 controllers and consoles use vendor requests during initialization:
     * - Request 0x01: Get device capabilities / init handshake
     * - Request 0xA9: Security chip / authentication related
     * - Request 0x00: Set LED pattern (some implementations)
     * 
     * Proper handling prevents enumeration timeouts (-110 errors) and allows
     * the xpad driver to bind correctly.
     * 
     * Reference: CasperVM/360-raw-gadget and real Xbox 360 controller traffic captures
     */
    else if ((setup->bRequestType & USB_TYPE_MASK) == USB_TYPE_VENDOR) {
        uint16_t wValue = __le16_to_cpu(setup->wValue);
        uint16_t wIndex = __le16_to_cpu(setup->wIndex);
        uint16_t wLength = __le16_to_cpu(setup->wLength);
        
        if (debug_mode) {
            printf("  -> VENDOR request 0x%02X (wValue=0x%04X, wIndex=0x%04X, wLength=%d)\n",
                   setup->bRequest, wValue, wIndex, wLength);
        }
        
        switch (setup->bRequest) {
            case 0x01:
                /*
                 * Vendor request 0x01: Get device capabilities / init handshake
                 * 
                 * The Xbox 360 console and xpad driver may send this during init.
                 * Return a minimal response to acknowledge the request.
                 * 
                 * bmRequestType=0xC1 (Device-to-host, Vendor, Interface)
                 * wValue=0x0100, wIndex=0x0000 typically
                 */
                if (setup->bRequestType & USB_DIR_IN) {
                    /* IN request - return capabilities data */
                    /* Real Xbox 360 controller returns ~20 bytes of capability data */
                    /* For now, return zeros which satisfies basic enumeration */
                    if (wLength > 0) {
                        memset(buffer, 0, wLength > sizeof(buffer) ? sizeof(buffer) : wLength);
                        length = wLength > XBOX360_CAPABILITIES_MAX_SIZE ? XBOX360_CAPABILITIES_MAX_SIZE : wLength;
                    } else {
                        length = 0;
                    }
                    if (debug_mode) printf("    -> Responding with %d bytes for capabilities\n", length);
                } else {
                    /* OUT request - acknowledge */
                    length = 0;
                }
                break;
                
            case 0xA9:
                /*
                 * Vendor request 0xA9: Security / authentication related
                 * 
                 * Used by Xbox 360 console for controller authentication.
                 * The security chip in real controllers handles this, but
                 * for basic PC compatibility, acknowledging is sufficient.
                 */
                if (setup->bRequestType & USB_DIR_IN) {
                    /* Return empty/zero response */
                    if (wLength > 0) {
                        memset(buffer, 0, wLength > sizeof(buffer) ? sizeof(buffer) : wLength);
                        length = wLength > XBOX360_SECURITY_MAX_SIZE ? XBOX360_SECURITY_MAX_SIZE : wLength;
                    } else {
                        length = 0;
                    }
                    if (debug_mode) printf("    -> Responding with %d bytes for security request\n", length);
                } else {
                    length = 0;
                }
                break;
                
            default:
                /*
                 * Unknown vendor request - acknowledge with empty response
                 * This prevents enumeration failures from unhandled requests
                 */
                if (debug_mode) printf("    -> Unknown vendor request, acknowledging\n");
                length = 0;
                break;
        }
    }
    /* Handle class-specific requests */
    else if ((setup->bRequestType & USB_TYPE_MASK) == USB_TYPE_CLASS) {
        if (debug_mode) printf("  -> CLASS request 0x%02X\n", setup->bRequest);
        length = 0;
    }
    else {
        if (debug_mode) printf("  -> Unknown request type 0x%02X\n", setup->bRequestType);
        return -1;
    }
    
    /* Send response */
    if (setup->bRequestType & USB_DIR_IN) {
        /* Limit to requested length */
        if (length > __le16_to_cpu(setup->wLength)) {
            length = __le16_to_cpu(setup->wLength);
        }
        
        struct usb_raw_ep_io *io = malloc(sizeof(*io) + length);
        if (!io) {
            perror("malloc failed");
            return -1;
        }
        
        io->ep = 0;
        io->flags = 0;
        io->length = length;
        if (length > 0) {
            memcpy(io->data, buffer, length);
        }
        
        int ret = ioctl(fd, USB_RAW_IOCTL_EP0_WRITE, io);
        free(io);
        
        if (ret < 0) {
            /* ESHUTDOWN (108) means transport endpoint shutdown - expected during disconnect */
            if (errno == ESHUTDOWN) {
                if (debug_mode) {
                    printf("EP0 write skipped (transport endpoint shutdown)\n");
                }
                return -1;
            }
            /* Also skip error if USB is already disconnected */
            if (!usb_connected) {
                if (debug_mode) {
                    printf("EP0 write skipped (USB not connected)\n");
                }
                return -1;
            }
            perror("EP0 write failed");
            return -1;
        }
    } else {
        /* OUT request - read status phase (completes the control transfer) */
        struct usb_raw_ep_io io = {0};
        io.ep = 0;
        io.flags = 0;
        io.length = 0;
        
        int ret = ioctl(fd, USB_RAW_IOCTL_EP0_READ, &io);
        if (ret < 0) {
            /* ESHUTDOWN (108) means transport endpoint shutdown - expected during disconnect */
            if (errno == ESHUTDOWN) {
                if (debug_mode) {
                    printf("EP0 read skipped (transport endpoint shutdown)\n");
                }
                return -1;
            }
            /* Also skip error if USB is already disconnected */
            if (!usb_connected) {
                if (debug_mode) {
                    printf("EP0 read skipped (USB not connected)\n");
                }
                return -1;
            }
            perror("EP0 read (status) failed");
            return -1;
        }
    }
    
    return 0;
}

/*
 * Main event loop for handling USB events.
 * This replaces the previous control_thread approach.
 * Events are fetched using USB_RAW_IOCTL_EVENT_FETCH.
 */
static void *event_loop_thread(void *arg) {
    if (debug_mode) {
        printf("Event loop thread started\n");
    }
    
    /* Buffer for event + control request data */
    struct {
        struct usb_raw_event event;
        uint8_t data[256];
    } event_buffer;
    
    while (running) {
        memset(&event_buffer, 0, sizeof(event_buffer));
        event_buffer.event.type = 0;
        event_buffer.event.length = sizeof(struct usb_ctrlrequest);
        
        /* Fetch next USB event */
        int ret = ioctl(fd, USB_RAW_IOCTL_EVENT_FETCH, &event_buffer);
        if (ret < 0) {
            if (errno == EINTR) {
                continue;
            }
            perror("USB_RAW_IOCTL_EVENT_FETCH failed");
            break;
        }
        
        switch (event_buffer.event.type) {
        case USB_RAW_EVENT_CONNECT:
            printf("USB connected\n");
            usb_connected = true;
            /* Now we can query endpoint info */
            if (setup_endpoints() < 0) {
                fprintf(stderr, "Failed to setup endpoints on connect\n");
                running = false;
            }
            break;
            
        case USB_RAW_EVENT_CONTROL:
            /* Handle control transfer */
            if (event_buffer.event.length >= sizeof(struct usb_ctrlrequest)) {
                struct usb_ctrlrequest *setup = (struct usb_ctrlrequest *)event_buffer.event.data;
                if (handle_control_request(setup) < 0) {
                    if (debug_mode) {
                        printf("Failed to handle control request\n");
                    }
                    /* TODO: Send STALL on EP0 for proper error handling */
                }
            }
            break;
            
        case USB_RAW_EVENT_SUSPEND:
            if (debug_mode) printf("USB suspended\n");
            break;
            
        case USB_RAW_EVENT_RESUME:
            if (debug_mode) printf("USB resumed\n");
            break;
            
        case USB_RAW_EVENT_RESET:
            printf("USB reset\n");
            /* On reset, clean up endpoints and prepare for re-enumeration */
            cleanup_endpoints();
            break;
            
        case USB_RAW_EVENT_DISCONNECT:
            printf("USB disconnected - waiting for reconnection...\n");
            usb_connected = false;
            /* Clean up endpoints to allow reconnection */
            cleanup_endpoints();
            /* Continue running - allow reconnection instead of exiting */
            break;
            
        default:
            if (debug_mode) {
                printf("Unknown event type: %d\n", event_buffer.event.type);
            }
            break;
        }
    }
    
    if (debug_mode) {
        printf("Event loop thread exiting\n");
    }
    return NULL;
}

/* Send input report via EP1 IN */
static int send_report(const uint8_t *report, size_t length) {
    static uint64_t report_count = 0;  /* Track total reports sent for debugging */
    
    if (!endpoints_configured || ep_in_fd < 0) {
        return -1;
    }
    
    struct usb_raw_ep_io *io = malloc(sizeof(*io) + length);
    if (!io) {
        return -1;
    }
    
    io->ep = ep_in_fd;  /* Use the handle returned from EP_ENABLE */
    io->flags = 0;
    io->length = length;
    memcpy(io->data, report, length);
    
    int ret = ioctl(fd, USB_RAW_IOCTL_EP_WRITE, io);
    
    if (ret >= 0) {
        report_count++;
        /* Log periodically to avoid spam (controlled by DEBUG_REPORT_LOG_INTERVAL) */
        if (debug_mode && (report_count % DEBUG_REPORT_LOG_INTERVAL == 0)) {
            printf("DEBUG: Sent %lu reports (last %d bytes)\n", 
                   (unsigned long)report_count, ret);
        }
    } else if (debug_mode && errno != EAGAIN && errno != EINTR) {
        printf("DEBUG: EP_WRITE failed, errno=%d (%s)\n", errno, strerror(errno));
    }
    
    free(io);
    
    return ret;
}

/* Receive output report (rumble/LED) via EP1 OUT 
 * TODO: Implement thread to read from EP1 OUT for rumble/LED commands
 * Currently unused but will be needed for bidirectional communication
 */
static int receive_output_report(uint8_t *buffer, size_t max_length) __attribute__((unused));
static int receive_output_report(uint8_t *buffer, size_t max_length) {
    if (!endpoints_configured || ep_out_fd < 0) {
        return -1;
    }
    
    struct usb_raw_ep_io *io = malloc(sizeof(*io) + max_length);
    if (!io) {
        return -1;
    }
    
    io->ep = ep_out_fd;  /* Use the handle returned from EP_ENABLE */
    io->flags = 0;
    io->length = max_length;
    
    int ret = ioctl(fd, USB_RAW_IOCTL_EP_READ, io);
    if (ret >= 0) {
        memcpy(buffer, io->data, ret);
    }
    
    free(io);
    return ret;
}

/* Read input reports from stdin (sent by Python) */
static void *input_thread(void *arg) {
    printf("Input thread started (reading from stdin)\n");
    uint8_t report[XBOX360_REPORT_SIZE];
    uint8_t last_report[XBOX360_REPORT_SIZE];
    bool have_last_report = false;
    
    /* Initialize last_report with idle report */
    memcpy(last_report, idle_report, XBOX360_REPORT_SIZE);
    
    /* Set stdin to non-blocking */
    int flags = fcntl(STDIN_FILENO, F_GETFL, 0);
    fcntl(STDIN_FILENO, F_SETFL, flags | O_NONBLOCK);
    
    while (running) {
        /* Try to read a complete 20-byte report */
        ssize_t n = read(STDIN_FILENO, report, XBOX360_REPORT_SIZE);
        
        if (n == XBOX360_REPORT_SIZE) {
            /* Got new report from Python - send it and save as last */
            int ret = send_report(report, XBOX360_REPORT_SIZE);
            if (ret < 0) {
                if (errno != EAGAIN && errno != EINTR) {
                    perror("Failed to send report");
                }
            }
            memcpy(last_report, report, XBOX360_REPORT_SIZE);
            have_last_report = true;
        } else if (n < 0) {
            if (errno == EAGAIN || errno == EWOULDBLOCK) {
                /*
                 * No data available from stdin - send last report as keep-alive.
                 * 
                 * The Xbox 360 console expects periodic reports even when idle.
                 * Without this keep-alive mechanism, the console may disconnect
                 * the controller after a timeout period.
                 * 
                 * PCs are more lenient, but the Xbox 360 requires continuous
                 * reports at ~125Hz (every 8ms).
                 * 
                 * Note: Errors from send_report() are intentionally ignored here
                 * because keep-alive failures are non-fatal. The next iteration
                 * will retry, and if the USB connection is truly broken, the
                 * event loop thread will detect it and set running=false.
                 */
                if (endpoints_configured) {
                    const uint8_t *report_to_send = have_last_report ? last_report : idle_report;
                    send_report(report_to_send, XBOX360_REPORT_SIZE);
                }
            } else {
                perror("stdin read error");
                break;
            }
        } else if (n > 0) {
            printf("Warning: Received incomplete report (%zd bytes)\n", n);
        }
        
        /* ~125Hz = 8ms polling rate */
        usleep(8000);
    }
    
    /*
     * Drain any remaining data from stdin to prevent garbage characters
     * appearing in the terminal after the program exits.
     * This discards any leftover binary data that wasn't consumed.
     * 
     * Note: stdin is already in non-blocking mode (set at the start of this function),
     * so this loop will return immediately when there's no more data.
     */
    uint8_t drain_buffer[256];
    ssize_t drained;
    while ((drained = read(STDIN_FILENO, drain_buffer, sizeof(drain_buffer))) > 0) {
        /* Discard data */
    }
    
    printf("Input thread exiting\n");
    return NULL;
}

/* Main function */
int main(int argc, char **argv) {
    printf("Xbox 360 Controller Emulator (raw-gadget)\n");
    printf("=========================================\n\n");
    
    /* Parse arguments */
    for (int i = 1; i < argc; i++) {
        if (strcmp(argv[i], "--debug") == 0 || strcmp(argv[i], "-d") == 0) {
            debug_mode = true;
            printf("Debug mode enabled\n");
        } else if (strcmp(argv[i], "--help") == 0 || strcmp(argv[i], "-h") == 0) {
            printf("Usage: %s [OPTIONS]\n", argv[0]);
            printf("Options:\n");
            printf("  --debug, -d   Enable debug output\n");
            printf("  --help, -h    Show this help message\n");
            return 0;
        }
    }
    
    setup_signals();
    
    /* Open raw-gadget device */
    if (open_raw_gadget() < 0) {
        return 1;
    }
    
    /* Initialize raw-gadget with UDC */
    if (init_raw_gadget() < 0) {
        close(fd);
        return 1;
    }
    
    /*
     * IMPORTANT: Run the gadget BEFORE trying to get endpoint info.
     * USB_RAW_IOCTL_EPS_INFO requires the gadget to be running and
     * a connect event to have occurred.
     * 
     * Note: USB_RAW_IOCTL_RUN requires 0 as its argument value.
     * The kernel checks if (value) return -EINVAL, so we must pass 0.
     */
    printf("Running USB gadget...\n");
    if (ioctl(fd, USB_RAW_IOCTL_RUN, 0) < 0) {
        perror("USB_RAW_IOCTL_RUN failed");
        close(fd);
        return 1;
    }
    
    printf("\n*** Xbox 360 Controller is now active ***\n");
    printf("Waiting for USB connection...\n");
    printf("Connect Pi Zero to Xbox 360 or PC via USB\n");
    printf("Send 20-byte input reports via stdin (from Python)\n\n");
    
    /* Start event loop thread (handles USB events including connect/control) */
    pthread_t event_thread;
    if (pthread_create(&event_thread, NULL, event_loop_thread, NULL) != 0) {
        perror("Failed to create event loop thread");
        close(fd);
        return 1;
    }
    
    /* Start input thread */
    pthread_t in_thread;
    if (pthread_create(&in_thread, NULL, input_thread, NULL) != 0) {
        perror("Failed to create input thread");
        close(fd);
        return 1;
    }
    
    /* Wait for threads */
    pthread_join(event_thread, NULL);
    pthread_join(in_thread, NULL);
    
    /* Cleanup */
    printf("\nShutting down...\n");
    close(fd);
    
    return 0;
}

/*
 * IMPLEMENTATION NOTES:
 * 
 * This emulator implements fixes for common PC/xpad recognition issues:
 * 
 * 1. Device Qualifier Descriptor (FIXED):
 *    - Proper full-speed fallback support for USB 2.0 high-speed devices
 *    - Class/subclass/protocol now matches device descriptor (0xFF/0xFF/0xFF)
 *    - Prevents enumeration timeouts (-110 errors) on hosts requesting qualifier
 * 
 * 2. bInterval values (FIXED):
 *    - EP3 IN changed from 64ms (invalid) to 8ms (valid for full-speed)
 *    - Prevents "invalid bInterval 64, changing to 10" kernel warning
 *    - All endpoints now use valid bInterval values per USB 2.0 spec
 * 
 * 3. Vendor request handler (IMPLEMENTED):
 *    - Request 0x01: Get device capabilities / init handshake
 *    - Request 0xA9: Security / authentication (returns zeros for PC compat)
 *    - Unknown requests acknowledged to prevent enumeration failures
 * 
 * 4. Debug mode (ENHANCED):
 *    - Run with --debug for verbose ioctl tracing
 *    - Tracks descriptor requests, EP enable/disable, report counts
 *    - Useful for diagnosing PC recognition issues via dmesg comparison
 * 
 * TODO for full Xbox 360 console compatibility:
 * 
 * 1. Output report handling:
 *    - Parse rumble/LED commands from EP OUT
 *    - Forward to Python for applying to source controller
 *    - Implement separate thread for reading EP OUT
 * 
 * 2. Keep-alive mechanism (FIXED):
 *    - Xbox 360 expects periodic reports even when idle
 *    - Now sends idle/last report every ~8ms when no new input from Python
 *    - Sends initial idle reports immediately after SET_CONFIGURATION
 *    - This fixes the "5 second delay" issue where Xbox 360 wouldn't recognize
 *      the controller even though PCs worked fine
 * 
 * 3. Integration improvements:
 *    - Current: stdin pipe (simple but one-way)
 *    - Better: Unix socket or shared memory for bidirectional communication
 *    - Enables rumble feedback to source controller
 */
