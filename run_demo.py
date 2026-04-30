from __future__ import annotations

import sys
from pathlib import Path

# Check active mode (handson vs solution)
root = Path(__file__).resolve().parent
active_mode_file = root / ".active_mode"
mode = "handson"
if active_mode_file.exists():
    mode = active_mode_file.read_text().strip()

print(f"--- Starting Agentic Game Demo in [{mode}] mode ---")
sys.path.insert(0, str(root / "src"))
sys.path.insert(0, str(root / mode))

from agentic_game_engine.game.runtime_api import main


if __name__ == "__main__":
    main()
