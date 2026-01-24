#!/usr/bin/env python3
"""
Xbox 360 Input Report Formatter

This module handles formatting input data into the Xbox 360 controller
input report format. The report is a 20-byte structure sent to the
Xbox 360 console.

Report Format (20 bytes):
    Byte 0:     Report type (0x00)
    Byte 1:     Report size (0x14 = 20)
    Bytes 2-3:  Button bitmap (16 bits)
    Byte 4:     Left trigger (0-255)
    Byte 5:     Right trigger (0-255)
    Bytes 6-7:  Left stick X (signed 16-bit, little endian)
    Bytes 8-9:  Left stick Y (signed 16-bit, little endian)
    Bytes 10-11: Right stick X (signed 16-bit, little endian)
    Bytes 12-13: Right stick Y (signed 16-bit, little endian)
    Bytes 14-19: Reserved (zeros)
"""

import struct
from typing import Optional
from xbox360_descriptors import Xbox360Buttons


class InputReport:
    """
    Represents an Xbox 360 controller input report.
    
    This class builds the 20-byte input report that is sent to the
    Xbox 360 console. All values can be set individually and the
    report can be serialized to bytes.
    """
    
    REPORT_SIZE = 20
    REPORT_TYPE = 0x00
    
    def __init__(self):
        """Initialize an empty input report with neutral values."""
        # Button states (bit flags)
        self._buttons = 0
        
        # Analog triggers (0-255)
        self._left_trigger = 0
        self._right_trigger = 0
        
        # Analog sticks (signed 16-bit, -32768 to 32767)
        self._left_stick_x = 0
        self._left_stick_y = 0
        self._right_stick_x = 0
        self._right_stick_y = 0
    
    # Button setters
    def set_button(self, button: int, pressed: bool) -> None:
        """
        Set a button state.
        
        Args:
            button: Button bit position from Xbox360Buttons
            pressed: True if pressed, False if released
        """
        if pressed:
            self._buttons |= (1 << button)
        else:
            self._buttons &= ~(1 << button)
    
    def set_dpad_up(self, pressed: bool) -> None:
        """Set D-pad Up state."""
        self.set_button(Xbox360Buttons.DPAD_UP, pressed)
    
    def set_dpad_down(self, pressed: bool) -> None:
        """Set D-pad Down state."""
        self.set_button(Xbox360Buttons.DPAD_DOWN, pressed)
    
    def set_dpad_left(self, pressed: bool) -> None:
        """Set D-pad Left state."""
        self.set_button(Xbox360Buttons.DPAD_LEFT, pressed)
    
    def set_dpad_right(self, pressed: bool) -> None:
        """Set D-pad Right state."""
        self.set_button(Xbox360Buttons.DPAD_RIGHT, pressed)
    
    def set_start(self, pressed: bool) -> None:
        """Set Start button state."""
        self.set_button(Xbox360Buttons.START, pressed)
    
    def set_back(self, pressed: bool) -> None:
        """Set Back button state."""
        self.set_button(Xbox360Buttons.BACK, pressed)
    
    def set_left_stick_click(self, pressed: bool) -> None:
        """Set Left Stick click state."""
        self.set_button(Xbox360Buttons.LEFT_STICK, pressed)
    
    def set_right_stick_click(self, pressed: bool) -> None:
        """Set Right Stick click state."""
        self.set_button(Xbox360Buttons.RIGHT_STICK, pressed)
    
    def set_lb(self, pressed: bool) -> None:
        """Set Left Bumper (LB) state."""
        self.set_button(Xbox360Buttons.LB, pressed)
    
    def set_rb(self, pressed: bool) -> None:
        """Set Right Bumper (RB) state."""
        self.set_button(Xbox360Buttons.RB, pressed)
    
    def set_guide(self, pressed: bool) -> None:
        """Set Xbox Guide button state."""
        self.set_button(Xbox360Buttons.GUIDE, pressed)
    
    def set_a(self, pressed: bool) -> None:
        """Set A button state."""
        self.set_button(Xbox360Buttons.A, pressed)
    
    def set_b(self, pressed: bool) -> None:
        """Set B button state."""
        self.set_button(Xbox360Buttons.B, pressed)
    
    def set_x(self, pressed: bool) -> None:
        """Set X button state."""
        self.set_button(Xbox360Buttons.X, pressed)
    
    def set_y(self, pressed: bool) -> None:
        """Set Y button state."""
        self.set_button(Xbox360Buttons.Y, pressed)
    
    # Trigger setters
    def set_left_trigger(self, value: int) -> None:
        """
        Set left trigger value.
        
        Args:
            value: Trigger pressure (0-255)
        """
        self._left_trigger = max(0, min(255, value))
    
    def set_right_trigger(self, value: int) -> None:
        """
        Set right trigger value.
        
        Args:
            value: Trigger pressure (0-255)
        """
        self._right_trigger = max(0, min(255, value))
    
    # Stick setters
    def set_left_stick(self, x: int, y: int) -> None:
        """
        Set left analog stick position.
        
        Args:
            x: X axis (-32768 to 32767, negative=left)
            y: Y axis (-32768 to 32767, negative=down)
        """
        self._left_stick_x = max(-32768, min(32767, x))
        self._left_stick_y = max(-32768, min(32767, y))
    
    def set_right_stick(self, x: int, y: int) -> None:
        """
        Set right analog stick position.
        
        Args:
            x: X axis (-32768 to 32767, negative=left)
            y: Y axis (-32768 to 32767, negative=down)
        """
        self._right_stick_x = max(-32768, min(32767, x))
        self._right_stick_y = max(-32768, min(32767, y))
    
    def to_bytes(self) -> bytes:
        """
        Serialize the input report to bytes.
        
        Returns:
            bytes: 20-byte input report
        """
        # Pack the report structure
        # Format: < = little endian
        #   B = unsigned char (1 byte)
        #   H = unsigned short (2 bytes)
        #   h = signed short (2 bytes)
        report = struct.pack(
            '<BBHBB hhhh 6x',
            self.REPORT_TYPE,      # Byte 0: Report type
            self.REPORT_SIZE,      # Byte 1: Report size
            self._buttons,         # Bytes 2-3: Button bitmap
            self._left_trigger,    # Byte 4: Left trigger
            self._right_trigger,   # Byte 5: Right trigger
            self._left_stick_x,    # Bytes 6-7: Left stick X
            self._left_stick_y,    # Bytes 8-9: Left stick Y
            self._right_stick_x,   # Bytes 10-11: Right stick X
            self._right_stick_y,   # Bytes 12-13: Right stick Y
            # Bytes 14-19: Reserved (padding via '6x')
        )
        
        return report
    
    def reset(self) -> None:
        """Reset all values to neutral/released state."""
        self._buttons = 0
        self._left_trigger = 0
        self._right_trigger = 0
        self._left_stick_x = 0
        self._left_stick_y = 0
        self._right_stick_x = 0
        self._right_stick_y = 0
    
    def __repr__(self) -> str:
        """String representation for debugging."""
        return (
            f"InputReport("
            f"buttons=0x{self._buttons:04X}, "
            f"LT={self._left_trigger}, RT={self._right_trigger}, "
            f"LS=({self._left_stick_x}, {self._left_stick_y}), "
            f"RS=({self._right_stick_x}, {self._right_stick_y}))"
        )


