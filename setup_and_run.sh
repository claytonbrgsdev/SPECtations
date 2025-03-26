#!/bin/bash
# Setup and Run Script for Spectograma
# This script creates a virtual environment, installs dependencies, and runs the application

# Text colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Script directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
VENV_DIR="$SCRIPT_DIR/.venv"

# Function to check if a command exists
command_exists() {
    command -v "$1" &> /dev/null
}

# Check if Python 3 is installed
echo -e "${BLUE}Checking for Python 3...${NC}"
if ! command_exists python3; then
    echo -e "${RED}Python 3 is not installed. Please install Python 3 and try again.${NC}"
    echo -e "${YELLOW}You can install it with Homebrew using: brew install python${NC}"
    exit 1
fi

# Get Python version
PYTHON_VERSION=$(python3 --version)
echo -e "${GREEN}Found $PYTHON_VERSION${NC}"

# Remove any existing virtual environment and create a fresh one
if [ -d "$VENV_DIR" ]; then
    echo -e "${BLUE}Removing existing virtual environment...${NC}"
    rm -rf "$VENV_DIR"
fi

echo -e "${BLUE}Creating fresh virtual environment in $VENV_DIR...${NC}"
python3 -m venv "$VENV_DIR"
if [ $? -ne 0 ]; then
    echo -e "${RED}Failed to create virtual environment. Please check your Python installation.${NC}"
    exit 1
fi
echo -e "${GREEN}Virtual environment created successfully!${NC}"

# Activate virtual environment
echo -e "${BLUE}Activating virtual environment...${NC}"
source "$VENV_DIR/bin/activate"
if [ $? -ne 0 ]; then
    echo -e "${RED}Failed to activate virtual environment.${NC}"
    exit 1
fi
echo -e "${GREEN}Virtual environment activated!${NC}"

# Install dependencies
echo -e "${BLUE}Installing dependencies...${NC}"
"$VENV_DIR/bin/pip" install --upgrade pip
"$VENV_DIR/bin/pip" install -r "$SCRIPT_DIR/requirements.txt"
if [ $? -ne 0 ]; then
    echo -e "${RED}Failed to install dependencies.${NC}"
    exit 1
fi
echo -e "${GREEN}Dependencies installed successfully!${NC}"

# Check if BlackHole is installed
echo -e "${BLUE}Checking for BlackHole audio driver...${NC}"
if ! command_exists brew; then
    echo -e "${YELLOW}Homebrew is not installed. We can't automatically check for BlackHole.${NC}"
    echo -e "${YELLOW}If you haven't installed BlackHole yet, please install it with:${NC}"
    echo -e "${YELLOW}brew install blackhole-2ch${NC}"
else
    if brew list blackhole-2ch &>/dev/null; then
        echo -e "${GREEN}BlackHole is installed!${NC}"
    else
        echo -e "${YELLOW}BlackHole is not installed. You may need it to capture system audio.${NC}"
        echo -e "${YELLOW}Would you like to install BlackHole now? (y/n)${NC}"
        read -r install_blackhole
        if [[ $install_blackhole =~ ^[Yy]$ ]]; then
            echo -e "${BLUE}Installing BlackHole...${NC}"
            brew install blackhole-2ch
            if [ $? -ne 0 ]; then
                echo -e "${RED}Failed to install BlackHole. You may need to install it manually.${NC}"
            else
                echo -e "${GREEN}BlackHole installed successfully!${NC}"
                echo -e "${YELLOW}Please configure your audio settings as described in the README.md file.${NC}"
            fi
        else
            echo -e "${YELLOW}Skipping BlackHole installation. You can install it later with:${NC}"
            echo -e "${YELLOW}brew install blackhole-2ch${NC}"
            echo -e "${YELLOW}Note: BlackHole is required for system audio capture.${NC}"
        fi
    fi
fi

# Run the application
echo -e "${BLUE}Starting Spectograma...${NC}"
echo -e "${YELLOW}Note: To properly visualize system audio, make sure BlackHole is configured as described in README.md${NC}"
python "$SCRIPT_DIR/spectograma.py"

# Deactivate virtual environment when the application exits
deactivate
