"""Coordinates Source Engine and Garry's Mod bridge lifecycles."""

import time

from sourcebox import install_manifest


class BridgeManager:
    def __init__(
        self,
        source_bridge_class=None,
        gmod_bridge_class=None,
        *,
        platform_name="",
        windows_api_available=False,
        manifest=None,
    ):
        self.source_bridge_class = source_bridge_class
        self.gmod_bridge_class = gmod_bridge_class
        self.platform_name = platform_name
        self.windows_api_available = windows_api_available
        self.source = None
        self.gmod = None
        self.status = "not_initialized"
        self.diagnostic_message = ""
        self.manifest = manifest

    def _manifest(self):
        return self.manifest or install_manifest.current()

    def initialize(self):
        # files a SourceBox that was killed or crashed did not get to remove
        leftovers = self._manifest().undo_leftovers()
        if leftovers:
            print("\n[cleanup] removing files left by an earlier SourceBox")
            install_manifest.report(leftovers)

        if self.source_bridge_class:
            try:
                self.source = self.source_bridge_class()
                if self.source and self.source.active_game:
                    self._configure_source_bridge()
                    self.status = "connected"
            except Exception as error:
                print(f"Bridge initialization error: {error}")
                self.source = None

        if self.gmod_bridge_class and (
            not self.source or not self.source.active_game
        ):
            try:
                self.gmod = self.gmod_bridge_class()
                if self.gmod and self.gmod.is_connected():
                    self._print_gmod_setup(self.gmod)
                    self.status = "connected"
            except Exception as error:
                print(f"GMod bridge initialization error: {error}")
                self.gmod = None

        self._track_runtime_files()

        if self.status != "connected":
            self.status = "no_game"
            self.diagnostic_message = self._no_game_guidance()
            print(f"\n[bridge] {self.diagnostic_message}")
        return self

    def _no_game_guidance(self):
        if self.platform_name == "Darwin":
            return (
                "No supported running Source game was detected. Start Steam and the game "
                "inside CrossOver first, then restart SourceBox. See "
                "~/Library/Logs/SourceBox/sourcebox.log for detection details."
            )
        return (
            "No supported running Source game was detected. Start the game first, then "
            "restart SourceBox."
        )

    def _configure_source_bridge(self):
        bridge = self.source
        if "Garry's Mod" in bridge.active_game:
            self._print_source_gmod_setup(bridge)
            return

        if getattr(bridge, "modern_bridge", None) is not None:
            bridge.start_listening()
            self._print_modern_vscript_setup(bridge)
            return

        if bridge.vscripts_path:
            if bridge.mapbase_bridge is None:
                bridge.install_listener()
                bridge.install_picker()
                bridge.install_awp_quit()
                bridge.install_auto_spawner()
                bridge.setup_mapspawn()
            bridge.start_listening()
            self._print_vscript_setup(bridge)
            return

        print("\n" + "=" * 70)
        print("SETUP COMPLETE - SOURCE ENGINE")
        print("=" * 70)
        print(f"\n[game] {bridge.active_game}")
        print(f"[session] {bridge.session_id}")
        print("\n[features]")
        if self.platform_name == "Windows" and self.windows_api_available:
            print("  source game with no vscript! ONLY srcbox spawn is supported!")
            print("  mode: legacy console injection (no VScript)")
            print("=" * 70 + "\n")
            print("\n[usage] click cube in SourceBox to spawn")
            print("=" * 70 + "\n")
        else:
            print("  mode: nothing (no VScript and console injection unavailable on this platform)")

    @staticmethod
    def _print_source_gmod_setup(bridge):
        print("\n" + "=" * 70)
        print("SETUP COMPLETE - GARRY'S MOD")
        print("=" * 70)
        print(f"\n[game] {bridge.active_game}")
        print(f"[session] {bridge.session_id}")
        print("\n[features]")
        print("  lua bridge - spawn props from SourceBox")
        print("  picker - aimbot (picker_toggle, picker_next)")
        print("  auto-spawner - spawns cube on map load")
        print("\n[usage] click cube in SourceBox to spawn")
        print("  [addon] installed to addons/sourcebox/lua/")
        print("=" * 70 + "\n")

    @staticmethod
    def _print_vscript_setup(bridge):
        print("\n" + "=" * 70)
        print("SETUP COMPLETE - SOURCE ENGINE")
        print("=" * 70)
        print(f"\n[game] {bridge.active_game}")
        print(f"[session] {bridge.session_id}")
        print("\n[features]")
        print("  python bridge - spawn the cube from sourcebox")
        print("  picker - aimbot (script PickerToggle and PickerNext)")
        print("  awp quit - shoot srcbox with awp to quit the game")
        print("  auto-spawner - spawns 1 cube at random locations on map load")
        print("\n[auto-load] all scripts start automatically on map load")
        print("\n[manual] if needed:")
        if bridge.mapbase_bridge:
            print("         exec mapbase_default")
            print("         script_execute vscript_server")
        else:
            print("         script_execute python_listener")
        print("=" * 70 + "\n")

    @staticmethod
    def _print_modern_vscript_setup(bridge):
        modern = bridge.modern_bridge
        print("\n" + "=" * 70)
        print("SETUP COMPLETE - SOURCE ENGINE")
        print("=" * 70)
        print(f"\n[game] {bridge.active_game}")
        print(f"[session] {bridge.session_id}")
        print(f"[mode] {modern.description}")
        print("\n[features]")
        print("  python bridge - spawn the cube from sourcebox")
        print("  auto-spawner - spawns 1 cube near the player on map load")
        if modern.branch == "l4d2":
            print("  picker - local survivor aim lock (!picker and !pickernext in game chat)")
        elif modern.branch == "portal2":
            print("  picker - experimental single-player aim lock (sv_cheats 1, script PickerToggle())")
        elif modern.branch == "csgo":
            print("  picker - local practice aim lock (sv_cheats 1, script PickerToggle())")
        print("\n[auto-load] the bridge starts on the next map load")
        print("\n[manual] if needed:")
        print("         script_execute sourcebox_bridge")
        if modern.response_file is None:
            print("\n[note] this game cannot write files: spawn results show in its console")
        print("=" * 70 + "\n")

    @staticmethod
    def _print_gmod_setup(bridge):
        print("\n" + "=" * 70)
        print("SETUP COMPLETE - GARRY'S MOD")
        print("=" * 70)
        print(f"\n[game] {bridge.active_gmod}")
        print(f"[data path] {bridge.data_path}")
        print(f"[session] {bridge.session_id}")
        print("\n[features]")
        print("  python bridge - spawn props from SourceBox")
        print("  picker - aimbot (picker_toggle, picker_next)")
        print("  auto-spawner - spawns cube on map load")
        print("\n[usage] click cube in SourceBox to spawn")
        print("  [addon] installed to addons/sourcebox/lua/")
        print("=" * 70 + "\n")

    def spawn_default_cube(self):
        model = "props/srcbox/srcbox.mdl"
        if self.source and self.source.active_game:
            try:
                self.source.spawn(model, 200)
                time.sleep(0.1)
                if (
                    self.source.mapbase_bridge is None
                    and getattr(self.source, "modern_bridge", None) is None
                ):
                    self.source.reinstall_awp_outputs()
            except Exception as error:
                print(f"Bridge spawn error: {error}")
            return

        if self.gmod and self.gmod.is_connected():
            try:
                self.gmod.spawn_model(model, 200)
                time.sleep(0.1)
            except Exception as error:
                print(f"GMod bridge spawn error: {error}")
            return

        print(f"[bridge] Cube spawn skipped: {self.diagnostic_message}")

    def _track_runtime_files(self):
        # command and response files come and go while SourceBox runs; the game
        # writes the responses itself, so they are recorded here
        manifest = self._manifest()
        for bridge in (self.source, self.gmod):
            for name in ("command_file", "response_file"):
                path = getattr(bridge, name, None) if bridge else None
                if isinstance(path, str) and path:
                    manifest.track(path)

    def cleanup(self):
        if self.source and getattr(self.source, "active_game", None):
            try:
                self.source.stop()
            except Exception:
                pass

        if self.gmod:
            try:
                self.gmod.cleanup()
            except Exception:
                pass

        # remove everything SourceBox installed into games, restoring originals
        try:
            done = self._manifest().undo()
            if done:
                print("\n[cleanup] removing SourceBox files from games")
                install_manifest.report(done)
        except Exception as error:
            print(f"[cleanup] failed: {error}")
