#!/usr/bin/env python3
"""
Input Bridge for Xbox 360 Controller Emulator

This script bridges input from a source controller (e.g., Bluetooth Xbox 
One/Series controller) to the C raw-gadget emulator via stdout pipe.

Architecture:
  - Reads input from source controller via evdev
  - Formats input as 20-byte Xbox 360 input reports
  - Writes reports to stdout (binary) for piping to C emulator

Usage:
    python3 input_bridge.py | sudo ./bin/xbox360_raw_emulator
    
    # Or specify a device:
    python3 input_bridge.py --input /dev/input/event0 | sudo ./bin/xbox360_raw_emulator

    # Debug mode (doesn't write to stdout, shows reports):
    python3 input_bridge.py --debug

Options:
    --input DEVICE    Path to input device (auto-detect if not specified)
    --debug           Show debug output instead of writing to stdout
    --rate HZ         Report rate in Hz (default: 125)
    --list-devices    List available input devices and exit
"""

import sys
import os
import time
import argparse
import logging
import signal
from typing import Optional

# Ensure we can import from the same directory
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from report_formatter import InputReport, format_report_hex

# Try to import input_handler
try:
    from input_handler import InputHandler, ControllerState, EVDEV_AVAILABLE, list_input_devices
except ImportError:
    EVDEV_AVAILABLE = False


# Report interval for Xbox 360 (125Hz = 8ms)
DEFAULT_REPORT_RATE = 125  # Hz

# Flag to signal that the bridge should stop
_stop_requested = False


def _signal_handler(signum, frame):
    """Handle signals to stop the bridge gracefully."""
    global _stop_requested
    _stop_requested = True


def state_to_report(state: ControllerState) -> bytes:
    """
    Convert a ControllerState to a 20-byte Xbox 360 input report.
    
    Args:
        state: Current controller state from input_handler
        
    Returns:
        bytes: 20-byte input report
    """
    report = InputReport()
    
    # Map buttons
    report.set_a(state.a)
    report.set_b(state.b)
    report.set_x(state.x)
    report.set_y(state.y)
    report.set_lb(state.lb)
    report.set_rb(state.rb)
    report.set_start(state.start)
    report.set_back(state.back)
    report.set_guide(state.guide)
    report.set_left_stick_click(state.left_stick_click)
    report.set_right_stick_click(state.right_stick_click)
    
    # Map D-pad
    report.set_dpad_up(state.dpad_up)
    report.set_dpad_down(state.dpad_down)
    report.set_dpad_left(state.dpad_left)
    report.set_dpad_right(state.dpad_right)
    
    # Map triggers
    report.set_left_trigger(state.left_trigger)
    report.set_right_trigger(state.right_trigger)
    
    # Map sticks
    report.set_left_stick(state.left_stick_x, state.left_stick_y)
    report.set_right_stick(state.right_stick_x, state.right_stick_y)
    
    return report.to_bytes()


