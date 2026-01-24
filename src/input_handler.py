#!/usr/bin/env python3
"""
Input Handler for Xbox One/Series Controllers

This module handles reading input from source controllers (Xbox One/Series)
connected via USB (evdev) or Bluetooth. It normalizes the input to a common
format that can be mapped to Xbox 360 reports.

Supported input methods:
1. USB via evdev (Linux event device interface)
2. Bluetooth via evdev (using xpadneo driver or similar)
"""

import os
import sys
import time
import select
import logging
from typing import Optional, Callable, Dict, Any

# Check if evdev is available
try:
    import evdev
    from evdev import InputDevice, categorize, ecodes
    EVDEV_AVAILABLE = True
except ImportError:
    EVDEV_AVAILABLE = False
    print("Warning: evdev not available. Install with: pip3 install evdev")


# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# Xbox One/Series controller event codes
# These may vary based on driver (xpad, xone, xpadneo)
class XboxOneEventCodes:
    """Event codes for Xbox One/Series controllers via evdev."""
    
    # Button event codes (EV_KEY)
    BTN_A = ecodes.BTN_A if EVDEV_AVAILABLE else 304
    BTN_B = ecodes.BTN_B if EVDEV_AVAILABLE else 305
    BTN_X = ecodes.BTN_X if EVDEV_AVAILABLE else 307
    BTN_Y = ecodes.BTN_Y if EVDEV_AVAILABLE else 308
    BTN_TL = ecodes.BTN_TL if EVDEV_AVAILABLE else 310  # LB
    BTN_TR = ecodes.BTN_TR if EVDEV_AVAILABLE else 311  # RB
    BTN_SELECT = ecodes.BTN_SELECT if EVDEV_AVAILABLE else 314  # Back/View
    BTN_START = ecodes.BTN_START if EVDEV_AVAILABLE else 315
    BTN_MODE = ecodes.BTN_MODE if EVDEV_AVAILABLE else 316  # Guide
    BTN_THUMBL = ecodes.BTN_THUMBL if EVDEV_AVAILABLE else 317  # LS click
    BTN_THUMBR = ecodes.BTN_THUMBR if EVDEV_AVAILABLE else 318  # RS click
    
    # Axis event codes (EV_ABS)
    ABS_X = ecodes.ABS_X if EVDEV_AVAILABLE else 0      # Left stick X
    ABS_Y = ecodes.ABS_Y if EVDEV_AVAILABLE else 1      # Left stick Y
    ABS_Z = ecodes.ABS_Z if EVDEV_AVAILABLE else 2      # Left trigger
    ABS_RX = ecodes.ABS_RX if EVDEV_AVAILABLE else 3    # Right stick X
    ABS_RY = ecodes.ABS_RY if EVDEV_AVAILABLE else 4    # Right stick Y
    ABS_RZ = ecodes.ABS_RZ if EVDEV_AVAILABLE else 5    # Right trigger
    ABS_HAT0X = ecodes.ABS_HAT0X if EVDEV_AVAILABLE else 16  # D-pad X
    ABS_HAT0Y = ecodes.ABS_HAT0Y if EVDEV_AVAILABLE else 17  # D-pad Y


class ControllerState:
    """
    Normalized controller state independent of input source.
    
    This represents the current state of all controller inputs
    in a format ready for mapping to Xbox 360 reports.
    """
    
    def __init__(self):
        """Initialize with all inputs in neutral/released state."""
        # Digital buttons (bool)
        self.a = False
        self.b = False
        self.x = False
        self.y = False
        self.lb = False
        self.rb = False
        self.start = False
        self.back = False
        self.guide = False
        self.left_stick_click = False
        self.right_stick_click = False
        
        # D-pad (bool)
        self.dpad_up = False
        self.dpad_down = False
        self.dpad_left = False
        self.dpad_right = False
        
        # Analog triggers (0-255)
        self.left_trigger = 0
        self.right_trigger = 0
        
        # Analog sticks (-32768 to 32767)
        self.left_stick_x = 0
        self.left_stick_y = 0
        self.right_stick_x = 0
        self.right_stick_y = 0
    
    def __repr__(self) -> str:
        """String representation for debugging."""
        buttons = []
        if self.a: buttons.append('A')
        if self.b: buttons.append('B')
        if self.x: buttons.append('X')
        if self.y: buttons.append('Y')
        if self.lb: buttons.append('LB')
        if self.rb: buttons.append('RB')
        if self.start: buttons.append('Start')
        if self.back: buttons.append('Back')
        if self.guide: buttons.append('Guide')
        if self.left_stick_click: buttons.append('LS')
        if self.right_stick_click: buttons.append('RS')
        if self.dpad_up: buttons.append('DU')
        if self.dpad_down: buttons.append('DD')
        if self.dpad_left: buttons.append('DL')
        if self.dpad_right: buttons.append('DR')
        
        return (
            f"ControllerState(buttons=[{', '.join(buttons)}], "
            f"LT={self.left_trigger}, RT={self.right_trigger}, "
            f"LS=({self.left_stick_x}, {self.left_stick_y}), "
            f"RS=({self.right_stick_x}, {self.right_stick_y}))"
        )


