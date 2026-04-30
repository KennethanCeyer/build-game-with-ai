from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_runtime_npc_models_are_animated_distinct_local_assets() -> None:
    main_js = (ROOT / "web/main.js").read_text(encoding="utf-8")

    npc_paths = [
        "vendor/threejs/Xbot.glb",
        "vendor/threejs/RobotExpressive/RobotExpressive.glb",
    ]
    for path in npc_paths:
        assert f"/static/assets/{path}" in main_js
        assert (ROOT / "web/assets" / path).exists()

    assert 'aliasAction(actions, "walking", "walk")' in main_js
    assert 'aliasAction(actions, "running", "run")' in main_js
    assert "Superhero_Female_FullBody.gltf" not in main_js
    assert "Superhero_Male_FullBody.gltf" not in main_js


def test_third_party_docs_track_npc_model_licenses() -> None:
    third_party = (ROOT / "web/assets/THIRD_PARTY.md").read_text(encoding="utf-8")
    assets_readme = (ROOT / "web/assets/README.md").read_text(encoding="utf-8")

    assert "vendor/threejs/Xbot.glb" in third_party
    assert "vendor/threejs/RobotExpressive/RobotExpressive.glb" in third_party
    assert "MIT license" in third_party
    assert "CC0" in third_party
    assert "NPC1: `vendor/threejs/Xbot.glb`" in assets_readme
    assert "NPC2: `vendor/threejs/RobotExpressive/RobotExpressive.glb`" in assets_readme
