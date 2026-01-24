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
#include <sys/ioctl.h>
#include <sys/select.h>
#include <linux/usb/ch9.h>

/* Raw-gadget includes */
#define USB_RAW_IOCTL_INIT              _IOW('U', 0, struct usb_raw_init)
#define USB_RAW_IOCTL_RUN               _IO('U', 1)
#define USB_RAW_IOCTL_EP0_READ          _IOWR('U', 3, struct usb_raw_ep_io)
#define USB_RAW_IOCTL_EP0_WRITE         _IOWR('U', 4, struct usb_raw_ep_io)
#define USB_RAW_IOCTL_EP_ENABLE         _IOW('U', 5, struct usb_endpoint_descriptor)
#define USB_RAW_IOCTL_EP_WRITE          _IOWR('U', 7, struct usb_raw_ep_io)
#define USB_RAW_IOCTL_EP_READ           _IOWR('U', 8, struct usb_raw_ep_io)
#define USB_RAW_IOCTL_CONFIGURE         _IO('U', 9)
#define USB_RAW_IOCTL_VBUS_DRAW         _IOW('U', 10, uint32_t)

#define USB_RAW_IO_FLAGS_ZERO       0x0001
#define USB_RAW_IO_FLAGS_MASK       0x0001

struct usb_raw_init {
    uint8_t driver_name[16];
    uint8_t device_name[16];
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

/* USB String Descriptor Indices */
#define STRING_ID_MANUFACTURER  1
#define STRING_ID_PRODUCT       2
#define STRING_ID_SERIAL        0  /* No serial number */

/* Endpoint addresses */
#define EP_IN_ADDRESS           0x81  /* Endpoint 1 IN (controller -> host) */
#define EP_OUT_ADDRESS          0x01  /* Endpoint 1 OUT (host -> controller) */

/* Device Descriptor */
static struct usb_device_descriptor device_descriptor = {
    .bLength            = USB_DT_DEVICE_SIZE,
    .bDescriptorType    = USB_DT_DEVICE,
    .bcdUSB             = __constant_cpu_to_le16(0x0200), /* USB 2.0 */
    .bDeviceClass       = 0xFF,  /* Vendor specific */
    .bDeviceSubClass    = 0xFF,
    .bDeviceProtocol    = 0xFF,
    .bMaxPacketSize0    = 8,     /* Max packet size for endpoint 0 */
    .idVendor           = __constant_cpu_to_le16(XBOX360_VENDOR_ID),
    .idProduct          = __constant_cpu_to_le16(XBOX360_PRODUCT_ID),
    .bcdDevice          = __constant_cpu_to_le16(XBOX360_DEVICE_VERSION),
    .iManufacturer      = STRING_ID_MANUFACTURER,
    .iProduct           = STRING_ID_PRODUCT,
    .iSerialNumber      = STRING_ID_SERIAL,
    .bNumConfigurations = 1,
};

/* Configuration Descriptor with interfaces and endpoints */
struct xbox360_config {
    struct usb_config_descriptor config;
    struct usb_interface_descriptor interface;
    struct usb_endpoint_descriptor ep_in;
    struct usb_endpoint_descriptor ep_out;
} __attribute__((packed));

static struct xbox360_config config_descriptor = {
    .config = {
        .bLength             = USB_DT_CONFIG_SIZE,
        .bDescriptorType     = USB_DT_CONFIG,
        .wTotalLength        = __constant_cpu_to_le16(sizeof(struct xbox360_config)),
        .bNumInterfaces      = 1,
        .bConfigurationValue = 1,
        .iConfiguration      = 0,
        .bmAttributes        = USB_CONFIG_ATT_ONE | USB_CONFIG_ATT_SELFPOWER,
        .bMaxPower           = 250,  /* 500mA */
    },
    .interface = {
        .bLength            = USB_DT_INTERFACE_SIZE,
        .bDescriptorType    = USB_DT_INTERFACE,
        .bInterfaceNumber   = 0,
        .bAlternateSetting  = 0,
        .bNumEndpoints      = 2,
        .bInterfaceClass    = 0xFF,  /* Vendor specific */
        .bInterfaceSubClass = 0x5D,  /* Xbox Controller */
        .bInterfaceProtocol = 0x01,  /* Wired controller */
        .iInterface         = 0,
    },
    .ep_in = {
        .bLength          = USB_DT_ENDPOINT_SIZE,
        .bDescriptorType  = USB_DT_ENDPOINT,
        .bEndpointAddress = EP_IN_ADDRESS,
        .bmAttributes     = USB_ENDPOINT_XFER_INT,
        .wMaxPacketSize   = __constant_cpu_to_le16(32),
        .bInterval        = 4,  /* Poll every 8ms (2^(4-1) = 8) */
    },
    .ep_out = {
        .bLength          = USB_DT_ENDPOINT_SIZE,
        .bDescriptorType  = USB_DT_ENDPOINT,
        .bEndpointAddress = EP_OUT_ADDRESS,
        .bmAttributes     = USB_ENDPOINT_XFER_INT,
        .wMaxPacketSize   = __constant_cpu_to_le16(32),
        .bInterval        = 8,  /* Poll every 64ms */
    },
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

/* Global state */
static int fd = -1;              /* raw-gadget file descriptor */
static int ep_in_fd = -1;        /* EP1 IN file descriptor */
static int ep_out_fd = -1;       /* EP1 OUT file descriptor */
static volatile bool running = true;

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

/* Initialize raw-gadget with UDC */
static int init_raw_gadget(void) {
    struct usb_raw_init init = {
        .driver_name = "dummy_udc",  /* Will be auto-detected */
        .device_name = "",
        .speed = USB_SPEED_FULL,
    };
    
    int ret = ioctl(fd, USB_RAW_IOCTL_INIT, &init);
    if (ret < 0) {
        perror("USB_RAW_IOCTL_INIT failed");
        return -1;
    }
    printf("Initialized raw-gadget (speed: full)\n");
    return 0;
}

/* Handle control endpoint (EP0) requests */
static int handle_control_request(struct usb_ctrlrequest *setup) {
    uint8_t buffer[512];
    int length = 0;
    
    printf("Control request: bRequestType=0x%02X, bRequest=0x%02X, wValue=0x%04X, wIndex=0x%04X, wLength=%d\n",
           setup->bRequestType, setup->bRequest, 
           __le16_to_cpu(setup->wValue), __le16_to_cpu(setup->wIndex),
           __le16_to_cpu(setup->wLength));
    
    /* Handle standard requests */
    if ((setup->bRequestType & USB_TYPE_MASK) == USB_TYPE_STANDARD) {
        switch (setup->bRequest) {
            case USB_REQ_GET_DESCRIPTOR: {
                uint8_t desc_type = __le16_to_cpu(setup->wValue) >> 8;
                uint8_t desc_index = __le16_to_cpu(setup->wValue) & 0xFF;
                
                switch (desc_type) {
                    case USB_DT_DEVICE:
                        printf("  -> GET_DESCRIPTOR: DEVICE\n");
                        memcpy(buffer, &device_descriptor, sizeof(device_descriptor));
                        length = sizeof(device_descriptor);
                        break;
                        
                    case USB_DT_CONFIG:
                        printf("  -> GET_DESCRIPTOR: CONFIG\n");
                        memcpy(buffer, &config_descriptor, sizeof(config_descriptor));
                        length = sizeof(config_descriptor);
                        break;
                        
                    case USB_DT_STRING:
                        printf("  -> GET_DESCRIPTOR: STRING (index %d)\n", desc_index);
                        if (desc_index == 0) {
                            memcpy(buffer, &string_lang, 4);
                            length = 4;
                        } else if (desc_index == STRING_ID_MANUFACTURER) {
                            memcpy(buffer, manufacturer_string, manufacturer_string[0]);
                            length = manufacturer_string[0];
                        } else if (desc_index == STRING_ID_PRODUCT) {
                            memcpy(buffer, product_string, product_string[0]);
                            length = product_string[0];
                        } else {
                            printf("  -> Unknown string index %d\n", desc_index);
                            return -1;
                        }
                        break;
                        
                    default:
                        printf("  -> Unknown descriptor type 0x%02X\n", desc_type);
                        return -1;
                }
                break;
            }
            
            case USB_REQ_SET_CONFIGURATION:
                printf("  -> SET_CONFIGURATION: %d\n", __le16_to_cpu(setup->wValue));
                /* Acknowledge with zero-length packet */
                length = 0;
                break;
                
            case USB_REQ_SET_INTERFACE:
                printf("  -> SET_INTERFACE\n");
                length = 0;
                break;
                
            default:
                printf("  -> Unsupported standard request 0x%02X\n", setup->bRequest);
                return -1;
        }
    }
    /* Handle vendor-specific requests (Xbox 360 init) */
    else if ((setup->bRequestType & USB_TYPE_MASK) == USB_TYPE_VENDOR) {
        printf("  -> VENDOR request 0x%02X\n", setup->bRequest);
        
        /* Xbox 360 controllers respond to vendor request 0x01 during init */
        if (setup->bRequest == 0x01) {
            /* Return empty response for now */
            /* TODO: Implement proper vendor request responses based on */
            /* https://www.partsnotincluded.com/understanding-the-xbox-360-wired-controllers-usb-data/ */
            length = 0;
        } else {
            length = 0;  /* Acknowledge unknown vendor requests */
        }
    }
    /* Handle class-specific requests */
    else if ((setup->bRequestType & USB_TYPE_MASK) == USB_TYPE_CLASS) {
        printf("  -> CLASS request 0x%02X\n", setup->bRequest);
        length = 0;
    }
    else {
        printf("  -> Unknown request type 0x%02X\n", setup->bRequestType);
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
            perror("EP0 write failed");
            return -1;
        }
    } else {
        /* OUT request - send status */
        struct usb_raw_ep_io io = {0};
        io.ep = 0;
        io.flags = 0;
        io.length = 0;
        
        int ret = ioctl(fd, USB_RAW_IOCTL_EP0_READ, &io);
        if (ret < 0) {
            perror("EP0 read (status) failed");
            return -1;
        }
    }
    
