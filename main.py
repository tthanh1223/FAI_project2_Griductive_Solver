"""Entry point: open the Griductive GUI.

Usage:
    python main.py                      # open GUI, then use the Load button
    python main.py puzzles/p3_01.json   # open GUI with this puzzle
"""
import sys

from gui.app import run


if __name__ == "__main__":
    run(sys.argv[1] if len(sys.argv) > 1 else None)
