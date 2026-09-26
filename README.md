# pyWare

A Roblox external written entirely in Python.

Do NOT expect every feature to work but do expect it being updated if something breaks, there are a few functions that are stragiht bullshit and it was made that way.

It’s an overlay-based tool - no DLL injection, no Roblox process injection, and no FPS unlocker. It uses `NtReadVirtualMemory` / `NtWriteVirtualMemory` through `ctypes` to read and write memory.

The overlay includes ESP, an in-game mouse-driven menu, aimbot/triggerbot, movement and world mods, teleport tools, diagnostics, and a console log.

## Setup

Run `setup.bat`. It will install Python 3.12 if you don't already have it, then install the required packages:

* PyQt5
* psutil
* requests

After that, start it with:

```bat
py main.py
```

Run it **as administrator**.

Roblox should already be running and you should be inside a game before starting pyWare.

If Roblox updates and the offsets need to be rebuilt:

```bat
py tools/dump_to_snapshot.py path\to\offsets.cs
```

## Controls

The menu is completely mouse-driven. The only keyboard shortcut is `INSERT`.

| Input                           | What it does                 |
| ------------------------------- | ---------------------------- |
| Drag title bar                  | Move a category window       |
| Right-click title               | Collapse / expand the window |
| Left-click                      | Toggle or activate an option |
| Drag slider                     | Change a value               |
| Click left/right side of slider | Step the value               |
| Mouse wheel over slider         | Nudge the value              |
| Player row — left click         | Teleport to player           |
| Player row — right click        | Bring player                 |
| `INSERT`                        | Show / hide the menu         |
| Hold `RMB`                      | Aimbot, if enabled           |

You can move each category independently. The categories are:

**ESP · AIM · MODS · WORLD · MISC · TP · SYS**

Closing the menu with `X` or `INSERT` only hides it. Use **SYS → UNLOAD** when you actually want to shut pyWare down and restore its changes.

## Features

### ESP

* Flat, corner and 3D boxes
* R6/R15 skeleton ESP
* Player names
* Equipped tool
* Health bars with gradients
* Health numbers
* Distance
* Snaplines
* Head dot
* Custom crosshair
* Team check and team colors
* Maximum render distance
* Distance-based fading
* Label stacking
* Text shadows

Skeleton joints are checked against the player's actual character class instead of blindly assuming every character has the same parts.

### Aim

Hold **RMB** to aim at a target.

* Head or chest targeting
* Crosshair or lowest-HP target selection
* Smoothing
* Per-tick movement limit
* Sub-pixel remainder handling
* Velocity prediction
* FOV ring
* Target line
* Sticky target until RMB is released

There's also a head hitbox option. The original hitbox is saved and restored when the feature is disabled.

### Triggerbot

Automatically fires when a player's head is on the crosshair.

The trigger radius and cooldown can be adjusted from the menu. The default cooldown is 120ms.

### Mods

Movement and character-related options:

* WalkSpeed
* Jump power
* Auto bunny hop
* Fly
* Spinbot
* Invisibility
* Gravity
* Camera FOV

Fly uses **SPACE** to go up and **C** to go down.

There is also a WalkSpeed readback in the menu showing the current value and the value pyWare is trying to set:

```text
walkspeed now: X (want Y)
```

This makes it easy to tell whether the write is actually reaching the game.

One important thing about WalkSpeed: it doesn't replicate server-side in the way you might expect. Once pyWare writes the value, disabling the option simply stops further writes — it doesn't automatically put the old value back. The game's own scripts or a respawn may change it later.

### World

* Fullbright
* No fog
* Clock lock
* Infinite zoom
* Day preset
* Sunset preset
* Night preset

World changes are saved so the original values can be restored when the feature is disabled.

### Teleport

The teleport menu shows the current player roster, including HP and distance.

You can:

* Teleport to a player
* Bring a player
* Bring everyone
* Save your current position
* Load a saved position
* Copy a rejoin script

### Misc

* ESP box color
* Menu accent color
* Violet
* Cyan
* Orange
* Pink
* Copy rejoin script

### Diagnostics

The diagnostics section is mainly there to make offset problems easier to find.

It includes:

* Per-stage resolve checks
* Version comparison
* Live offset refetch
* DataModel / Workspace / Players validation
* JobId display

The HUD also shows whether the current offsets resolved successfully.

**Green = resolved**

**Red = failed**

## Offsets

The included offset snapshot is mainly a fallback. Roblox client offsets change between builds, so pyWare checks the current Roblox version when it starts.

It then fetches the current table from:

`offsets.imtheo.lol/offsets.json`

The compiled snapshot and the live table are both tested. pyWare keeps whichever one passes its validation checks.

The validation isn't just "did we get an address?" — it checks things such as `DataModel`, `Workspace` and `Players` so a bad offset table is less likely to be accepted.

## Unloading

Use:

**SYS → UNLOAD**

This stops the engine, restores the values pyWare changed, removes the overlay and exits cleanly.

The goal is that anything pyWare changed gets put back before the process closes.

## Project structure

```text
main.py
│
├── pyware/
│   ├── memory.py
│   ├── offsets_snapshot.py
│   ├── offsets.py
│   ├── sdk.py
│   ├── engine.py
│   ├── config.py
│   ├── aimbot.py
│   ├── mods.py
│   ├── world.py
│   ├── hitbox.py
│   ├── teleport.py
│   └── overlay.py
│
└── tools/
    └── dump_to_snapshot.py
```

### What each file does

* `memory.py` — Windows memory access, module bases and string handling
* `offsets_snapshot.py` — generated fallback offset table
* `offsets.py` — offset handling and live offset fetching
* `sdk.py` — DataModel resolution, validation and instance helpers
* `engine.py` — entity cache, roster and diagnostics
* `config.py` — settings and JSON config
* `aimbot.py` — aimbot and triggerbot
* `mods.py` — movement and character modifications
* `world.py` — lighting, fog, clock and zoom changes
* `hitbox.py` — head hitbox changes and restoration
* `teleport.py` — teleport, bring, position slots and rejoin script
* `overlay.py` — ESP, menu, HUD and mouse input
* `dump_to_snapshot.py` — generates a new snapshot from an `offsets.cs` dump

## Notes

pyWare is intentionally kept as a pure Python project. There are no DLLs to inject and no separate native component required.

The overlay runs independently of the Roblox UI and all configuration is controlled through the in-game ClickGUI.
