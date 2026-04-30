# Prompt Ideas

Use these after `run_game.py` is already running.

## Live room flow

Inspect the room:

```text
Inspect the running room. Explain the objective, the safe moves, and whether the exit is still locked.
```

Ask for a route:

```text
Suggest the next four safe moves and explain why they are safe.
```

Preview the route:

```text
Preview that plan in the running room and tell me what changed on the board.
```

Apply the route:

```text
Apply the safest moves now and tell me what the next decision is.
```

Switch rooms:

```text
Load the crossfire_gallery room, inspect it, and suggest the next safe route.
```

## Multimodal prompt

```text
Capture the current board and analyze it visually. Tell me what the screenshot confirms about the player position, relics, danger lanes, and highlighted path.
```

## Planning and production prompts

Vertical slice planning:

```text
Plan an 8-week vertical slice for a top-down roguelike called Nightshift Echo.
The fantasy is a forbidden archive under a dead city.
The core loop is enter one room, read watcher lanes, claim the relic, escape.
Assume a team of 2.
```

Enemy roster design:

```text
Design a 4-enemy roster for a catacomb order faction with a mixed combat focus.
Keep the output readable for a small indie team.
```

Playtest triage:

```text
Triage these playtest notes for a build that ships in 21 days:
- The second room spike feels unfair.
- The retry flow sometimes freezes.
- The objective text is too small.
```

Feature backlog:

```text
Draft a backlog for a feature called relic swap.
The design goal is to trade position for safer routing in static rooms.
Assume a 10-day sprint.
```

Launch checklist:

```text
Build a launch checklist for PC and Steam Deck.
Assume there is a demo and the game ships with 3 supported languages.
```
