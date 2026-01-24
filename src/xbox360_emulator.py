#!/usr/bin/env python3
"""
Xbox 360 Controller Emulator for Raspberry Pi Zero

This is the main application that:
1. Sets up USB gadget emulating an Xbox 360 wired controller
2. Reads input from an Xbox One/Series controller
3. Maps and sends input reports to the connected console
4. Handles rumble/LED feedback from the console

The emulator uses Linux's configfs gadget interface or raw-gadget
for low-level USB device emulation.

Usage:
    sudo python3 xbox360_emulator.py [options]

Options:
    --input DEVICE    Path to input device (auto-detect if not specified)
    --debug           Enable debug output
    --dry-run         Don't actually configure USB gadget
"""

import os
import sys
import time
import signal
import logging
import argparse
import threading
from typing import Optional

# Local imports
from xbox360_descriptors import (
    Xbox360Descriptors, VENDOR_ID, PRODUCT_ID,
    MANUFACTURER_STRING, PRODUCT_STRING
)
from report_formatter import InputReport, OutputReport, create_idle_report

# Optional imports
try:
    from input_handler import InputHandler, ControllerState, EVDEV_AVAILABLE
except ImportError:
    EVDEV_AVAILABLE = False


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# Constants
GADGET_NAME = "xbox360"
GADGET_BASE_PATH = "/sys/kernel/config/usb_gadget"
GADGET_PATH = f"{GADGET_BASE_PATH}/{GADGET_NAME}"

# Polling interval for input reports (Xbox 360 expects ~8ms)
REPORT_INTERVAL = 0.008  # 8ms = 125Hz


class USBGadgetError(Exception):
    """Exception raised for USB gadget configuration errors."""
    pass