def run_bridge(input_device: Optional[str] = None, 
               debug_mode: bool = False,
               report_rate: int = DEFAULT_REPORT_RATE) -> None:
    """
    Run the input bridge loop.
    
    This function reads from the input controller and writes 20-byte
    reports to stdout at the specified rate.
    
    Args:
        input_device: Path to input device (None for auto-detect)
        debug_mode: If True, print debug info instead of binary output
        report_rate: Report rate in Hz
    """
    global _stop_requested
    
    # Set up signal handlers for graceful shutdown FIRST, before any other operations
    # SIGPIPE: Broken pipe (C emulator exited)
    # SIGINT: Ctrl+C
    # SIGTERM: termination request
    signal.signal(signal.SIGPIPE, _signal_handler)
    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)
    
    if not EVDEV_AVAILABLE:
        print("Error: evdev module not available. Install with: pip3 install evdev", 
              file=sys.stderr)
        sys.exit(1)
    
    # Initialize input handler
    try:
        handler = InputHandler(input_device)
        print(f"Connected to: {handler.device.name}", file=sys.stderr)
    except RuntimeError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except (FileNotFoundError, PermissionError) as e:
        print(f"Error opening device: {e}", file=sys.stderr)
        sys.exit(1)
    
    # Calculate sleep interval
    interval = 1.0 / report_rate
    
    # For non-debug mode, ensure stdout is binary and unbuffered
    stdout_binary = None
    if not debug_mode:
        # Re-open stdout in binary mode, unbuffered
        stdout_binary = os.fdopen(sys.stdout.fileno(), 'wb', 0)
    
    print(f"Starting input bridge (rate: {report_rate}Hz, interval: {interval*1000:.1f}ms)",
          file=sys.stderr)
    print("Press Ctrl+C to stop", file=sys.stderr)
    
    report_count = 0
    last_time = time.time()
    stopped_by_signal = False
    
    try:
        while not _stop_requested:
            # Poll for input events
            handler.poll(0.001)
            
            # Get current state
            state = handler.state
            
            # Convert to report
            report_bytes = state_to_report(state)
            
            if debug_mode:
                # Debug mode: print hex representation
                report_count += 1
                if report_count % 100 == 0:
                    print(f"Reports sent: {report_count}", file=sys.stderr)
                # Only print when state changes (to reduce noise)
                # For debugging, print every N reports
                if report_count % 10 == 0:
                    print(f"Report: {format_report_hex(report_bytes)}")
            else:
                # Normal mode: write binary to stdout
                try:
                    stdout_binary.write(report_bytes)
                except (BrokenPipeError, OSError):
                    # C emulator has exited or pipe error
                    print("Pipe closed, exiting", file=sys.stderr)
                    break
            
            report_count += 1
            
            # Sleep to maintain rate
            elapsed = time.time() - last_time
            if elapsed < interval:
                time.sleep(interval - elapsed)
            last_time = time.time()
        
        # If we exited because _stop_requested was set, it was due to a signal
        if _stop_requested:
            stopped_by_signal = True
            
    except KeyboardInterrupt:
        stopped_by_signal = True
    finally:
        handler.close()
        # Close stdout_binary to ensure no more writes
        if stdout_binary is not None:
            try:
                stdout_binary.close()
            except (BrokenPipeError, OSError):
                pass  # Ignore errors on close
        if stopped_by_signal:
            print("\nStopped by user", file=sys.stderr)
        print(f"Total reports sent: {report_count}", file=sys.stderr)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='Input bridge for Xbox 360 Controller Emulator',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Auto-detect controller and pipe to C emulator:
  python3 input_bridge.py | sudo ./bin/xbox360_raw_emulator
  
  # Specify input device:
  python3 input_bridge.py --input /dev/input/event0 | sudo ./bin/xbox360_raw_emulator
  
  # Debug mode (shows reports without piping):
  python3 input_bridge.py --debug
  
  # List available devices:
  python3 input_bridge.py --list-devices
"""
    )
    parser.add_argument(
        '--input', '-i',
        dest='input_device',
        help='Path to input device (auto-detect if not specified)'
    )
    parser.add_argument(
        '--debug', '-d',
        action='store_true',
        help='Debug mode: print reports instead of binary output'
    )
    parser.add_argument(
        '--rate', '-r',
        type=int,
        default=DEFAULT_REPORT_RATE,
        help=f'Report rate in Hz (default: {DEFAULT_REPORT_RATE})'
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
            list_input_devices()
        else:
            print("evdev not available. Install with: pip3 install evdev")
        return
    
    # Check prerequisites
    if not EVDEV_AVAILABLE:
        print("Error: evdev module not available.", file=sys.stderr)
        print("Install with: pip3 install evdev", file=sys.stderr)
        sys.exit(1)
    
    # Run the bridge
    run_bridge(
        input_device=args.input_device,
        debug_mode=args.debug,
        report_rate=args.rate
    )


if __name__ == "__main__":
    main()
