from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_runtime_npc_models_are_animated_distinct_local_assets() -> None:
    main_js = (ROOT / "src/web/main.js").read_text(encoding="utf-8")

    npc_paths = [
        "vendor/threejs/Xbot.glb",
        "vendor/threejs/RobotExpressive/RobotExpressive.glb",
    ]
    for path in npc_paths:
        assert f"/static/assets/{path}" in main_js
        assert (ROOT / "src/web/assets" / path).exists()

    assert 'aliasAction(actions, "walking", "walk")' in main_js
    assert 'aliasAction(actions, "running", "run")' in main_js
    assert "Superhero_Female_FullBody.gltf" not in main_js
    assert "Superhero_Male_FullBody.gltf" not in main_js


def test_third_party_docs_track_npc_model_licenses() -> None:
    tp_path = ROOT / "src/web/assets/THIRD_PARTY.md"
    third_party = tp_path.read_text(encoding="utf-8")
    readme_path = ROOT / "src/web/assets/README.md"
    assets_readme = readme_path.read_text(encoding="utf-8")

    assert "vendor/threejs/Xbot.glb" in third_party
    assert "vendor/threejs/RobotExpressive/RobotExpressive.glb" in third_party
    assert "MIT license" in third_party
    assert "CC0" in third_party
    assert "NPC1: `vendor/threejs/Xbot.glb`" in assets_readme
    npc2_path = "NPC2: `vendor/threejs/RobotExpressive/RobotExpressive.glb`"
    assert npc2_path in assets_readme
