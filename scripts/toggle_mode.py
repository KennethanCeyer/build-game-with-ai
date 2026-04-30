#!/usr/bin/env python3
import sys
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]
ACTIVE_MARKER = ROOT / ".active_mode"

def set_mode(mode: str):
    if mode not in ["handson", "solution"]:
        print(f"Error: Invalid mode '{mode}'. Choose 'handson' or 'solution'.")
        sys.exit(1)
    
    with open(ACTIVE_MARKER, "w") as f:
        f.write(mode)
    
    print(f"Mode switched to: {mode}")
    print("Please restart the demo (run_demo.py) to apply changes.")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        current = "handson"
        if ACTIVE_MARKER.exists():
            current = ACTIVE_MARKER.read_text().strip()
        print(f"Current mode: {current}")
        print("Usage: python scripts/toggle_mode.py [handson|solution]")
    else:
        set_mode(sys.argv[1])