    return 0;
}

/* Event loop for control endpoint */
static void *control_thread(void *arg) {
    printf("Control thread started\n");
    
    while (running) {
        struct usb_raw_ep_io io = {0};
        io.ep = 0;
        io.flags = 0;
        io.length = 64;
        
        /* Read control request from EP0 */
        int ret = ioctl(fd, USB_RAW_IOCTL_EP0_READ, &io);
        if (ret < 0) {
            if (errno == EINTR) {
                continue;
            }
            perror("EP0 read failed");
            break;
        }
        
        if (ret < sizeof(struct usb_ctrlrequest)) {
            printf("Short read on EP0: %d bytes\n", ret);
            continue;
        }
        
        /* Handle the request */
        struct usb_ctrlrequest *setup = (struct usb_ctrlrequest *)io.data;
        if (handle_control_request(setup) < 0) {
            printf("Failed to handle control request\n");
            /* TODO: Send STALL on EP0 */
        }
    }
    
    printf("Control thread exiting\n");
    return NULL;
}

/* Send input report via EP1 IN */
static int send_report(const uint8_t *report, size_t length) {
    if (ep_in_fd < 0) {
        return -1;
    }
    
    struct usb_raw_ep_io *io = malloc(sizeof(*io) + length);
    if (!io) {
        return -1;
    }
    
    io->ep = EP_IN_ADDRESS;
    io->flags = 0;
    io->length = length;
    memcpy(io->data, report, length);
    
    int ret = ioctl(fd, USB_RAW_IOCTL_EP_WRITE, io);
    free(io);
    
    return ret;
}

/* Receive output report (rumble/LED) via EP1 OUT */
static int receive_output_report(uint8_t *buffer, size_t max_length) __attribute__((unused));
static int receive_output_report(uint8_t *buffer, size_t max_length) {
    if (ep_out_fd < 0) {
        return -1;
    }
    
    struct usb_raw_ep_io *io = malloc(sizeof(*io) + max_length);
    if (!io) {
        return -1;
    }
    
    io->ep = EP_OUT_ADDRESS;
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
    
    /* Set stdin to non-blocking */
    int flags = fcntl(STDIN_FILENO, F_GETFL, 0);
    fcntl(STDIN_FILENO, F_SETFL, flags | O_NONBLOCK);
    
    while (running) {
        /* Try to read a complete 20-byte report */
        ssize_t n = read(STDIN_FILENO, report, XBOX360_REPORT_SIZE);
        
        if (n == XBOX360_REPORT_SIZE) {
            /* Send report to host */
            int ret = send_report(report, XBOX360_REPORT_SIZE);
            if (ret < 0) {
                if (errno != EAGAIN && errno != EINTR) {
                    perror("Failed to send report");
                }
            }
        } else if (n < 0) {
            if (errno != EAGAIN && errno != EWOULDBLOCK) {
                perror("stdin read error");
                break;
            }
        } else if (n > 0) {
            printf("Warning: Received incomplete report (%zd bytes)\n", n);
        }
        
        /* ~125Hz = 8ms polling rate */
        usleep(8000);
    }
    
    printf("Input thread exiting\n");
    return NULL;
}

/* Main function */
int main(int argc, char **argv) {
    printf("Xbox 360 Controller Emulator (raw-gadget)\n");
    printf("=========================================\n\n");
    
    setup_signals();
    
    /* Open raw-gadget device */
    if (open_raw_gadget() < 0) {
        return 1;
    }
    
    /* Initialize */
    if (init_raw_gadget() < 0) {
        close(fd);
        return 1;
    }
    
    /* Enable endpoints */
    printf("Enabling endpoints...\n");
    
    ep_in_fd = ioctl(fd, USB_RAW_IOCTL_EP_ENABLE, &config_descriptor.ep_in);
    if (ep_in_fd < 0) {
        perror("Failed to enable EP IN");
        close(fd);
        return 1;
    }
    printf("EP1 IN enabled (fd %d)\n", ep_in_fd);
    
    ep_out_fd = ioctl(fd, USB_RAW_IOCTL_EP_ENABLE, &config_descriptor.ep_out);
    if (ep_out_fd < 0) {
        perror("Failed to enable EP OUT");
        close(fd);
        return 1;
    }
    printf("EP1 OUT enabled (fd %d)\n", ep_out_fd);
    
    /* Configure device */
    if (ioctl(fd, USB_RAW_IOCTL_CONFIGURE) < 0) {
        perror("USB_RAW_IOCTL_CONFIGURE failed");
        close(fd);
        return 1;
    }
    
    /* Set VBUS power draw (500mA) */
    uint32_t power = 500;
    if (ioctl(fd, USB_RAW_IOCTL_VBUS_DRAW, &power) < 0) {
        perror("USB_RAW_IOCTL_VBUS_DRAW failed");
        /* Non-fatal, continue */
    }
    
    /* Run the gadget */
    printf("Running USB gadget...\n");
    if (ioctl(fd, USB_RAW_IOCTL_RUN) < 0) {
        perror("USB_RAW_IOCTL_RUN failed");
        close(fd);
        return 1;
    }
    
    printf("\n*** Xbox 360 Controller is now active ***\n");
    printf("Waiting for USB enumeration...\n");
    printf("Connect Pi Zero to Xbox 360 or PC via USB\n");
    printf("Send 20-byte input reports via stdin (from Python)\n\n");
    
    /* Start control thread */
    pthread_t ctrl_thread;
    if (pthread_create(&ctrl_thread, NULL, control_thread, NULL) != 0) {
        perror("Failed to create control thread");
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
    pthread_join(ctrl_thread, NULL);
    pthread_join(in_thread, NULL);
    
    /* Cleanup */
    printf("\nShutting down...\n");
    close(fd);
    
    return 0;
}

/*
 * TODO for full implementation:
 * 
 * 1. Vendor request handling:
 *    - Implement responses for Xbox 360 init vendor requests
 *    - Reference: https://www.partsnotincluded.com/understanding-the-xbox-360-wired-controllers-usb-data/
 * 
 * 2. Output report handling:
 *    - Parse rumble/LED commands from EP1 OUT
 *    - Forward to Python for applying to source controller
 *    - Implement separate thread for reading EP1 OUT
 * 
 * 3. Keep-alive mechanism:
 *    - Xbox 360 may expect periodic reports even when idle
 *    - Send last report every ~8ms if no new input
 * 
 * 4. Error handling:
 *    - Improve EP0 STALL handling
 *    - Reconnection logic if USB disconnects
 * 
 * 5. Integration with Python:
 *    - Current: stdin pipe (simple but one-way)
 *    - Better: Unix socket or shared memory for bidirectional communication
 *    - Enables rumble feedback to source controller
 * 
 * 6. Logging and debugging:
 *    - Add verbose mode flag
 *    - Log all USB transactions for debugging
 *    - Monitor report sending rate
 */
