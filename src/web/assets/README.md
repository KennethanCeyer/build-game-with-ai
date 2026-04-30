# Character Assets

The primary runtime now uses real local character assets:

- Player: `vendor/threejs/Soldier.glb`, animated with idle/walk/run clips.
- NPC1: `vendor/threejs/Xbot.glb`, animated with idle/walk/run clips.
- NPC2: `vendor/threejs/RobotExpressive/RobotExpressive.glb`, animated with idle/walk/run clips.

The NPCs are separate GLB character models with their own meshes and animations. They are
not recolored copies of the player model. The procedural humanoid remains only as a
loader failure fallback.

License details are tracked in `THIRD_PARTY.md`.
