# Solution

This is the completed build.

Use it when you want to run the finished demo end to end, or when you want to compare a file against [../starter](../starter).

Commands below use `python`. If your shell only provides `python3`, use that instead.

## 1. Install the packages

```bash
cd ./solution
export PATH="$HOME/.local/bin:$PATH"
python -m pip install --user -r requirements.txt
```

## 2. Start the room sandbox

Keep this running:

```bash
python run_game.py
```

The window should show a turn-based top-down puzzle room.

What the board means:

- blue circle: player
- gold diamond: relic
- green door: exit
- red triangle: watcher
- red tint: danger lane
- cyan tint: suggested route preview

Nothing moves until a move is applied. That pause is intentional. It gives the agent time to inspect the board and plan.

## 3. Run the checks

Open a second terminal and run:

```bash
python check_runtime.py
python check_env.py
python check_agent.py
python check_mcp.py
python smoke_mcp.py
```

What each check proves:

- `check_runtime.py`
  The local UDP runtime is alive. Look for `Ping reply: pong`.
- `check_env.py`
  The API key loaded correctly. Look for `Loaded GOOGLE_API_KEY from .env`.
- `check_agent.py`
  The ADK agent object is configured. Look for `Agent name: indie_game_agent` and `Model: gemini-3-flash-preview`.
- `check_mcp.py`
  The MCP server exported the full tool surface. Look for all 15 tool names and all 3 resource names.
- `smoke_mcp.py`
  MCP can load rooms, plan routes, apply moves, and export a snapshot before the LLM is involved.

## 4. Run the agent in the terminal

```bash
adk run ./indie_game_agent
```

When `[user]:` appears, use this sequence.

First prompt:

```text
Inspect the running room. Explain the objective, the safe moves, and whether the exit is still locked.
```

Expected result:

- the answer names the room
- it explains the goal
- it lists safe moves
- the board does not move yet

Second prompt:

```text
Suggest the next four safe moves and explain why they are safe.
```

Expected result:

- the answer gives a concrete move sequence
- it explains how the route avoids watcher lanes
- the board still does not move yet

Third prompt:

```text
Preview that plan in the running room and tell me what changed on the board.
```

Expected result:

- cyan tiles appear on the board
- the player stays in place
- the answer clearly says this was only a preview

Fourth prompt:

```text
Apply the safest moves now and tell me what the next decision is.
```

Expected result:

- the player moves
- the turn count rises
- the answer tells you whether a relic was collected and what to do next

Fifth prompt:

```text
Capture the current board and analyze it visually. Tell me what the screenshot confirms.
```

Expected result:

- a PNG is saved into [./indie_game_agent/runtime_exports](./indie_game_agent/runtime_exports)
- Gemini describes the board from the image
- the visual answer agrees with the structured room state

That is the core demo. The agent is using MCP for room control and Gemini for multimodal verification.

## 5. Try another room

You can switch rooms with the keyboard:

- `1` for `vault_intro`
- `2` for `crossfire_gallery`
- `3` for `switchback_archive`

Or ask the agent:

```text
Load the crossfire_gallery room, inspect it, and suggest the next safe route.
```

## 6. Use the same agent for indie-game production work

The room is the live runtime demo. The same agent also has planning tools.

Model split used in this folder:

- `gemini-3-flash-preview` for the main ADK agent
- `gemini-3.1-flash-lite-preview` for fast board snapshot analysis

Examples:

```text
Plan an 8-week vertical slice for a top-down roguelike called Nightshift Echo.
The fantasy is a forbidden archive under a dead city.
The core loop is enter one room, read watcher lanes, claim the relic, escape.
Assume a team of 2.
```

```text
Design a 4-enemy roster for a catacomb order faction with a mixed combat focus.
Keep the output readable for a small indie team.
```

```text
Triage these playtest notes for a build that ships in 21 days:
- The second room spike feels unfair.
- The retry flow sometimes freezes.
- The objective text is too small.
```

```text
Draft a backlog for a feature called relic swap.
The design goal is to trade position for safer routing in static rooms.
Assume a 10-day sprint.
```

More prompt examples are in [./prompts.md](./prompts.md).

## 7. ADK commands used in this repository

```bash
adk run ./indie_game_agent
adk web --port 8000 .
adk api_server --auto_create_session --port 8001 .
```

Use them like this:

- `adk run`
  Fastest way to demo the agent in a terminal.
- `adk web`
  Browser UI for the same app.
- `adk api_server`
  HTTP surface for app discovery and structured event inspection.

App discovery check:

```bash
curl -s http://127.0.0.1:8000/list-apps
curl -s http://127.0.0.1:8001/list-apps
```

Expected output:

```json
["indie_game_agent"]
```

If you call `/run` on the API server, a healthy response includes:

- `functionCall`
- `functionResponse`
- final `text`

That means the model chose a tool, the tool returned data, and the model summarized that data into a reply.

## 8. Troubleshooting

- If `adk` is not found, run `export PATH="$HOME/.local/bin:$PATH"` again.
- If `python` is not available, use `python3`.
- If the room window cannot open, run `python run_game.py --headless`.
- If the agent answers but the room never changes, make sure `run_game.py` is still running in another terminal.
