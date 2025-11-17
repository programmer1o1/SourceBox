# SourceBox

An application with Source Engine integration through VScript.

![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20Linux-blue)
![Python](https://img.shields.io/badge/python-3.7+-green)
![License](https://img.shields.io/badge/license-MIT-orange)

> [!NOTE]
> SRCBOX cube model is a custom model! You need to install it into your game custom folder otherwise it won't spawn when you press the cube in SourceBox window.
> It should be this `YOUR_GAME\custom\srcbox\models\props\srcbox\srcbox.mdl`.
> 
> You can download it ![here!](https://github.com/Kiverix/srcbox.mdl/releases)

## Features
- **Source Engine Bridge**: Spawn the very silly cube directly into Source games 
- **Picker (Aimbot)**: Advanced targeting system with manual selection
- **AWP Quit Trigger**: Shoot spawned props with AWP to quit the game
- **Auto-load Scripts**: Automatically loads on every map

## Supported Games

- Team Fortress 2
- Counter-Strike: Source
- Day of Defeat: Source
- Half-Life 2: Deathmatch
- Half-Life 1 Source: Deathmatch

## Installation

### Option 1: Pre-built Executable (Recommended)
1. Download the latest release from [Releases](https://github.com/programmer1o1/sourcebox/releases)
2. Extract the ZIP file
3. Run `Sourcebox.exe` (Windows) or `./Sourcebox` (Linux)

### Option 2: Manual Installation
#### Prerequisites

- Python 3.7 or higher
- pip package manager
- A supported Source Engine game installed via Steam

#### Setup

1. Clone the repository:
```bash
git clone https://github.com/programmer1o1/sourcebox.git
cd sourcebox
```

2. Create a virtual environment (for Linux users):
```bash
python -m venv myenv

source myenv/bin/activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Run the application:
```bash
python Sourcebox.py
```

## Usage

### Controls

- **Left Click**: Interact with objects
  - **Cube**: Spawn the silly cube in-game
  - **Sphere**: Toggle error scene 
  - **Cone**: Doesn't do anything (for now)
- **ESC**: Exit application 

### Source Engine Integration

1. **Automatic Setup**:
   - Launch Sourcebox while a supported game is running
   - Scripts are automatically installed to the game directory `game/scripts/vscripts/`

2. **In-Game Commands**:
```
script PickerToggle()      // toggle aimbot
script PickerNext()        // cycle targets
```

You can also bind them:
```
bind mouse4 "script PickerToggle()"
bind mouse5 "script PickerNext()"
```

3. **Spawning Props**:
   - Click the cube in Sourcebox
   - Prop spawns at your crosshair in-game
   - Shoot spawned props with AWP to quit the game (CS:S)

## Development

### Building from Source

```bash
# install development dependencies
pip install -r requirements.txt

# run in verbose mode for debugging
python source_bridge.py  # test bridge standalone
```

### Compiling to Executable

1. Install PyInstaller:
```bash
pip install pyinstaller
```

2. Build the executable:

**Windows:**
```bash
pyinstaller --onefile --windowed --add-data=assets;assets --icon=assets/images/sourcebox.png --name Sourcebox Sourcebox.py
```

**Linux:**
```bash
pyinstaller --onefile --windowed --add-data=assets:assets --icon=assets/images/sourcebox.png --name Sourcebox Sourcebox.py
```

3. The executable will be in the `dist/` folder!

### Adding New Models

Place `.mdl` files in your game's `models/props/` directory and reference them:
```python
bridge.spawn("props/your_model/model.mdl", 200)
```

## License

This project is licensed under the MIT License.

---
