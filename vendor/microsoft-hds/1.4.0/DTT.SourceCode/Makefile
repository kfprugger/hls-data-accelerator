# ============================================
# DTT Makefile (Open Source Friendly)
# ============================================
.NOTPARALLEL:
.PHONY: help check-python setup build rebuild install clean clean-all reset lint lint-install

# -------- Python Detection (>= 3.10, < 4.0) --------
PYTHON_MIN := 3.10
PYTHON_MAX := 4.0
# PySpark 3.4.x requires Python 3.10 or 3.11. Python 3.12+ parses fine but will
# fail at runtime when PySpark is imported, so we prefer supported versions first.
# Override at the command line: `PYTHON_CMD=python3.11 make setup`
PYTHON_CMD ?= $(shell command -v python3.10 || command -v python3.11 || command -v python3.12 || command -v python3 || command -v python)

VENV := .venv
PYTHON := $(VENV)/bin/python
PIP := $(VENV)/bin/pip
DIST_DIR := dist
BUILD_DIR := build

PACKAGE_NAME := dtt

# ============================================
# Utility Targets
# ============================================

help:
	@echo "DTT Build Commands"
	@echo "------------------"
	@echo "make setup     - Create virtual environment and install build tools"
	@echo "make build     - Build wheel"
	@echo "make install   - Install built wheel into venv"
	@echo "make rebuild   - Clean + setup + rebuild wheel"
	@echo "make clean     - Remove build artifacts (preserves venv)"
	@echo "make clean-all - Remove build artifacts AND virtual environment"
	@echo "make reset     - Full reset (clean-all + recreate environment)"
	@echo ""
	@echo "Lint Commands (Optional)"
	@echo "------------------------"
	@echo "make lint          - Run pre-commit checks on all files"
	@echo "make lint-install  - Enable pre-commit hooks on git commit"

# ============================================
# Python Version Check
# ============================================
check-python:
	@if [ -z "$(PYTHON_CMD)" ]; then \
		echo "Error: Python not found. Please install Python >= $(PYTHON_MIN), < $(PYTHON_MAX)."; \
		exit 1; \
	fi
	@$(PYTHON_CMD) -c "import sys; \
	lo = tuple(map(int, '$(PYTHON_MIN)'.split('.'))); \
	hi = tuple(map(int, '$(PYTHON_MAX)'.split('.'))); \
	cur = sys.version_info[:2]; \
	sys.exit(0) if lo <= cur < hi else \
	sys.exit('Error: Python >= $(PYTHON_MIN), < $(PYTHON_MAX) required. Found: ' + sys.version.split()[0])"
	@$(PYTHON_CMD) -c "import sys; \
	cur = sys.version_info[:2]; \
	print('Warning: Python ' + '.'.join(map(str, cur)) + ' detected. PySpark 3.4.x only supports Python 3.10 or 3.11; runtime imports may fail. Override with PYTHON_CMD=python3.10 make setup.') if cur >= (3, 12) else None"
	@echo "Using Python: $$($(PYTHON_CMD) --version)"

# ============================================
# Virtual Environment
# ============================================
setup: check-python
	@if [ -d "$(VENV)" ]; then \
		VENV_VER=$$($(PYTHON) -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null); \
		MIN_VER="$(PYTHON_MIN)"; \
		if [ "$$VENV_VER" != "$$MIN_VER" ] && ! $(PYTHON) -c "import sys; \
			lo = tuple(map(int, '$(PYTHON_MIN)'.split('.'))); \
			hi = tuple(map(int, '$(PYTHON_MAX)'.split('.'))); \
			cur = sys.version_info[:2]; \
			sys.exit(0) if lo <= cur < hi else sys.exit(1)" 2>/dev/null; then \
			echo "Existing venv has Python $$VENV_VER (requires >= $(PYTHON_MIN), < $(PYTHON_MAX)). Recreating..."; \
			rm -rf $(VENV); \
		fi; \
	fi
	@if [ ! -d "$(VENV)" ]; then \
		echo "Creating virtual environment..."; \
		$(PYTHON_CMD) -m venv $(VENV); \
	fi
	@echo "Upgrading build tools..."
	@$(PIP) install --upgrade pip setuptools wheel build
	@echo "Environment ready."
	@echo "Activate with: source $(VENV)/bin/activate"

# ============================================
# Build
# ============================================
build:
	@if [ ! -x "$(PYTHON)" ]; then \
		echo "Error: Virtual environment not found or corrupt. Run 'make setup' first."; \
		exit 1; \
	fi
	@echo "Cleaning previous build artifacts..."
	@rm -rf $(BUILD_DIR) $(DIST_DIR) *.egg-info src/*.egg-info
	@echo "Building wheel..."
	@$(PYTHON) -m build --wheel --outdir $(DIST_DIR)
	@echo "Build complete."

rebuild:
	@$(MAKE) clean
	@$(MAKE) setup
	@$(MAKE) build

# ============================================
# Install
# ============================================
install:
	@if [ ! -x "$(PIP)" ]; then \
		echo "Error: Virtual environment not found or corrupt. Run 'make setup' first."; \
		exit 1; \
	fi
	@WHL_COUNT=$$(ls -1 $(DIST_DIR)/*.whl 2>/dev/null | wc -l); \
	if [ "$$WHL_COUNT" -eq 0 ]; then \
		echo "Error: No wheel found in $(DIST_DIR)/. Run 'make build' first."; \
		exit 1; \
	elif [ "$$WHL_COUNT" -gt 1 ]; then \
		echo "Error: Multiple wheels found in $(DIST_DIR)/. Run 'make rebuild' for a clean build."; \
		exit 1; \
	fi
	@$(PIP) install --force-reinstall $(DIST_DIR)/*.whl
	@echo "Wheel installed."

# ============================================
# Clean
# ============================================
clean:
	@echo "Cleaning build artifacts..."
	@rm -rf $(BUILD_DIR) $(DIST_DIR) *.egg-info src/*.egg-info
	@find . -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
	@echo "Build artifacts cleaned. Virtual environment preserved."

clean-all:
	@echo "Cleaning build artifacts and virtual environment..."
	@rm -rf $(BUILD_DIR) $(DIST_DIR) $(VENV) *.egg-info src/*.egg-info
	@find . -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true

reset:
	@$(MAKE) clean-all
	@$(MAKE) setup
	@echo "Environment reset complete."

# ============================================
# Lint (Optional — Pre-commit)
# ============================================
PRE_COMMIT_CONFIG ?= .pre-commit-config.yaml

lint:
	@if [ ! -x "$(VENV)/bin/pre-commit" ]; then \
		echo "Error: pre-commit not installed. Run 'make setup' and then 'pip install -r requirements/pre-commit-requirements.txt'."; \
		exit 1; \
	fi
	@echo "Running pre-commit checks..."
	@$(VENV)/bin/pre-commit run --config $(PRE_COMMIT_CONFIG) --all-files

lint-install:
	@if [ ! -x "$(VENV)/bin/pre-commit" ]; then \
		echo "Error: pre-commit not installed. Run 'make setup' and then 'pip install -r requirements/pre-commit-requirements.txt'."; \
		exit 1; \
	fi
	@$(VENV)/bin/pre-commit install
	@echo "Pre-commit hooks installed. Checks will run automatically on git commit."