class Xbox360GadgetConfigFS:
    """
    Manages Xbox 360 controller emulation using Linux configfs gadget.
    
    This class handles:
    - Creating the USB gadget configuration
    - Setting up device descriptors to match Xbox 360 controller
    - Managing the HID endpoints for input/output reports
    """
    
    def __init__(self, dry_run: bool = False):
        """
        Initialize the gadget manager.
        
        Args:
            dry_run: If True, don't actually configure the gadget
        """
        self.dry_run = dry_run
        self.configured = False
        self.gadget_device = None  # Path to /dev/hidgX
        self._ep_in = None  # File handle for input endpoint
        self._ep_out = None  # File handle for output endpoint
    
    def _write_file(self, path: str, content: str) -> None:
        """Write content to a file, creating parent dirs if needed."""
        if self.dry_run:
            logger.debug(f"DRY RUN: Would write '{content}' to {path}")
            return
        
        try:
            with open(path, 'w') as f:
                f.write(content)
        except OSError as e:
            raise USBGadgetError(f"Failed to write to {path}: {e}")
    
    def _write_file_bytes(self, path: str, data: bytes) -> None:
        """Write binary data to a file."""
        if self.dry_run:
            logger.debug(f"DRY RUN: Would write {len(data)} bytes to {path}")
            return
        
        try:
            with open(path, 'wb') as f:
                f.write(data)
        except OSError as e:
            raise USBGadgetError(f"Failed to write to {path}: {e}")
    
    def _mkdir(self, path: str) -> None:
        """Create a directory."""
        if self.dry_run:
            logger.debug(f"DRY RUN: Would create directory {path}")
            return
        
        try:
            os.makedirs(path, exist_ok=True)
        except OSError as e:
            raise USBGadgetError(f"Failed to create directory {path}: {e}")
    
    def _symlink(self, src: str, dst: str) -> None:
        """Create a symbolic link."""
        if self.dry_run:
            logger.debug(f"DRY RUN: Would create symlink {dst} -> {src}")
            return
        
        try:
            if os.path.exists(dst):
                os.remove(dst)
            os.symlink(src, dst)
        except OSError as e:
            raise USBGadgetError(f"Failed to create symlink {dst}: {e}")
    
    def _check_prerequisites(self) -> None:
        """Check if system is ready for USB gadget configuration."""
        # Check for root privileges
        if os.geteuid() != 0 and not self.dry_run:
            raise USBGadgetError("Root privileges required")
        
        # Check for configfs
        if not os.path.exists(GADGET_BASE_PATH) and not self.dry_run:
            raise USBGadgetError(
                f"configfs not mounted at {GADGET_BASE_PATH}. "
                "Try: mount -t configfs none /sys/kernel/config"
            )
        
        # Check for libcomposite module
        if not self.dry_run:
            try:
                with open('/proc/modules') as f:
                    modules = f.read()
                if 'libcomposite' not in modules:
                    logger.warning("libcomposite module not loaded. Loading...")
                    os.system('modprobe libcomposite')
            except (OSError, PermissionError):
                pass
    
    def setup(self) -> None:
        """
        Set up the Xbox 360 controller USB gadget.
        
        This creates the complete gadget configuration in configfs
        with all necessary descriptors and endpoints.
        """
        logger.info("Setting up Xbox 360 controller USB gadget...")
        
        self._check_prerequisites()
        
        # Remove existing gadget if present
        self.teardown()
        
        # Create gadget directory
        self._mkdir(GADGET_PATH)
        
        # Set device identifiers
        self._write_file(f"{GADGET_PATH}/idVendor", f"0x{VENDOR_ID:04X}")
        self._write_file(f"{GADGET_PATH}/idProduct", f"0x{PRODUCT_ID:04X}")
        self._write_file(f"{GADGET_PATH}/bcdDevice", "0x0114")  # 1.14
        self._write_file(f"{GADGET_PATH}/bcdUSB", "0x0200")     # USB 2.0
        
        # Set device class (vendor specific)
        self._write_file(f"{GADGET_PATH}/bDeviceClass", "0xFF")
        self._write_file(f"{GADGET_PATH}/bDeviceSubClass", "0xFF")
        self._write_file(f"{GADGET_PATH}/bDeviceProtocol", "0xFF")
        
        # Create English strings
        strings_path = f"{GADGET_PATH}/strings/0x409"
        self._mkdir(strings_path)
        self._write_file(f"{strings_path}/manufacturer", MANUFACTURER_STRING)
        self._write_file(f"{strings_path}/product", PRODUCT_STRING)
        self._write_file(f"{strings_path}/serialnumber", "")
        
        # Create configuration
        config_path = f"{GADGET_PATH}/configs/c.1"
        self._mkdir(config_path)
        self._write_file(f"{config_path}/MaxPower", "500")
        
        config_strings = f"{config_path}/strings/0x409"
        self._mkdir(config_strings)
        self._write_file(f"{config_strings}/configuration", "Xbox 360 Controller")
        
        # Create HID function
        # Note: Standard HID gadget may not fully support Xbox 360 protocol
        # For full compatibility, raw-gadget or custom function may be needed
        func_path = f"{GADGET_PATH}/functions/hid.usb0"
        self._mkdir(func_path)
        
        # Configure HID function
        self._write_file(f"{func_path}/protocol", "0")  # No protocol (vendor specific)
        self._write_file(f"{func_path}/subclass", "0")  # No subclass
        self._write_file(f"{func_path}/report_length", "20")  # 20 byte reports
        
        # Write HID report descriptor
        # Note: Xbox 360 uses vendor-specific reports, not standard HID
        # This is a minimal descriptor for compatibility
        hid_descriptor = self._create_hid_report_descriptor()
        self._write_file_bytes(f"{func_path}/report_desc", hid_descriptor)
        
        # Link function to configuration
        self._symlink(func_path, f"{config_path}/hid.usb0")
        
        # Bind to UDC (USB Device Controller)
        if not self.dry_run:
            udc_list = os.listdir('/sys/class/udc') if os.path.exists('/sys/class/udc') else []
            if udc_list:
                udc = udc_list[0]
                self._write_file(f"{GADGET_PATH}/UDC", udc)
                logger.info(f"Bound to UDC: {udc}")
            else:
                logger.warning("No UDC available. Gadget not bound.")
        
        self.configured = True
        logger.info("USB gadget configured successfully")
        
        # Find the HID device
        self._find_hid_device()
    
    def _create_hid_report_descriptor(self) -> bytes:
        """
        Create a minimal HID report descriptor.
        
        Note: The Xbox 360 controller uses vendor-specific USB class,
        not standard HID. This descriptor is for basic compatibility
        when testing on a PC. For actual Xbox 360 console use, raw-gadget
        with custom descriptors is recommended.
        """
        # Minimal vendor-specific HID descriptor for 20-byte reports
        return bytes([
            0x05, 0x01,        # Usage Page (Generic Desktop)
            0x09, 0x05,        # Usage (Game Pad)
            0xA1, 0x01,        # Collection (Application)
            0x15, 0x00,        #   Logical Minimum (0)
            0x26, 0xFF, 0x00,  #   Logical Maximum (255)
            0x75, 0x08,        #   Report Size (8 bits)
            0x95, 0x14,        #   Report Count (20)
            0x09, 0x00,        #   Usage (Undefined - vendor specific)
            0x81, 0x02,        #   Input (Data, Var, Abs)
            0x09, 0x00,        #   Usage (Undefined - vendor specific)
            0x91, 0x02,        #   Output (Data, Var, Abs)
            0xC0,              # End Collection
        ])
    
    def _find_hid_device(self) -> None:
        """Find the created HID gadget device."""
        if self.dry_run:
            self.gadget_device = "/dev/hidg0"
            return
        
        # Wait for device to appear
        for _ in range(10):
            if os.path.exists("/dev/hidg0"):
                self.gadget_device = "/dev/hidg0"
                logger.info(f"HID device found: {self.gadget_device}")
                return
            time.sleep(0.1)
        
        logger.warning("HID gadget device not found at /dev/hidg0")
    
    def open_endpoints(self) -> bool:
        """
        Open the HID gadget device for reading/writing.
        
        Returns:
            True if successful, False otherwise
        """
        if self.dry_run:
            logger.info("DRY RUN: Would open endpoints")
            return True
        
        if not self.gadget_device:
            logger.error("No gadget device available")
            return False
        
        try:
            self._ep_in = open(self.gadget_device, 'wb', buffering=0)
            self._ep_out = open(self.gadget_device, 'rb', buffering=0)
            logger.info("Endpoints opened successfully")
            return True
        except (OSError, PermissionError) as e:
            logger.error(f"Failed to open endpoints: {e}")
            return False
    
    def send_report(self, report: bytes) -> bool:
        """
        Send an input report to the host.
        
        Args:
            report: 20-byte input report
            
        Returns:
            True if successful, False otherwise
        """
        if self.dry_run:
            return True
        
        if not self._ep_in:
            return False
        
        try:
            self._ep_in.write(report)
            return True
        except (OSError, BrokenPipeError) as e:
            logger.debug(f"Failed to send report: {e}")
            return False
    
    def receive_report(self, timeout: float = 0.0) -> Optional[bytes]:
        """
        Receive an output report from the host (rumble/LED commands).
        
        Args:
            timeout: Read timeout in seconds (0 = non-blocking)
            
        Returns:
            bytes: Output report, or None if no data
        """
        if self.dry_run:
            return None
        
        if not self._ep_out:
            return None
        
        try:
            # Non-blocking read would require fcntl
            import select
            readable, _, _ = select.select([self._ep_out], [], [], timeout)
            if readable:
                return self._ep_out.read(32)
            return None
        except (OSError, BlockingIOError):
            return None
    
    def close_endpoints(self) -> None:
        """Close the endpoint file handles."""
        if self._ep_in:
            try:
                self._ep_in.close()
            except OSError:
                pass
            self._ep_in = None
        
        if self._ep_out:
            try:
                self._ep_out.close()
            except OSError:
                pass
            self._ep_out = None
    
    def teardown(self) -> None:
        """Remove the USB gadget configuration."""
        if self.dry_run:
            logger.debug("DRY RUN: Would remove gadget")
            self.configured = False
            return
        
        if not os.path.exists(GADGET_PATH):
            return
        
        logger.info("Removing existing USB gadget...")
        
        try:
            # Unbind from UDC
            udc_path = f"{GADGET_PATH}/UDC"
            if os.path.exists(udc_path):
                with open(udc_path, 'w') as f:
                    f.write("")
            
            # Remove symlinks in configs
            config_path = f"{GADGET_PATH}/configs/c.1"
            if os.path.exists(config_path):
                for item in os.listdir(config_path):
                    item_path = f"{config_path}/{item}"
                    if os.path.islink(item_path):
                        os.unlink(item_path)
                
                # Remove config strings
                strings_path = f"{config_path}/strings/0x409"
                if os.path.exists(strings_path):
                    os.rmdir(strings_path)
                
                os.rmdir(config_path)
            
            # Remove functions
            func_path = f"{GADGET_PATH}/functions/hid.usb0"
            if os.path.exists(func_path):
                os.rmdir(func_path)
            
            # Remove strings
            strings_path = f"{GADGET_PATH}/strings/0x409"
            if os.path.exists(strings_path):
                os.rmdir(strings_path)
            
            # Remove gadget
            os.rmdir(GADGET_PATH)
            
            logger.info("USB gadget removed")
        except OSError as e:
            logger.warning(f"Error removing gadget: {e}")
        
        self.configured = False