class OutputReport:
    """
    Parser for Xbox 360 output reports (rumble and LED commands).
    
    The Xbox 360 sends output reports to the controller for:
    - Rumble/vibration feedback
    - LED status/pattern control
    """
    
    @staticmethod
    def parse(data: bytes) -> Optional[dict]:
        """
        Parse an output report from the Xbox 360.
        
        Args:
            data: Raw output report bytes
            
        Returns:
            dict: Parsed report data, or None if invalid
        """
        if not data or len(data) < 3:
            return None
        
        report_type = data[0]
        report_size = data[1]
        
        # Rumble report
        if report_type == 0x00 and report_size >= 0x08:
            if len(data) >= 8:
                return {
                    'type': 'rumble',
                    'left_motor': data[3],   # Big motor (low frequency)
                    'right_motor': data[4],  # Small motor (high frequency)
                }
        
        # LED control report
        if report_type == 0x01 and report_size >= 0x03:
            if len(data) >= 3:
                return {
                    'type': 'led',
                    'pattern': data[2],
                }
        
        return {'type': 'unknown', 'data': data.hex()}


def create_idle_report() -> bytes:
    """
    Create an idle input report (all buttons released, sticks centered).
    
    Returns:
        bytes: 20-byte idle input report
    """
    report = InputReport()
    return report.to_bytes()


