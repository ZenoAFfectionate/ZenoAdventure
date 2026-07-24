#!/usr/bin/env python3
"""
main.py - Entry point for Kenney's Adventure platformer game.

Run:  python3 main.py
"""

import os
import sys

# Ensure the src package is importable regardless of CWD
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.game import Game


def main():
    game = Game()
    game.run()


if __name__ == "__main__":
    main()
