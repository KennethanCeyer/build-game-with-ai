from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from agentic_game_demo.game.runtime_api import main


if __name__ == "__main__":
    main()