def format_report_hex(report: bytes) -> str:
    """
    Format a report as a hex string for debugging.
    
    Args:
        report: Raw report bytes
        
    Returns:
        str: Space-separated hex string
    """
    return ' '.join(f'{b:02X}' for b in report)


def run_tests() -> bool:
    """Run comprehensive tests for all inputs.
    
    Returns:
        True if all tests pass, False otherwise.
    """
    print("=== Running Comprehensive Input Tests ===\n")
    all_passed = True
    
    # Xbox 360 protocol constants (per USB_PROTOCOL.md)
    STICK_MAX = 32767   # Max positive stick value (16-bit signed)
    STICK_MIN = -32768  # Max negative stick value (16-bit signed)
    TRIGGER_MAX = 255   # Max trigger value (8-bit unsigned)
    
    # Test 1: Idle report structure
    print("Test 1: Idle report structure")
    idle = create_idle_report()
    assert len(idle) == 20, f"Expected 20 bytes, got {len(idle)}"
    assert idle[0] == 0x00, f"Expected report type 0x00, got {idle[0]}"
    assert idle[1] == 0x14, f"Expected report size 0x14, got {idle[1]}"
    print("  PASS: Idle report is 20 bytes with correct header")
    
    # Test 2: All face buttons (A, B, X, Y)
    print("Test 2: Face buttons (A, B, X, Y)")
    for btn_name, btn_setter, expected_bit in [
        ('A', 'set_a', 12),
        ('B', 'set_b', 13),
        ('X', 'set_x', 14),
        ('Y', 'set_y', 15),
    ]:
        report = InputReport()
        getattr(report, btn_setter)(True)
        data = report.to_bytes()
        btn_word = data[2] | (data[3] << 8)
        if not (btn_word & (1 << expected_bit)):
            print(f"  FAIL: {btn_name} button not set correctly")
            all_passed = False
        else:
            print(f"  PASS: {btn_name} button (bit {expected_bit})")
    
    # Test 3: Bumpers (LB, RB)
    print("Test 3: Bumpers (LB, RB)")
    for btn_name, btn_setter, expected_bit in [
        ('LB', 'set_lb', 8),
        ('RB', 'set_rb', 9),
    ]:
        report = InputReport()
        getattr(report, btn_setter)(True)
        data = report.to_bytes()
        btn_word = data[2] | (data[3] << 8)
        if not (btn_word & (1 << expected_bit)):
            print(f"  FAIL: {btn_name} button not set correctly")
            all_passed = False
        else:
            print(f"  PASS: {btn_name} button (bit {expected_bit})")
    
    # Test 4: Triggers (analog, 0-255)
    print("Test 4: Triggers (LT, RT)")
    report = InputReport()
    report.set_left_trigger(TRIGGER_MAX)  # Full press
    report.set_right_trigger(128)  # Half press
    data = report.to_bytes()
    if data[4] != TRIGGER_MAX:
        print(f"  FAIL: Left trigger expected {TRIGGER_MAX}, got {data[4]}")
        all_passed = False
    else:
        print(f"  PASS: Left trigger = {TRIGGER_MAX} (full press)")
    if data[5] != 128:
        print(f"  FAIL: Right trigger expected 128, got {data[5]}")
        all_passed = False
    else:
        print(f"  PASS: Right trigger = 128 (half press)")
    
    # Test 5: D-pad
    print("Test 5: D-pad")
    for btn_name, btn_setter, expected_bit in [
        ('Up', 'set_dpad_up', 0),
        ('Down', 'set_dpad_down', 1),
        ('Left', 'set_dpad_left', 2),
        ('Right', 'set_dpad_right', 3),
    ]:
        report = InputReport()
        getattr(report, btn_setter)(True)
        data = report.to_bytes()
        btn_word = data[2] | (data[3] << 8)
        if not (btn_word & (1 << expected_bit)):
            print(f"  FAIL: D-pad {btn_name} not set correctly")
            all_passed = False
        else:
            print(f"  PASS: D-pad {btn_name} (bit {expected_bit})")
    
    # Test 6: System buttons (Start, Back, Guide)
    print("Test 6: System buttons (Start, Back, Guide)")
    for btn_name, btn_setter, expected_bit in [
        ('Start', 'set_start', 4),
        ('Back', 'set_back', 5),
        ('Guide', 'set_guide', 10),
    ]:
        report = InputReport()
        getattr(report, btn_setter)(True)
        data = report.to_bytes()
        btn_word = data[2] | (data[3] << 8)
        if not (btn_word & (1 << expected_bit)):
            print(f"  FAIL: {btn_name} button not set correctly")
            all_passed = False
        else:
            print(f"  PASS: {btn_name} button (bit {expected_bit})")
    
    # Test 7: Stick clicks
    print("Test 7: Stick clicks (LS, RS)")
    for btn_name, btn_setter, expected_bit in [
        ('LS', 'set_left_stick_click', 6),
        ('RS', 'set_right_stick_click', 7),
    ]:
        report = InputReport()
        getattr(report, btn_setter)(True)
        data = report.to_bytes()
        btn_word = data[2] | (data[3] << 8)
        if not (btn_word & (1 << expected_bit)):
            print(f"  FAIL: {btn_name} click not set correctly")
            all_passed = False
        else:
            print(f"  PASS: {btn_name} click (bit {expected_bit})")
    
    # Test 8: Analog sticks
    print("Test 8: Analog sticks")
    report = InputReport()
    report.set_left_stick(STICK_MAX, STICK_MIN)   # Full right, full down
    report.set_right_stick(STICK_MIN, STICK_MAX)  # Full left, full up
    data = report.to_bytes()
    # Left stick X (bytes 6-7, little endian)
    lx = struct.unpack('<h', data[6:8])[0]
    ly = struct.unpack('<h', data[8:10])[0]
    rx = struct.unpack('<h', data[10:12])[0]
    ry = struct.unpack('<h', data[12:14])[0]
    if lx != STICK_MAX:
        print(f"  FAIL: Left stick X expected {STICK_MAX}, got {lx}")
        all_passed = False
    else:
        print(f"  PASS: Left stick X = {STICK_MAX} (full right)")
    if ly != STICK_MIN:
        print(f"  FAIL: Left stick Y expected {STICK_MIN}, got {ly}")
        all_passed = False
    else:
        print(f"  PASS: Left stick Y = {STICK_MIN} (full down)")
    if rx != STICK_MIN:
        print(f"  FAIL: Right stick X expected {STICK_MIN}, got {rx}")
        all_passed = False
    else:
        print(f"  PASS: Right stick X = {STICK_MIN} (full left)")
    if ry != STICK_MAX:
        print(f"  FAIL: Right stick Y expected {STICK_MAX}, got {ry}")
        all_passed = False
    else:
        print(f"  PASS: Right stick Y = {STICK_MAX} (full up)")
    
    # Test 9: Combined inputs (simulate real gameplay)
    print("Test 9: Combined inputs (realistic gameplay scenario)")
    report = InputReport()
    report.set_a(True)           # Jump
    report.set_lb(True)          # Left bumper
    report.set_rb(True)          # Right bumper
    report.set_left_trigger(200) # Aim
    report.set_right_trigger(TRIGGER_MAX) # Fire
    report.set_left_stick(16000, 8000)  # Moving
    report.set_right_stick(-5000, 3000) # Aiming
    data = report.to_bytes()
    
    btn_word = data[2] | (data[3] << 8)
    if not (btn_word & (1 << 12)):  # A
        print(f"  FAIL: A button not set in combined test")
        all_passed = False
    if not (btn_word & (1 << 8)):   # LB
        print(f"  FAIL: LB button not set in combined test")
        all_passed = False
    if not (btn_word & (1 << 9)):   # RB
        print(f"  FAIL: RB button not set in combined test")
        all_passed = False
    if data[4] != 200:  # LT
        print(f"  FAIL: Left trigger expected 200, got {data[4]}")
        all_passed = False
    if data[5] != TRIGGER_MAX:  # RT
        print(f"  FAIL: Right trigger expected {TRIGGER_MAX}, got {data[5]}")
        all_passed = False
    print(f"  PASS: Combined inputs work correctly")
    
    # Test 10: Trigger value clamping
    print("Test 10: Trigger value clamping")
    report = InputReport()
    report.set_left_trigger(300)   # Should clamp to 255
    report.set_right_trigger(-10)  # Should clamp to 0
    data = report.to_bytes()
    if data[4] != TRIGGER_MAX:
        print(f"  FAIL: Left trigger should clamp to {TRIGGER_MAX}, got {data[4]}")
        all_passed = False
    else:
        print(f"  PASS: Left trigger clamped 300->{TRIGGER_MAX}")
    if data[5] != 0:
        print(f"  FAIL: Right trigger should clamp to 0, got {data[5]}")
        all_passed = False
    else:
        print(f"  PASS: Right trigger clamped -10->0")
    
    # Test 11: Output report parsing
    print("Test 11: Output report parsing")
    rumble_data = bytes([0x00, 0x08, 0x00, 0xFF, 0x80, 0x00, 0x00, 0x00])
    parsed = OutputReport.parse(rumble_data)
    if parsed['type'] != 'rumble':
        print(f"  FAIL: Expected rumble type, got {parsed['type']}")
        all_passed = False
    elif parsed['left_motor'] != 255 or parsed['right_motor'] != 128:
        print(f"  FAIL: Wrong motor values: {parsed}")
        all_passed = False
    else:
        print(f"  PASS: Rumble report parsed correctly")
    
    led_data = bytes([0x01, 0x03, 0x06])
    parsed = OutputReport.parse(led_data)
    if parsed['type'] != 'led' or parsed['pattern'] != 6:
        print(f"  FAIL: LED report not parsed correctly: {parsed}")
        all_passed = False
    else:
        print(f"  PASS: LED report parsed correctly")
    
    print()
    return all_passed