class InputHandler:
    """
    Handles input from Xbox One/Series controllers via evdev.
    
    This class manages the connection to the input device and
    translates events to a normalized ControllerState.
    """
    
    # Known Xbox controller vendor/product IDs
    XBOX_VENDOR_IDS = [0x045E]  # Microsoft
    XBOX_ONE_PRODUCT_IDS = [
        0x02D1,  # Xbox One Controller
        0x02DD,  # Xbox One Controller (Firmware 2015)
        0x02E3,  # Xbox One Elite Controller
        0x02EA,  # Xbox One S Controller
        0x0B00,  # Xbox One Elite 2 Controller
        0x0B12,  # Xbox Series X|S Controller
        0x0B13,  # Xbox Series X|S Controller (Bluetooth)
    ]
    
    def __init__(self, device_path: Optional[str] = None):
        """
        Initialize the input handler.
        
        Args:
            device_path: Path to evdev device (e.g., /dev/input/event0).
                        If None, will auto-detect Xbox controllers.
        """
        if not EVDEV_AVAILABLE:
            raise RuntimeError("evdev module not available")
        
        self.device: Optional[InputDevice] = None
        self.state = ControllerState()
        self.callback: Optional[Callable[[ControllerState], None]] = None
        
        # Axis calibration values (will be updated from device capabilities)
        self.axis_info: Dict[int, dict] = {}
        
        if device_path:
            self._open_device(device_path)
        else:
            self._auto_detect_device()
    
    def _open_device(self, path: str) -> None:
        """Open a specific evdev device."""
        try:
            self.device = InputDevice(path)
            logger.info(f"Opened device: {self.device.name} ({path})")
            self._read_axis_info()
        except (FileNotFoundError, PermissionError) as e:
            logger.error(f"Failed to open device {path}: {e}")
            raise
    
    def _auto_detect_device(self) -> None:
        """Auto-detect an Xbox controller from available evdev devices."""
        devices = [InputDevice(path) for path in evdev.list_devices()]
        
        for dev in devices:
            # Check by vendor/product ID
            info = dev.info
            if info.vendor in self.XBOX_VENDOR_IDS:
                logger.info(f"Found Xbox controller: {dev.name}")
                self.device = dev
                self._read_axis_info()
                return
            
            # Check by name pattern
            name_lower = dev.name.lower()
            if 'xbox' in name_lower and 'controller' in name_lower:
                logger.info(f"Found Xbox controller by name: {dev.name}")
                self.device = dev
                self._read_axis_info()
                return
        
        raise RuntimeError("No Xbox controller found. Available devices: " + 
                          ", ".join(d.name for d in devices))
    
    def _read_axis_info(self) -> None:
        """Read axis calibration info from device capabilities."""
        if not self.device:
            return
        
        caps = self.device.capabilities(absinfo=True)
        if ecodes.EV_ABS in caps:
            for code, absinfo in caps[ecodes.EV_ABS]:
                self.axis_info[code] = {
                    'min': absinfo.min,
                    'max': absinfo.max,
                    'flat': absinfo.flat,
                    'fuzz': absinfo.fuzz,
                }
                logger.debug(f"Axis {code}: min={absinfo.min}, max={absinfo.max}")
    
    def _scale_axis(self, code: int, value: int, target_min: int, target_max: int) -> int:
        """
        Scale an axis value from device range to target range.
        
        Args:
            code: Axis event code
            value: Raw axis value
            target_min: Target minimum value
            target_max: Target maximum value
            
        Returns:
            Scaled value in target range
        """
        if code not in self.axis_info:
            return value
        
        info = self.axis_info[code]
        src_min = info['min']
        src_max = info['max']
        
        # Normalize to 0-1
        if src_max == src_min:
            normalized = 0.5
        else:
            normalized = (value - src_min) / (src_max - src_min)
        
        # Scale to target range
        return int(target_min + normalized * (target_max - target_min))
    
    def _process_event(self, event) -> bool:
        """
        Process a single evdev event and update controller state.
        
        Args:
            event: evdev InputEvent
            
        Returns:
            True if state changed, False otherwise
        """
        changed = False
        
        if event.type == ecodes.EV_KEY:
            # Button events
            pressed = event.value == 1
            
            if event.code == XboxOneEventCodes.BTN_A:
                self.state.a = pressed
                changed = True
            elif event.code == XboxOneEventCodes.BTN_B:
                self.state.b = pressed
                changed = True
            elif event.code == XboxOneEventCodes.BTN_X:
                self.state.x = pressed
                changed = True
            elif event.code == XboxOneEventCodes.BTN_Y:
                self.state.y = pressed
                changed = True
            elif event.code == XboxOneEventCodes.BTN_TL:
                self.state.lb = pressed
                changed = True
            elif event.code == XboxOneEventCodes.BTN_TR:
                self.state.rb = pressed
                changed = True
            elif event.code == XboxOneEventCodes.BTN_SELECT:
                self.state.back = pressed
                changed = True
            elif event.code == XboxOneEventCodes.BTN_START:
                self.state.start = pressed
                changed = True
            elif event.code == XboxOneEventCodes.BTN_MODE:
                self.state.guide = pressed
                changed = True
            elif event.code == XboxOneEventCodes.BTN_THUMBL:
                self.state.left_stick_click = pressed
                changed = True
            elif event.code == XboxOneEventCodes.BTN_THUMBR:
                self.state.right_stick_click = pressed
                changed = True
        
        elif event.type == ecodes.EV_ABS:
            # Axis events
            if event.code == XboxOneEventCodes.ABS_X:
                self.state.left_stick_x = self._scale_axis(
                    event.code, event.value, -32768, 32767)
                changed = True
            elif event.code == XboxOneEventCodes.ABS_Y:
                # Note: Y axis may need inversion depending on driver
                self.state.left_stick_y = -self._scale_axis(
                    event.code, event.value, -32768, 32767)
                changed = True
            elif event.code == XboxOneEventCodes.ABS_RX:
                self.state.right_stick_x = self._scale_axis(
                    event.code, event.value, -32768, 32767)
                changed = True
            elif event.code == XboxOneEventCodes.ABS_RY:
                self.state.right_stick_y = -self._scale_axis(
                    event.code, event.value, -32768, 32767)
                changed = True
            elif event.code == XboxOneEventCodes.ABS_Z:
                self.state.left_trigger = self._scale_axis(
                    event.code, event.value, 0, 255)
                changed = True
            elif event.code == XboxOneEventCodes.ABS_RZ:
                self.state.right_trigger = self._scale_axis(
                    event.code, event.value, 0, 255)
                changed = True
            elif event.code == XboxOneEventCodes.ABS_HAT0X:
                # D-pad X axis (-1=left, 0=neutral, 1=right)
                self.state.dpad_left = event.value < 0
                self.state.dpad_right = event.value > 0
                changed = True
            elif event.code == XboxOneEventCodes.ABS_HAT0Y:
                # D-pad Y axis (-1=up, 0=neutral, 1=down)
                self.state.dpad_up = event.value < 0
                self.state.dpad_down = event.value > 0
                changed = True
        
        return changed
    
    def set_callback(self, callback: Callable[[ControllerState], None]) -> None:
        """
        Set callback function to be called when state changes.
        
        Args:
            callback: Function that takes ControllerState as argument
        """
        self.callback = callback
    
    def poll(self, timeout: float = 0.0) -> bool:
        """
        Poll for input events (non-blocking).
        
        Args:
            timeout: Maximum time to wait for events (0 = non-blocking)
            
        Returns:
            True if events were processed, False if timeout
        """
        if not self.device:
            return False
        
        # Use select for non-blocking read
        r, _, _ = select.select([self.device.fd], [], [], timeout)
        
        if not r:
            return False
        
        try:
            for event in self.device.read():
                if self._process_event(event):
                    if self.callback:
                        self.callback(self.state)
            return True
        except BlockingIOError:
            return False
    
    def run_loop(self, report_callback: Callable[[ControllerState], None],
                 poll_interval: float = 0.001) -> None:
        """
        Run the main input loop.
        
        Args:
            report_callback: Called when input state changes
            poll_interval: Polling interval in seconds
        """
        self.callback = report_callback
        
        logger.info("Starting input loop...")
        try:
            while True:
                self.poll(poll_interval)
                time.sleep(poll_interval)
        except KeyboardInterrupt:
            logger.info("Input loop stopped")
    
    def close(self) -> None:
        """Close the input device."""
        if self.device:
            self.device.close()
            self.device = None


