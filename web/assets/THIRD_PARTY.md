# Third-Party Assets

## Player Character Model

- File: `vendor/threejs/Soldier.glb`
- Source: three.js examples repository
- URL: https://github.com/mrdoob/three.js/blob/dev/examples/models/gltf/Soldier.glb
- License used here: three.js repository MIT license
- Purpose: animated player character with `Idle`, `Walk`, and `Run` clips for the live WebGL demo.

## NPC Character Models

- Files:
  - `vendor/threejs/Xbot.glb`
  - `vendor/threejs/RobotExpressive/RobotExpressive.glb`
- Source: three.js examples repository
- URLs:
  - https://github.com/mrdoob/three.js/blob/dev/examples/models/gltf/Xbot.glb
  - https://github.com/mrdoob/three.js/blob/dev/examples/models/gltf/RobotExpressive/RobotExpressive.glb
- Licenses used here:
  - `Xbot.glb`: three.js repository MIT license.
  - `RobotExpressive.glb`: CC0, per the official three.js skinning/morphing example notes.
- Purpose: two visually distinct animated NPCs with neutral idle poses. These are separate GLB assets, not recolored copies of the player model.

## WebGL Runtime

- Files: `vendor/threejs/build/three.module.js`, `vendor/threejs/build/three.core.js`, `vendor/threejs/examples/jsm/loaders/GLTFLoader.js`, `vendor/threejs/examples/jsm/utils/BufferGeometryUtils.js`
- Source: three.js 0.181.2 distribution
- URL: https://github.com/mrdoob/three.js
- License: MIT, copied to `vendor/threejs/LICENSE`
- Purpose: local, deterministic Three.js runtime for workshop use without CDN startup variance.

## CC0 Human Character Source Pack

- Files: `vendor/quaternius/base-characters/*`
- Source: Quaternius Universal Base Characters
- URL: https://quaternius.itch.io/universal-base-characters
- License: Creative Commons Zero v1.0 Universal
- Purpose: license-safe human base character reference assets for workshop replacement or retargeting. These are retained as reference assets, but the runtime NPCs now use the animated three.js GLB files above.

Quaternius states the pack includes six game-ready character models, humanoid rig compatibility,
and free use in personal, educational, and commercial projects under CC0.

## CC0 Animation Reference Pack

- Source checked: Quaternius Universal Animation Library
- URL: https://quaternius.itch.io/universal-animation-library
- License: Creative Commons Zero v1.0 Universal
- Purpose: walk/run/locomotion reference pack for the next retargeting step.

## Sound Effects

- Files: `audio/ui_click.ogg`, `audio/ui_confirm.ogg`, `audio/ui_open.ogg`
- Source: Kenney Interface Sounds
- URL: https://kenney.nl/assets/interface-sounds
- License: Creative Commons CC0
- Purpose: console and HUD feedback sounds.

- Files: `audio/footstep00.ogg` through `audio/footstep03.ogg`, `audio/jump_whoosh.ogg`
- Source: Kenney RPG Audio
- URL: https://kenney.nl/assets/rpg-audio
- License: Creative Commons CC0
- Purpose: movement and jump feedback.

- Files: `audio/jump_land.wav`, `audio/ui_move.wav`, `audio/powerup.wav`, legacy WAV fallbacks
- Source: OpenGameArt CC0 sound effects
- URLs:
  - https://lpc.opengameart.org/content/jump-landing-sound
  - https://opengameart.org/content/various-sound-effects-0
- License: Creative Commons CC0
- Purpose: landing and alternate UI/gameplay feedback.
