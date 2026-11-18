# SourceBox architecture

`Sourcebox.py` remains the executable entry point for compatibility with existing
commands and PyInstaller builds. It owns the application loop and scene switching.

## Runtime modules

- `sourcebox/audio.py` manages sound effects and music.
- `sourcebox/cursor.py` loads and renders the custom cursor.
- `sourcebox/demo_watcher.py` detects in-game demo playback by scanning for open
  `.dem` files in a separate worker process (so `psutil` can never stall rendering);
  the cone scene uses it to enter PULL mode.
- `sourcebox/raycast.py` converts mouse positions into world-space rays.
- `sourcebox/resources.py` resolves development and PyInstaller resources.
- `sourcebox/steam.py` contains shared Steam installation, library, and CrossOver
  bottle discovery.
- `sourcebox/bridges/manager.py` coordinates bridge setup, spawning, and cleanup.
- `sourcebox/bridges/source_discovery.py` locates Source games and sourcemods.
- `sourcebox/install_manifest.py` records every file and folder the bridges write
  into games (`installed.json` next to the log, with backups of anything
  replaced) and undoes it when SourceBox closes. A guard process
  (`Sourcebox.py --cleanup-guard <pid>`) undoes it if SourceBox is killed, and
  leftovers are undone at the next start. Bridges must write through
  `install_manifest.write_text` / `make_dirs` / `track`, not `open()`.
- `sourcebox/bridges/modern_vscript.py` sets up the newer VScript branches (L4D2,
  Portal 2, CS:GO, Alien Swarm, Strata Source). They share
  `bridge_scripts/modern/sourcebox_bridge.nut`; L4D2 receives commands through
  `ems/` files, the rest through a re-included `sourcebox_command.nut`, because
  their scripts cannot read files. Strata games are found by `scriptsystem.dll`
  beside a `bin/win64` launcher.
- `sourcebox/rendering/main_scene.py` contains main-menu geometry, camera, and
  lighting. Its values are fitted to the reference render; the menu lights itself
  with `GL_LIGHT1` and leaves `GL_LIGHT0` as Voidside expects to inherit it.
- `sourcebox/rendering/shadows.py` computes the sphere's shadow on the cube
  (pure Python, no OpenGL).
- `sourcebox/rendering/picking.py` does exact ray hits on the menu shapes for
  hover and click (pure Python). The spinning cube is drawn without depth, so it
  is only picked where no other shape is under the mouse.
- `sourcebox/rendering/antialias.py` provides 4x MSAA for every scene. If the
  window itself has no multisampling, frames go through an offscreen multisampled
  framebuffer; show each frame with `frame_target.present()`, not `pygame.display.flip()`.
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

`tests/test_modern_vscript_squirrel.py` also runs the newer-branch bridge script
in a real Squirrel interpreter against `tests/squirrel/engine_mock.nut`. It is
skipped unless `SOURCEBOX_SQUIRREL` points at an `sq` executable (Squirrel 3.x,
built from https://github.com/albertodemichelis/squirrel).

The tests protect ARG-sensitive timing and camera behavior, extracted script bytes,
Steam library parsing, and bridge coordination. Preserve random-call ordering when
refactoring `cone_scene.py` or its entity classes.
