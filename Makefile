# Xbox 360 Controller Emulator Makefile
#
# Usage:
#   make build       - Build C emulator
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
BIN_DIR := bin

CC := gcc
CFLAGS := -Wall -O2 -pthread
LDFLAGS := -lpthread

EMULATOR_SRC := $(SRC_DIR)/360_raw_emulator.c
EMULATOR_BIN := $(BIN_DIR)/xbox360_raw_emulator

.PHONY: all build install setup run teardown test clean lint help build-rawgadget

all: build

help:
	@echo "Xbox 360 Controller Emulator"
	@echo ""
	@echo "Usage:"
	@echo "  make build       Build C emulator binary"
	@echo "  make install     Install dependencies"
	@echo "  make setup       Configure USB gadget (requires root)"
	@echo "  make run         Run the emulator (requires root)"
	@echo "  make teardown    Remove USB gadget (requires root)"
	@echo "  make test        Run tests"
	@echo "  make lint        Run linter"
	@echo "  make clean       Clean temporary files"
	@echo "  make build-rawgadget  Build raw-gadget module"
	@echo ""

# Build C emulator
build: $(BIN_DIR)
	@echo "Building Xbox 360 raw-gadget emulator..."
	$(CC) $(CFLAGS) -o $(EMULATOR_BIN) $(EMULATOR_SRC) $(LDFLAGS)
	@echo "Built: $(EMULATOR_BIN)"

# Create bin directory
$(BIN_DIR):
	mkdir -p $(BIN_DIR)

# Install dependencies
install:
	@echo "Installing Python dependencies..."
	$(PIP) install evdev pyusb
	@echo ""
	@echo "Making scripts executable..."
	chmod +x $(SCRIPT_DIR)/*.sh
	@echo ""
	@echo "Installation complete!"
	@echo "Next steps:"
	@echo "  1. Build raw-gadget: make build-rawgadget"
	@echo "  2. Build C emulator: make build"
	@echo "  3. Run: sudo make run"

# Build raw-gadget kernel module
build-rawgadget:
	@echo "Building raw-gadget kernel module..."
	@if [ ! -d /tmp/raw-gadget ]; then \
		echo "Cloning raw-gadget..."; \
		cd /tmp && git clone https://github.com/xairy/raw-gadget.git; \
	fi
	@echo "Compiling module..."
	@cd /tmp/raw-gadget && make
	@echo ""
	@echo "raw-gadget module built: /tmp/raw-gadget/raw_gadget.ko"
	@echo "Install with: sudo make install-rawgadget"

# Install raw-gadget module
install-rawgadget:
	@if [ ! -f /tmp/raw-gadget/raw_gadget.ko ]; then \
		echo "Error: raw-gadget module not built. Run 'make build-rawgadget' first."; \
		exit 1; \
	fi
	@echo "Installing raw-gadget module..."
	@cd /tmp/raw-gadget && sudo make install
	@sudo modprobe raw_gadget
	@echo "raw-gadget module installed and loaded"
	@echo "Checking module:"
	@lsmod | grep raw_gadget || echo "  Warning: Module not loaded"
	@ls -l /dev/raw-gadget 2>/dev/null || echo "  Warning: Device node not found"

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
	@if [ ! -f $(EMULATOR_BIN) ]; then \
		echo "Error: Emulator not built. Run 'make build' first."; \
		exit 1; \
	fi
	@echo "Starting Xbox 360 raw-gadget emulator..."
	$(EMULATOR_BIN)

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
	@echo "Running input handler tests..."
	$(PYTHON) $(SRC_DIR)/input_handler.py
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
	rm -f $(EMULATOR_BIN)
	@echo "Clean complete!"

# Show system status
status:
	@echo "=== System Status ==="
	@echo ""
	@echo "Kernel modules:"
	@lsmod | grep -E "(raw_gadget|dwc2)" || echo "  (none loaded)"
	@echo ""
	@echo "raw-gadget device:"
	@ls -l /dev/raw-gadget 2>/dev/null || echo "  (not available)"
	@echo ""
	@echo "Emulator binary:"
	@if [ -f $(EMULATOR_BIN) ]; then \
		echo "  Built: $(EMULATOR_BIN)"; \
		ls -lh $(EMULATOR_BIN); \
	else \
		echo "  Not built (run 'make build')"; \
	fi
	@echo ""
	@echo "Input devices:"
	@ls /dev/input/event* 2>/dev/null | head -5 || echo "  (none)"