if __name__ == "__main__":
    # Run comprehensive tests
    if run_tests():
        print("=== All Tests Passed ===\n")
    else:
        print("=== Some Tests Failed ===\n")
        import sys
        sys.exit(1)
    
    # Demo: Create and display sample reports
    print("=== Xbox 360 Input Report Formatter Demo ===\n")
    
    # Idle report
    print("Idle report:")
    idle = create_idle_report()
    print(f"  {format_report_hex(idle)}")
    print(f"  Length: {len(idle)} bytes")
    
    # Report with some buttons pressed
    print("\nReport with A + B + Start pressed:")
    report = InputReport()
    report.set_a(True)
    report.set_b(True)
    report.set_start(True)
    data = report.to_bytes()
    print(f"  {format_report_hex(data)}")
    print(f"  {report}")
    
    # Report with analog inputs
    print("\nReport with left stick full right, triggers half:")
    report = InputReport()
    report.set_left_stick(32767, 0)  # Full right
    report.set_left_trigger(128)
    report.set_right_trigger(128)
    data = report.to_bytes()
    print(f"  {format_report_hex(data)}")
    print(f"  {report}")
    
    # Report with bumpers pressed
    print("\nReport with LB + RB pressed:")
    report = InputReport()
    report.set_lb(True)
    report.set_rb(True)
    data = report.to_bytes()
    print(f"  {format_report_hex(data)}")
    print(f"  {report}")
    
    # Report with full triggers
    print("\nReport with full triggers (LT=255, RT=255):")
    report = InputReport()
    report.set_left_trigger(255)
    report.set_right_trigger(255)
    data = report.to_bytes()
    print(f"  {format_report_hex(data)}")
    print(f"  {report}")
    
    # Parse sample output report
    print("\n=== Output Report Parser Demo ===\n")
    
    # Sample rumble report
    rumble_data = bytes([0x00, 0x08, 0x00, 0xFF, 0x80, 0x00, 0x00, 0x00])
    parsed = OutputReport.parse(rumble_data)
    print(f"Rumble report: {parsed}")
    
    # Sample LED report
    led_data = bytes([0x01, 0x03, 0x06])
    parsed = OutputReport.parse(led_data)
    print(f"LED report: {parsed}")
