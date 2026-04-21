"""
main.py — Run the Tavily research feeder.

Usage:
    python main.py
"""

import sys
import os

# Make sure scripts/ is importable when running from project root
sys.path.insert(0, os.path.dirname(__file__))

from scripts.runner import run

if __name__ == "__main__":
    run()