class Xbox360Emulator:
    """
    Main emulator application that ties everything together.
    
    This class manages:
    - USB gadget setup
    - Input device handling
    - Report generation and transmission
    - Rumble feedback forwarding
    """
    
    def __init__(self, input_device: Optional[str] = None,
                 dry_run: bool = False, debug: bool = False):
        """
        Initialize the emulator.
        
        Args:
            input_device: Path to input device (None for auto-detect)
            dry_run: Don't actually configure USB gadget
            debug: Enable debug logging
        """
        if debug:
            logging.getLogger().setLevel(logging.DEBUG)
        
        self.dry_run = dry_run
        self.gadget = Xbox360GadgetConfigFS(dry_run=dry_run)
        self.input_handler: Optional[InputHandler] = None
        self.input_device_path = input_device
        
        self.running = False
        self.report = InputReport()
        self._last_report_time = 0.0
        self._report_count = 0
    
    def _map_input_to_report(self, state: ControllerState) -> None:
        """
        Map input controller state to Xbox 360 report format.
        
        Args:
            state: Current controller state
        """
        # Map buttons
        self.report.set_a(state.a)
        self.report.set_b(state.b)
        self.report.set_x(state.x)
        self.report.set_y(state.y)
        self.report.set_lb(state.lb)
        self.report.set_rb(state.rb)
        self.report.set_start(state.start)
        self.report.set_back(state.back)
        self.report.set_guide(state.guide)
        self.report.set_left_stick_click(state.left_stick_click)
        self.report.set_right_stick_click(state.right_stick_click)
        
        # Map D-pad
        self.report.set_dpad_up(state.dpad_up)
        self.report.set_dpad_down(state.dpad_down)
        self.report.set_dpad_left(state.dpad_left)
        self.report.set_dpad_right(state.dpad_right)
        
        # Map triggers
        self.report.set_left_trigger(state.left_trigger)
        self.report.set_right_trigger(state.right_trigger)
        
        # Map sticks
        self.report.set_left_stick(state.left_stick_x, state.left_stick_y)
        self.report.set_right_stick(state.right_stick_x, state.right_stick_y)
    
    def _on_input_change(self, state: ControllerState) -> None:
        """Callback when input state changes."""
        self._map_input_to_report(state)
    
    def _send_periodic_report(self) -> None:
        """Send input report at regular intervals."""
        now = time.time()
        if now - self._last_report_time >= REPORT_INTERVAL:
            report_bytes = self.report.to_bytes()
            if self.gadget.send_report(report_bytes):
                self._report_count += 1
                if self._report_count % 1000 == 0:
                    logger.debug(f"Sent {self._report_count} reports")
            self._last_report_time = now
    
    def _process_output_reports(self) -> None:
        """Process any output reports from the console."""
        report = self.gadget.receive_report(0.001)
        if report:
            parsed = OutputReport.parse(report)
            if parsed:
                if parsed['type'] == 'rumble':
                    logger.debug(f"Rumble: L={parsed['left_motor']}, R={parsed['right_motor']}")
                    # TODO: Forward rumble to input controller if supported
                elif parsed['type'] == 'led':
                    logger.debug(f"LED pattern: {parsed['pattern']}")
    
    def setup(self) -> bool:
        """
        Set up the emulator.
        
        Returns:
            True if successful, False otherwise
        """
        logger.info("Setting up Xbox 360 controller emulator...")
        
        # Set up USB gadget
        try:
            self.gadget.setup()
        except USBGadgetError as e:
            logger.error(f"Failed to set up USB gadget: {e}")
            if not self.dry_run:
                return False
        
        # Open gadget endpoints
        if not self.gadget.open_endpoints():
            if not self.dry_run:
                logger.error("Failed to open gadget endpoints")
                return False
        
        # Set up input handler
        if EVDEV_AVAILABLE:
            try:
                self.input_handler = InputHandler(self.input_device_path)
                self.input_handler.set_callback(self._on_input_change)
                logger.info("Input handler initialized")
            except RuntimeError as e:
                logger.warning(f"Could not initialize input handler: {e}")
                logger.warning("Running without input device (idle reports only)")
        else:
            logger.warning("evdev not available - running without input device")
        
        return True
    
    def run(self) -> None:
        """Run the main emulator loop."""
        logger.info("Starting emulator...")
        self.running = True
        
        # Send initial idle report
        idle_report = create_idle_report()
        self.gadget.send_report(idle_report)
        
        try:
            while self.running:
                # Poll for input events
                if self.input_handler:
                    self.input_handler.poll(0.001)
                
                # Send periodic reports
                self._send_periodic_report()
                
                # Process output reports (rumble, LED)
                self._process_output_reports()
                
                # Small sleep to prevent CPU spinning
                time.sleep(0.001)
                
        except KeyboardInterrupt:
            logger.info("Interrupted by user")
        finally:
            self.running = False
    
    def stop(self) -> None:
        """Stop the emulator."""
        logger.info("Stopping emulator...")
        self.running = False
    
    def cleanup(self) -> None:
        """Clean up resources."""
        logger.info("Cleaning up...")
        
        self.gadget.close_endpoints()
        self.gadget.teardown()
        
        if self.input_handler:
            self.input_handler.close()
        
        logger.info("Cleanup complete")


