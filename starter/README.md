# Starter

This folder is the guided build.

The game code is already here. Your job is to finish the agent wiring so the model can talk to the running room through MCP.

Only these files need edits:

1. [./indie_game_agent/settings.py](./indie_game_agent/settings.py)
2. [./indie_game_agent/agent.py](./indie_game_agent/agent.py)
3. [./indie_game_agent/mcp_server.py](./indie_game_agent/mcp_server.py)

Commands below use `python`. If your shell only provides `python3`, use that instead.

## 1. Install the packages

```bash
cd ./starter
export PATH="$HOME/.local/bin:$PATH"
python -m pip install --user -r requirements.txt
```

If [./.env](./.env) does not exist yet, copy [./.env.example](./.env.example) to [./.env](./.env) and add your `GOOGLE_API_KEY`.

## 2. Start the room sandbox

Keep this running in one terminal:

```bash
python run_game.py
```

The first screen should already look like a small puzzle room:

- blue circle: player
- gold diamond: relic
- green door: exit
- red triangle: watcher
- red tint: danger lane

The room is intentionally turn-based. Nothing moves until you press a movement key or the agent sends a move command.

You can also switch rooms manually:

- `1` loads `vault_intro`
- `2` loads `crossfire_gallery`
- `3` loads `switchback_archive`

Run a quick connectivity check in a second terminal:

```bash
python check_runtime.py
```

Look for these lines:

- `Ping reply: pong`
- `Room: ...`
- `Safe moves: ...`

That means the local UDP runtime is alive and ready for MCP tools.

## 3. Finish the settings loader

Open [./indie_game_agent/settings.py](./indie_game_agent/settings.py) and fill in the lines marked `TODO(starter-1)`.

That small block should do three things:

- read `GOOGLE_API_KEY`
- load [./.env](./.env)
- copy the key into the current process environment

Check it:

```bash
python check_env.py
```

The success line is:

- `Loaded GOOGLE_API_KEY from .env`

## 4. Finish the ADK agent

Open [./indie_game_agent/agent.py](./indie_game_agent/agent.py) and fill in `TODO(starter-2)`.

This step connects the agent to the local MCP server. When it is correct, the agent will know:

- which model to use
- which app name to expose through ADK
- how to launch the local MCP server
- when to inspect the room
- when to suggest moves
- when to preview or apply moves
- when to use the visual board analysis tool

Check it:

```bash
python check_agent.py
```

Look for:

- `Agent name: indie_game_agent`
- `Model: gemini-3-flash-preview`

## 5. Finish the MCP server

Open [./indie_game_agent/mcp_server.py](./indie_game_agent/mcp_server.py) and fill in `TODO(starter-3)`.

This step turns ordinary Python functions into the tool surface that the agent can call.

The finished MCP server should expose tools for:

- room inspection
- room loading
- safe-route suggestion
- previewing a route on the board
- applying moves
- snapshot export
- visual snapshot analysis
- planning and production tasks for an indie game

In the completed build, the main agent uses `gemini-3-flash-preview`.
The snapshot-analysis helper uses `gemini-3.1-flash-lite-preview` so the visual step stays fast enough for the workshop flow.

Check it:

```bash
python check_mcp.py
```

The success condition is simple:

- all 15 expected tool names are present
- all 3 expected resource names are present

## 6. Prove that MCP can drive the room

Keep `run_game.py` running and execute:

```bash
python smoke_mcp.py
```

This script does not use the model yet. It talks to MCP directly.

By the time it finishes, it should have:

- generated design output
- loaded a room preset
- asked for a safe route
- previewed that route on the board
- applied a few moves
- exported a PNG snapshot

The room window should visibly change while the script runs. That proves the tool layer is working before the LLM is involved.

## 7. Run the agent in the terminal

Start the agent:

```bash
adk run ./indie_game_agent
```

Ignore the warning lines that ADK may print before the prompt. The important line is:

```text
Running agent indie_game_agent, type exit to exit.
```

When `[user]:` appears, paste this first:

```text
Inspect the running room. Explain the objective, the safe moves, and whether the exit is still locked.
```

What should happen:

- the answer names the room and objective
- it tells you whether relics still remain
- it lists the currently safe directions
- the board itself does not move yet

Now ask for a plan:

```text
Suggest the next four safe moves and explain why they are safe.
```

What should happen:

- the answer gives a short move sequence such as `up, up, right, right`
- it explains that the moves avoid watcher lanes and blocked tiles
- the board still stays in place because this was only a suggestion

Now preview that plan on the board:

```text
Preview that plan in the running room and tell me what changed on the board.
```

What should happen:

- cyan tiles appear on the board
- the player stays on the current tile
- the answer explains that this is only a preview, not a committed move

Now commit the move sequence:

```text
Apply the safest moves now and tell me what the next decision is.
```

What should happen:

- the player moves
- the turn count increases
- the answer explains whether a relic was collected or what the next target is

Now try the multimodal step:

```text
Capture the current board and analyze it visually. Tell me what the screenshot confirms.
```

What should happen:

- the tool saves a PNG into [./indie_game_agent/runtime_exports](./indie_game_agent/runtime_exports)
- Gemini describes the board from the image
- the answer should agree with the tool-based room state

That is the main moment of the hands-on: the same agent can use MCP for structured state and Gemini for visual confirmation.

## 8. Try a different room

You can press `2` or `3` in the game window, or ask the agent:

```text
Load the crossfire_gallery room, inspect it, and suggest the next safe route.
```

That should switch the room and produce a fresh explanation based on the new board layout.

## 9. Use the same agent for indie-game planning

The room control flow is only half of the demo. The same agent also has planning tools.

Try any prompt from [./prompts.md](./prompts.md), or start with these:

```text
Plan an 8-week vertical slice for a top-down roguelike called Nightshift Echo.
The fantasy is a forbidden archive under a dead city.
The core loop is enter one room, read watcher lanes, claim the relic, escape.
Assume a team of 2.
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

This is the broader point of the workshop: the agent is not only a board controller. It can also support day-to-day indie production work.

## 10. ADK commands worth knowing

Once the terminal flow works, these commands show the same agent through different surfaces:

```bash
adk run ./indie_game_agent
adk web --port 8000 .
adk api_server --auto_create_session --port 8001 .
```

What each one is for:

- `adk run`
  A terminal chat. This is the fastest way to prove the agent can call MCP tools.
- `adk web`
  A browser chat. Use it when you want a UI instead of a terminal.
- `adk api_server`
  A raw HTTP surface. Use it when you want to test app discovery or inspect structured events.

For `adk web` and `adk api_server`, this check should return the same app name:

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

That means the model chose a tool, the tool returned data, and the model turned that data into a user-facing answer.

## 11. If something is off

- If `python` is not available in your shell, replace it with `python3`.
- If `adk` is not found, run `export PATH="$HOME/.local/bin:$PATH"` again.
- If the room window cannot open, use `python run_game.py --headless`.
- If `check_runtime.py` fails, make sure `run_game.py` is still running in another terminal.
- If the model answers without touching the room, re-check the MCP TODOs and re-run `python check_mcp.py`.
