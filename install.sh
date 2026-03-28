#!/bin/bash
#
# DRP to Premiere Pro Converter - Installer
# Copies the script to DaVinci Resolve's Scripts directory
#

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
APP_NAME="DRP-to-Premiere"

echo "=================================="
echo " DRP to Premiere Pro Converter"
echo " Installer"
echo "=================================="
echo ""

# Detect OS
if [[ "$OSTYPE" == "darwin"* ]]; then
    RESOLVE_SCRIPTS_DIR="$HOME/Library/Application Support/Blackmagic Design/DaVinci Resolve/Support/Fusion/Scripts/Utility"
    RESOLVE_SCRIPTS_ALT="/Library/Application Support/Blackmagic Design/DaVinci Resolve/Fusion/Scripts/Utility"
    OS_NAME="macOS"
elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
    RESOLVE_SCRIPTS_DIR="$HOME/.local/share/DaVinciResolve/Fusion/Scripts/Utility"
    OS_NAME="Linux"
elif [[ "$OSTYPE" == "msys" || "$OSTYPE" == "cygwin" || "$OSTYPE" == "win32" ]]; then
    RESOLVE_SCRIPTS_DIR="$APPDATA/Blackmagic Design/DaVinci Resolve/Support/Fusion/Scripts/Utility"
    OS_NAME="Windows"
else
    echo "Unknown OS: $OSTYPE"
    echo "Please manually copy the files to your Resolve Scripts directory."
    exit 1
fi

echo "Detected OS: $OS_NAME"
echo "Install target: $RESOLVE_SCRIPTS_DIR"
echo ""

# Create the scripts directory if it doesn't exist
if [ ! -d "$RESOLVE_SCRIPTS_DIR" ]; then
    echo "Creating Resolve scripts directory..."
    mkdir -p "$RESOLVE_SCRIPTS_DIR"
fi

# Create our app directory
INSTALL_DIR="$RESOLVE_SCRIPTS_DIR/$APP_NAME"
if [ -d "$INSTALL_DIR" ]; then
    echo "Updating existing installation..."
    rm -rf "$INSTALL_DIR"
fi

mkdir -p "$INSTALL_DIR"

# Copy files
echo "Copying files..."
cp "$SCRIPT_DIR/resolve_to_premiere.py" "$INSTALL_DIR/"
cp "$SCRIPT_DIR/timeline_extractor.py" "$INSTALL_DIR/"
cp "$SCRIPT_DIR/lut_exporter.py" "$INSTALL_DIR/"
cp "$SCRIPT_DIR/premiere_xml_builder.py" "$INSTALL_DIR/"
cp "$SCRIPT_DIR/effects_mapper.py" "$INSTALL_DIR/"

# Create __init__.py
touch "$INSTALL_DIR/__init__.py"

# Create the launcher script that Resolve will see
cat > "$RESOLVE_SCRIPTS_DIR/DRP to Premiere.py" << 'LAUNCHER'
#!/usr/bin/env python3
"""DRP to Premiere Pro Converter - Launch from Resolve's Workspace > Scripts menu."""
import sys
import os

# Add our module directory to path
script_dir = os.path.dirname(os.path.abspath(__file__))
module_dir = os.path.join(script_dir, "DRP-to-Premiere")
if module_dir not in sys.path:
    sys.path.insert(0, module_dir)

from resolve_to_premiere import main
main()
LAUNCHER

echo ""
echo "Installation complete!"
echo ""
echo "How to use:"
echo "  1. Open DaVinci Resolve"
echo "  2. Go to Workspace > Scripts"
echo "  3. Click 'DRP to Premiere'"
echo ""
echo "Or run standalone:"
echo "  cd $INSTALL_DIR"
echo "  python3 resolve_to_premiere.py"
echo ""
echo "Files installed to: $INSTALL_DIR"
echo ""
