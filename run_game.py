from __future__ import annotations

import sys
from pathlib import Path

root = Path(__file__).resolve().parent
active_mode_file = root / ".active_mode"
mode = "handson"

if len(sys.argv) > 1 and sys.argv[1] in ["handson", "solution"]:
    mode = sys.argv[1]
elif active_mode_file.exists():
    mode = active_mode_file.read_text().strip()

print(f"--- Starting Agentic Game Demo in [{mode}] mode ---")
if mode == "solution":
    print("Tip: Use 'python run_game.py handson' to return to lab mode.")

sys.path.insert(0, str(root / "src"))
sys.path.insert(0, str(root / mode))

from engine.game.runtime_api import main  # noqa: E402


if __name__ == "__main__":
    main()