def list_input_devices() -> None:
    """List all available input devices."""
    if not EVDEV_AVAILABLE:
        print("evdev not available")
        return
    
    print("Available input devices:\n")
    for path in evdev.list_devices():
        try:
            device = InputDevice(path)
            info = device.info
            print(f"  {path}:")
            print(f"    Name: {device.name}")
            print(f"    Vendor: 0x{info.vendor:04X}")
            print(f"    Product: 0x{info.product:04X}")
            print()
        except (PermissionError, FileNotFoundError):
            print(f"  {path}: (permission denied)")


def run_controller_state_tests() -> bool:
    """Run tests for ControllerState to verify all inputs are properly tracked.
    
    Returns:
        True if all tests pass, False otherwise.
    """
    print("=== Running ControllerState Tests ===\n")
    all_passed = True
    
    # Xbox 360 protocol constants (per USB_PROTOCOL.md)
    STICK_MAX = 32767   # Max positive stick value (16-bit signed)
    STICK_MIN = -32768  # Max negative stick value (16-bit signed)
    TRIGGER_MAX = 255   # Max trigger value (8-bit unsigned)
    
    # Test 1: Default state is all neutral
    print("Test 1: Default state initialization")
    state = ControllerState()
    
    # Check all buttons are False
    button_checks = [
        ('a', state.a),
        ('b', state.b),
        ('x', state.x),
        ('y', state.y),
        ('lb', state.lb),
        ('rb', state.rb),
        ('start', state.start),
        ('back', state.back),
        ('guide', state.guide),
        ('left_stick_click', state.left_stick_click),
        ('right_stick_click', state.right_stick_click),
        ('dpad_up', state.dpad_up),
        ('dpad_down', state.dpad_down),
        ('dpad_left', state.dpad_left),
        ('dpad_right', state.dpad_right),
    ]
    
    for name, value in button_checks:
        if value is not False:
            print(f"  FAIL: {name} should be False, got {value}")
            all_passed = False
    
    # Check analog values are 0
    analog_checks = [
        ('left_trigger', state.left_trigger, 0),
        ('right_trigger', state.right_trigger, 0),
        ('left_stick_x', state.left_stick_x, 0),
        ('left_stick_y', state.left_stick_y, 0),
        ('right_stick_x', state.right_stick_x, 0),
        ('right_stick_y', state.right_stick_y, 0),
    ]
    
    for name, value, expected in analog_checks:
        if value != expected:
            print(f"  FAIL: {name} should be {expected}, got {value}")
            all_passed = False
    
    if all_passed:
        print("  PASS: Default state is neutral for all inputs")
    
    # Test 2: All buttons can be set
    print("Test 2: Button state changes")
    state = ControllerState()
    
    # Set all buttons
    state.a = True
    state.b = True
    state.x = True
    state.y = True
    state.lb = True
    state.rb = True
    state.start = True
    state.back = True
    state.guide = True
    state.left_stick_click = True
    state.right_stick_click = True
    state.dpad_up = True
    state.dpad_down = True
    state.dpad_left = True
    state.dpad_right = True
    
    # Verify all are True
    button_checks = [
        ('a', state.a),
        ('b', state.b),
        ('x', state.x),
        ('y', state.y),
        ('lb', state.lb),
        ('rb', state.rb),
        ('start', state.start),
        ('back', state.back),
        ('guide', state.guide),
        ('left_stick_click', state.left_stick_click),
        ('right_stick_click', state.right_stick_click),
        ('dpad_up', state.dpad_up),
        ('dpad_down', state.dpad_down),
        ('dpad_left', state.dpad_left),
        ('dpad_right', state.dpad_right),
    ]
    
    for name, value in button_checks:
        if value is not True:
            print(f"  FAIL: {name} should be True after setting")
            all_passed = False
    
    if all_passed:
        print("  PASS: All buttons can be set to True")
    
    # Test 3: Analog values (triggers)
    print("Test 3: Trigger values")
    state = ControllerState()
    state.left_trigger = TRIGGER_MAX
    state.right_trigger = 128
    
    if state.left_trigger != TRIGGER_MAX:
        print(f"  FAIL: left_trigger should be {TRIGGER_MAX}, got {state.left_trigger}")
        all_passed = False
    else:
        print(f"  PASS: Left trigger can be set to {TRIGGER_MAX}")
    
    if state.right_trigger != 128:
        print(f"  FAIL: right_trigger should be 128, got {state.right_trigger}")
        all_passed = False
    else:
        print("  PASS: Right trigger can be set to 128")
    
    # Test 4: Analog values (sticks)
    print("Test 4: Stick values")
    state = ControllerState()
    state.left_stick_x = STICK_MAX
    state.left_stick_y = STICK_MIN
    state.right_stick_x = STICK_MIN
    state.right_stick_y = STICK_MAX
    
    if state.left_stick_x != STICK_MAX:
        print(f"  FAIL: left_stick_x should be {STICK_MAX}")
        all_passed = False
    else:
        print("  PASS: Left stick X can be set to full range")
    
    if state.left_stick_y != STICK_MIN:
        print(f"  FAIL: left_stick_y should be {STICK_MIN}")
        all_passed = False
    else:
        print("  PASS: Left stick Y can be set to full range")
    
    if state.right_stick_x != STICK_MIN:
        print(f"  FAIL: right_stick_x should be {STICK_MIN}")
        all_passed = False
    else:
        print("  PASS: Right stick X can be set to full range")
    
    if state.right_stick_y != STICK_MAX:
        print(f"  FAIL: right_stick_y should be {STICK_MAX}")
        all_passed = False
    else:
        print("  PASS: Right stick Y can be set to full range")
    
    # Test 5: String representation includes all inputs
    print("Test 5: String representation")
    state = ControllerState()
    state.a = True
    state.lb = True
    state.rb = True
    state.left_trigger = 100
    state.right_trigger = 200
    state.left_stick_x = 1000
    state.left_stick_y = 2000
    state.right_stick_x = 3000
    state.right_stick_y = 4000
    
    repr_str = repr(state)
    
    # Check that key elements are in the repr
    checks = ['A', 'LB', 'RB', 'LT=100', 'RT=200']
    for check in checks:
        if check not in repr_str:
            print(f"  FAIL: '{check}' not in repr: {repr_str}")
            all_passed = False
    
    if all_passed:
        print("  PASS: String representation includes all active inputs")
    
    print()
    return all_passed


if __name__ == "__main__":
    # Run unit tests first
    print("=== Input Handler Tests ===\n")
    
    # Run ControllerState tests (no evdev required)
    if not run_controller_state_tests():
        print("=== Some Tests Failed ===\n")
        sys.exit(1)
    
    print("=== All ControllerState Tests Passed ===\n")
    
    # Demo/test mode (requires evdev and actual controller)
    print("=== Input Handler Demo ===\n")
    
    if not EVDEV_AVAILABLE:
        print("Note: evdev module not available")
        print("Install with: pip3 install evdev")
        print("Skipping device detection (tests still passed)")
        sys.exit(0)
    
    print("Listing available devices...\n")
    list_input_devices()
    
    print("\nAttempting to auto-detect Xbox controller...")
    try:
        handler = InputHandler()
        print(f"Connected to: {handler.device.name}")
        print("\nReading input (Ctrl+C to stop)...\n")
        
        def on_change(state):
            print(f"\r{state}", end='', flush=True)
        
        handler.run_loop(on_change)
        
    except RuntimeError as e:
        print(f"Error: {e}")
        print("No Xbox controller found (this is OK for CI/testing)")
    except KeyboardInterrupt:
        print("\nStopped")
