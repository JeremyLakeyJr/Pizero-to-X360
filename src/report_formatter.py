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
            '<BBHBB hhhh xxxxxx',
            self.REPORT_TYPE,      # Byte 0: Report type
            self.REPORT_SIZE,      # Byte 1: Report size
            self._buttons,         # Bytes 2-3: Button bitmap
            self._left_trigger,    # Byte 4: Left trigger
            self._right_trigger,   # Byte 5: Right trigger
            self._left_stick_x,    # Bytes 6-7: Left stick X
            self._left_stick_y,    # Bytes 8-9: Left stick Y
            self._right_stick_x,   # Bytes 10-11: Right stick X
            self._right_stick_y,   # Bytes 12-13: Right stick Y
            # Bytes 14-19: Reserved (padding via 'xxxxxx')
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


if __name__ == "__main__":
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