def signal_handler(signum, frame):
    """Handle termination signals."""
    logger.info(f"Received signal {signum}")
    raise KeyboardInterrupt


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='Xbox 360 Controller Emulator for Raspberry Pi Zero'
    )
    parser.add_argument(
        '--input', '-i',
        dest='input_device',
        help='Path to input device (auto-detect if not specified)'
    )
    parser.add_argument(
        '--debug', '-d',
        action='store_true',
        help='Enable debug output'
    )
    parser.add_argument(
        '--dry-run', '-n',
        action='store_true',
        help="Don't actually configure USB gadget"
    )
    parser.add_argument(
        '--list-devices', '-l',
        action='store_true',
        help='List available input devices and exit'
    )
    
    args = parser.parse_args()
    
    # List devices mode
    if args.list_devices:
        if EVDEV_AVAILABLE:
            from input_handler import list_input_devices
            list_input_devices()
        else:
            print("evdev not available. Install with: pip3 install evdev")
        return
    
    # Set up signal handlers
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
    
    # Create and run emulator
    emulator = Xbox360Emulator(
        input_device=args.input_device,
        dry_run=args.dry_run,
        debug=args.debug
    )
    
    try:
        if emulator.setup():
            emulator.run()
        else:
            logger.error("Setup failed")
            sys.exit(1)
    finally:
        emulator.cleanup()


if __name__ == "__main__":
    main()
