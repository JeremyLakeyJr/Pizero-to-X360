# Xbox 360 Controller Emulator Makefile
#
# Usage:
#   make install     - Install the emulator and dependencies
#   make setup       - Configure USB gadget
#   make run         - Run the emulator
#   make teardown    - Remove USB gadget configuration
#   make test        - Run tests
#   make clean       - Clean temporary files
#   make lint        - Run linter
#

PYTHON := python3
PIP := pip3
SCRIPT_DIR := scripts
SRC_DIR := src

.PHONY: all install setup run teardown test clean lint help

all: help

help:
	@echo "Xbox 360 Controller Emulator"
	@echo ""
	@echo "Usage:"
	@echo "  make install     Install dependencies"
	@echo "  make setup       Configure USB gadget (requires root)"
	@echo "  make run         Run the emulator (requires root)"
	@echo "  make teardown    Remove USB gadget (requires root)"
	@echo "  make test        Run tests"
	@echo "  make lint        Run linter"
	@echo "  make clean       Clean temporary files"
	@echo ""

# Install dependencies
install:
	@echo "Installing Python dependencies..."
	$(PIP) install evdev pyusb
	@echo ""
	@echo "Making scripts executable..."
	chmod +x $(SCRIPT_DIR)/*.sh
	@echo ""
	@echo "Installation complete!"
	@echo "Run 'sudo make setup' to configure USB gadget"

# Full installation (requires root)
install-full:
	sudo $(SCRIPT_DIR)/install.sh

# Set up USB gadget
setup:
	@if [ "$$(id -u)" -ne 0 ]; then \
		echo "Error: This target must be run as root"; \
		echo "Usage: sudo make setup"; \
		exit 1; \
	fi
	$(SCRIPT_DIR)/setup_gadget.sh

# Run the emulator
run:
	@if [ "$$(id -u)" -ne 0 ]; then \
		echo "Error: This target must be run as root"; \
		echo "Usage: sudo make run"; \
		exit 1; \
	fi
	$(PYTHON) $(SRC_DIR)/xbox360_emulator.py

# Run in dry-run mode (no root required)
run-dry:
	$(PYTHON) $(SRC_DIR)/xbox360_emulator.py --dry-run --debug

# Run with debug output
run-debug:
	@if [ "$$(id -u)" -ne 0 ]; then \
		echo "Error: This target must be run as root"; \
		echo "Usage: sudo make run-debug"; \
		exit 1; \
	fi
	$(PYTHON) $(SRC_DIR)/xbox360_emulator.py --debug

# Remove USB gadget
teardown:
	@if [ "$$(id -u)" -ne 0 ]; then \
		echo "Error: This target must be run as root"; \
		echo "Usage: sudo make teardown"; \
		exit 1; \
	fi
	$(SCRIPT_DIR)/teardown_gadget.sh

# Run tests
test:
	@echo "Running descriptor tests..."
	$(PYTHON) $(SRC_DIR)/xbox360_descriptors.py
	@echo ""
	@echo "Running report formatter tests..."
	$(PYTHON) $(SRC_DIR)/report_formatter.py
	@echo ""
	@echo "All tests passed!"

# List available input devices
list-devices:
	$(PYTHON) $(SRC_DIR)/xbox360_emulator.py --list-devices

# Run linter
lint:
	@echo "Checking Python syntax..."
	$(PYTHON) -m py_compile $(SRC_DIR)/*.py
	@echo "Syntax check passed!"
	@echo ""
	@if command -v pylint >/dev/null 2>&1; then \
		echo "Running pylint..."; \
		pylint --disable=C0114,C0115,C0116 $(SRC_DIR)/*.py || true; \
	else \
		echo "pylint not installed. Install with: pip3 install pylint"; \
	fi

# Clean temporary files
clean:
	@echo "Cleaning temporary files..."
	rm -f $(SRC_DIR)/__pycache__/*.pyc
	rm -rf $(SRC_DIR)/__pycache__
	rm -f *.pyc
	rm -rf __pycache__
	rm -f /tmp/xbox360_*.bin
	@echo "Clean complete!"

# Show system status
status:
	@echo "=== System Status ==="
	@echo ""
	@echo "Kernel modules:"
	@lsmod | grep -E "(libcomposite|usb_f_hid|dwc2)" || echo "  (none loaded)"
	@echo ""
	@echo "USB gadget:"
	@if [ -d "/sys/kernel/config/usb_gadget/xbox360" ]; then \
		echo "  Configured: yes"; \
		cat /sys/kernel/config/usb_gadget/xbox360/UDC 2>/dev/null && echo "" || echo "  UDC: (not bound)"; \
	else \
		echo "  Configured: no"; \
	fi
	@echo ""
	@echo "HID device:"
	@ls -la /dev/hidg* 2>/dev/null || echo "  (not available)"
	@echo ""
	@echo "Input devices:"
	@ls /dev/input/event* 2>/dev/null | head -5 || echo "  (none)"
