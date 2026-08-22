# SourceBox architecture

`Sourcebox.py` remains the executable entry point for compatibility with existing
commands and PyInstaller builds. It owns the application loop and scene switching.

## Runtime modules

- `sourcebox/audio.py` manages sound effects and music.
- `sourcebox/cursor.py` loads and renders the custom cursor.
- `sourcebox/raycast.py` converts mouse positions into world-space rays.
- `sourcebox/resources.py` resolves development and PyInstaller resources.
- `sourcebox/steam.py` contains shared Steam installation, library, and CrossOver
  bottle discovery.
- `sourcebox/bridges/manager.py` coordinates bridge setup, spawning, and cleanup.
- `sourcebox/bridges/source_discovery.py` locates Source games and sourcemods.
- `sourcebox/rendering/main_scene.py` contains main-menu geometry and lighting.
- `sourcebox/scenes/missing_texture.py` contains the error scene.
- `cone_scene.py` owns Voidside scene state and update behavior.
- `sourcebox/scenes/cone_entities.py` owns the floating XYZ pointers.
- `sourcebox/scenes/cone_renderer.py` owns Voidside OpenGL and text rendering.

## Game-side scripts

Generated Lua and VScript payloads live under `bridge_scripts/`. Python bridge
classes load these files as resources rather than embedding thousands of lines in
method bodies. The build workflow packages this directory with the executable.

## Tests

Run the dependency-light characterization suite with:

```bash
python -m unittest discover -v
```

The tests protect ARG-sensitive timing and camera behavior, extracted script bytes,
Steam library parsing, and bridge coordination. Preserve random-call ordering when
refactoring `cone_scene.py` or its entity classes.
