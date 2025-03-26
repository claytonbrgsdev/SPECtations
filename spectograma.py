#!/usr/bin/env python3
"""
Spectograma - Real-time Audio Visualization for macOS
Entry point script to launch the application.
"""
import os
import sys

# Add src directory to Python path
src_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'src')
sys.path.insert(0, src_dir)

# Import and run main function
from main import main

if __name__ == "__main__":
    sys.exit(main())
