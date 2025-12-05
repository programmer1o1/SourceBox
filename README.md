# SourceBox

An application with Source Engine integration through VScript and Garry's Mod Lua scripting.

![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20Linux-blue)
![Python](https://img.shields.io/badge/python-3.7+-green)
![License](https://img.shields.io/badge/license-MIT-orange)

> [!NOTE]
> SRCBOX cube model is a custom model! You need to install it into your game custom folder otherwise it won't spawn when you press the cube in SourceBox window.
> It should be in `YOUR_GAME\custom\srcbox\models\props\srcbox\srcbox.mdl`.
> 
> You can download it [here!](https://github.com/Kiverix/srcbox.mdl/releases)

## Features
- **Python Bridge**: Spawn props directly from SourceBox into your game
- **Multi-game Support**: Works across most Source Engine games

### VScript Features (TF2 Branch Source Engine Games)
- **Picker (Aimbot)**: Advanced targeting system with priority targeting (Players → Props)
- **AWP Quit Trigger**: Shoot spawned SRCBOX props with AWP to quit the game (Only for CS:S)
- **Auto-Spawner**: Automatically spawns cube at random locations on map load
- **Auto-load Scripts**: Scripts automatically load on every map via `mapspawn.nut`

### Lua Features (Garry's Mod 9-12)
- **Automatic Addon Installation**: Creates addon structure in `addons/sourcebox/lua/`
- **Picker (Aimbot)**: Silent targeting system (NPCs → Players → Props)
- **Auto-Spawner**: Spawns cube on map load at random locations
- **Console Commands**: `picker_toggle`, `picker_next`, `sourcebox_spawn`

> [!NOTE]
> Picker aimbot script is little bit buggy on GMod 9.

## Supported Games

### VScript Support (Full Features)
| Game | VScript | Picker | AWP Quit | Auto-Spawn | Notes |
|------|---------|--------|----------|------------|-------|
| Team Fortress 2 | ✅ | ✅ | ✅ | ✅ | AWP Quit only for CS:S |
| Counter-Strike: Source | ✅ | ✅ | ✅ | ✅ | 
| Day of Defeat: Source | ✅ | ✅ | ✅ | ✅ | AWP Quit only for CS:S |
| Half-Life 2: Deathmatch | ✅ | ✅ | ✅ | ✅ | AWP Quit only for CS:S |
| Half-Life 1 Source: Deathmatch | ✅ | ✅ | ✅ | ✅ | AWP Quit only for CS:S |

### Garry's Mod Support (Lua Bridge)
| Version | Lua Bridge | Picker | Auto-Spawn | Notes |
|---------|------------|--------|------------|-------|
| GMod 9 | ✅ | ✅ | ✅ | Picker little bit buggy |
| GMod 10 | ✅ | ✅ | ✅ | Sourcemod |
| GMod 11 | ✅ | ✅ | ✅ | Sourcemod |
| GMod 12 | ✅ | ✅ | ✅ | Sourcemod |
| GMod 13 | 🚧 | 🚧 | 🚧 | Coming soon |

### Console Injection (Legacy Support - Windows Only)
- Works with any Source mod without VScript support or Lua support
- Only cube spawning supported
- Brief window freeze during spawn
- **Linux not supported**

## Installation

### Option 1: Pre-built Executable (Recommended)
1. Download the latest release from [Releases](https://github.com/programmer1o1/sourcebox/releases)
2. Extract the ZIP file
3. **Important**: Launch your game **before** running SourceBox
4. Run `SourceBox.exe` (Windows) or `./SourceBox` (Linux)

### Option 2: Manual Installation

#### Prerequisites
- Python 3.7 or higher
- pip package manager
- A supported Source Engine game or Garry's Mod installed via Steam

#### Setup

1. Clone the repository:
```bash
git clone https://github.com/programmer1o1/sourcebox.git
cd sourcebox
```

2. Create a virtual environment (Linux):
```bash
python -m venv myenv
source myenv/bin/activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. **Important**: Launch your game **before** running SourceBox

5. Run the application:
```bash
python Sourcebox.py
```

## Usage

### Controls

- **Left Click**: Interact with objects
  - **Cube**: Spawn SRCBOX cube in-game
  - **Sphere**: Toggle error scene
  - **Cone**: Enter Voidside tracker mode
- **ESC**: Exit application

### Source Engine Integration (VScript)

#### Automatic Setup
1. Launch a supported Source game (TF2, CS:S, DOD:S, HL2:DM, HL1S:DM)
2. Launch SourceBox
3. Scripts automatically install to:
   - `game/scripts/vscripts/python_listener.nut`
   - `game/scripts/vscripts/picker.nut`
   - `game/scripts/vscripts/auto_spawner.nut`
   - `game/scripts/vscripts/mapspawn.nut`

#### In-Game Usage

**Spawning Props:**
- Click the cube in SourceBox
- Prop spawns at your crosshair
- Works in single-player or local listen servers

**Picker Commands:**
```javascript
script PickerToggle()      // toggle aimbot on/off
script PickerNext()        // manually cycle to next target
```

You can also set binds like these
```
bind mouse4 "script PickerToggle()"
bind mouse5 "script PickerNext()"
bind kp_plus "script PickerToggle()"
```

**AWP Quit Feature:**
- Shoot any spawned SRCBOX cube with AWP
- Game quits immediately
- Only works in CS:S

**Manual Script Loading** (if auto-load fails):
```
sv_cheats 1
script_execute python_listener
```

### Garry's Mod Integration (Lua)

#### Automatic Setup
1. Launch GMod 9 (gmod9), 10 (garrysmod10classic), 11 (garrysmod), or 12 (garrysmod12) (sourcemod version)
2. Launch SourceBox
3. Addon automatically installs to:
   - `garrysmod/addons/sourcebox/lua/autorun/sourcebox_init.lua`
   - `garrysmod/addons/sourcebox/lua/autorun/sourcebox/sv_*.lua`
4. Restart GMod game to load addon on first install (Optional for GMod 9)

#### In-Game Usage

**Console Commands:**
```
picker_toggle              // toggle aimbot silently
picker_next               // cycle to next target
sourcebox_spawn <model> [distance]   // spawn any model
```

**Examples:**
```
picker_toggle
sourcebox_spawn props_junk/PopCan01a.mdl 300
sourcebox_spawn props/srcbox/srcbox.mdl
```

**Spawning Props:**
- Click the cube in SourceBox
- Prop spawns at crosshair
- Props are fully visible and interactive

### Legacy Console Injection

**Requirements:**
- Windows only
- Running Source mod detected automatically

**Spawning:**
- Click cube in SourceBox
- Console briefly opens, executes commands, closes
- Window may freeze for ~200ms
- Only SRCBOX cube supported

## Troubleshooting

### Common Issues

**"No game configured" error:**
- Make sure game is running **before** launching SourceBox
- Check that game is installed via Steam
- Try restarting Steam

**Scripts not loading in Source games:**
- Type `sv_cheats 1` in console
- Manually run: `script_execute python_listener`

**GMod addon not working:**
- Make sure you're using GMod 9, 10, 11, or 12 (sourcemod)
- Restart GMod after first install
- Check `garrysmod/addons/sourcebox/` exists
- Use `lua_run include("autorun/sourcebox_init.lua")` to manually load

**AWP quit not working:**
- Only works in CS:S
- Must shoot SRCBOX cube specifically
- Requires AWP weapon

## Development

### Building from Source

```bash
# install development dependencies
pip install -r requirements.txt

# test bridges standalone
python source_bridge.py   # test source engine bridge
python gmod_bridge.py    # test gmod bridge

# run in verbose mode
python Sourcebox.py
```

### Compiling to Executable

**Windows:**
```bash
pip install pyinstaller
pyinstaller --onefile --windowed --name SourceBox ^
  --icon=assets/images/sourcebox.png ^
  --add-data "assets;assets" ^
  --exclude-module pkg_resources ^
  --exclude-module setuptools ^
  --noupx --clean Sourcebox.py
```

**Linux:**
```bash
pip install pyinstaller
pyinstaller --onefile --windowed --name SourceBox \
  --icon=assets/images/sourcebox.png \
  --add-data "assets:assets" \
  --exclude-module pkg_resources \
  --exclude-module setuptools \
  --hidden-import=OpenGL.platform.glx \
  --hidden-import=OpenGL.arrays.vbo \
  --collect-all OpenGL \
  --noupx --clean Sourcebox.py
```

Output: `dist/SourceBox.exe` (Windows) or `dist/SourceBox` (Linux)

### Adding Custom Models

**For Source Engine:**
1. Place models in `game/custom/yourmod/models/props/`
2. Spawn via Python:
```python
bridge.spawn("props/yourmod/model.mdl", 200)
```

**For Garry's Mod:**
```python
gmod_bridge.spawn_model("props/yourmod/model.mdl", 300)
```

Or in-game console:
```
sourcebox_spawn props/yourmod/model.mdl 300
```

## Technical Details

### VScript Communication
- **Method**: File I/O via `scriptdata/` folder
- **Files**: `python_command.txt`, `python_response.txt`
- **Format**: JSON with session ID and command counter
- **Rate**: Commands checked every 100ms

### Lua Communication (GMod)
- **Method**: File I/O via `data/` folder
- **Files**: `sourcebox_command.txt`, `sourcebox_response.txt`
- **Format**: JSON with session ID and command counter
- **Rate**: Commands checked every 100ms
- **Addon Path**: `addons/sourcebox/lua/autorun/`

### Console Injection (Legacy)
- **Method**: Windows API message sending
- **Process**: Freeze window → Open console → Paste command → Execute → Close console → Unfreeze
- **Limitation**: Windows only, visual freeze, cube only

## License

This project is licensed under the MIT License - see the LICENSE file for details.
