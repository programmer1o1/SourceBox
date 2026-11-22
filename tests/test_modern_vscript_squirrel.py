"""Runs the newer-branch bridge script in a real Squirrel interpreter.

The engine is replaced by tests/squirrel/engine_mock.nut, which defines only the
functions each game family really has. Set SOURCEBOX_SQUIRREL to the path of an
`sq` interpreter (Squirrel 3.x) to run these; without it they are skipped.
"""

import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from sourcebox.bridges.modern_vscript import (
    BRANCHES,
    bridge_script,
    command_script,
    hook_script,
)

SQUIRREL = os.environ.get("SOURCEBOX_SQUIRREL")
MOCK = Path(__file__).resolve().parent / "squirrel" / "engine_mock.nut"

# 13+ digit session ids do not fit the 32-bit integers of the older games
SESSION_A = "1763300000000123"
SESSION_B = "1763300000999999"
CUBE = "models/props/srcbox/srcbox.mdl"


def _verbatim(text):
    return '@"' + text.replace('"', '""') + '"'


def _command(session, ident):
    return ('{"command":"spawn_model","model":"props/srcbox/srcbox.mdl","distance":200,'
            f'"id":{ident},"session":{session}}}')


def _scenario(branch, has_cube_maker=True, l4d2_precache=True, l4d2_spawn=True, revolution_assets=False):
    transport = BRANCHES[branch]["transport"]
    hook = BRANCHES[branch]["hook"][:-4]
    cmd_key = "sourcebox_command.txt" if transport == "file" else "sourcebox_command.nut"
    wrap = (lambda text: text) if transport == "file" else command_script
    with_original = branch == "portal2"

    lines = [
        f'::MOCK_BRANCH <- "{branch}";',
        f'::MOCK_MAP_MODEL <- {_verbatim(CUBE)};',
        f'::MOCK_HAS_CUBE_MAKER <- {str(has_cube_maker).lower()};',
        f'::MOCK_L4D2_PRECACHE <- {str(l4d2_precache).lower()};',
        f'::MOCK_L4D2_SPAWN <- {str(l4d2_spawn).lower()};',
        'dofile("engine_mock.nut");',
        f'::FILES["sourcebox_bridge.nut"] <- {_verbatim(bridge_script(branch))};',
        f'::FILES["{hook}.nut"] <- {_verbatim(hook_script(with_original, branch, revolution_assets))};',
        f'::FILES["{cmd_key}"] <- {_verbatim(wrap(""))};',
    ]
    if with_original:
        lines.append('::FILES["sourcebox_original_mapspawn.nut"] <- @"printl(""original mapspawn"")";')
    if branch in ("portal2", "csgo", "revolution"):
        lines.append("::WORLD_SPAWNED = false;")
    if branch == "csgo":
        lines.append('if (!::MOCK_HAS_CUBE_MAKER) ::MAP_PROP.model = null;')
    activate_map = '::Portal2ActivateMap();' if branch == "portal2" else ''
    lines += [
        'local show = function(tag) {',
        '    local s = "STEP " + tag;',
        '    foreach (p in ::PROPS) s += " | " + p.cls + " " + p.origin + " " + p.model + " " + p.tint;',
        '    print(s + "\\n");',
        '};',
        f'::RunFile("{hook}", getroottable());',
        '::WORLD_SPAWNED = true;',
        activate_map,
        '::Advance(2.0); show("before_autospawn");',
        '::Advance(2.0); show("autospawn");',
        f'::FILES["{cmd_key}"] <- {_verbatim(wrap(_command(SESSION_A, 1)))};',
        '::Advance(0.5); show("command");',
        '::Advance(1.0); show("command_again");',
        f'::FILES["{cmd_key}"] <- {_verbatim(wrap(_command(SESSION_B, 1)))};',
        '::Advance(0.5); show("new_session");',
        '::NewMap();',
        f'::RunFile("{hook}", getroottable());',
        activate_map,
        'local polls = function() {',
        '    local n = 0;',
        '    foreach (k in ["DoIncludeScript:sourcebox_command", "FileToString"]) if (k in ::CALLS) n += ::CALLS[k];',
        '    return n;',
        '};',
        'local before = polls();',
        '::Advance(5.0); show("new_map");',
        'print("POLLS " + (polls() - before) + "\\n");',
        'local not_found = function() { return ("Script not found" in ::CALLS) ? ::CALLS["Script not found"] : 0; };',
        # SourceBox is killed mid-map: the guard just removes the command file
        'local before_close = polls();',
        f'delete ::FILES["{cmd_key}"];',
        '::Advance(3.0);',
        'print("POLLS_AFTER_CLOSE " + (polls() - before_close) + "\\n");',
        'print("NOT_FOUND_AFTER_CLOSE " + not_found() + "\\n");',
        # SourceBox closes normally: "quit" first, then the files go
        f'::FILES["{cmd_key}"] <- {_verbatim(wrap(""))};',
        '::NewMap();',
        f'::RunFile("{hook}", getroottable());',
        activate_map,
        '::Advance(1.5);',
        'local before_quit = polls();',
        'local not_found_before_quit = not_found();',
        f'::FILES["{cmd_key}"] <- {_verbatim(wrap("quit"))};',
        '::Advance(0.4);',
        f'delete ::FILES["{cmd_key}"];',
        '::Advance(3.0);',
        'print("POLLS_AFTER_QUIT " + (polls() - before_quit) + "\\n");',
        'print("NOT_FOUND_AFTER_QUIT " + (not_found() - not_found_before_quit) + "\\n");',
        'foreach (call in ["SpawnEntityAtLocation", "CreateProp", "SpawnEntityFromTable", "PrecacheModel"]) {',
        '    print("SPAWN_CALL " + call + " " + ((call in ::CALLS) ? ::CALLS[call] : 0) + "\\n");',
        '}',
        'foreach (line in ::LOGS) print("LOG " + line + "\\n");',
    ]
    return "\n".join(lines) + "\n"


def _run_squirrel(script_text):
    with tempfile.TemporaryDirectory() as temp:
        shutil.copy(MOCK, temp)
        script = Path(temp) / "scenario.nut"
        script.write_text(script_text, encoding="utf-8", newline="\n")
        return subprocess.run([SQUIRREL, script.name], cwd=temp, capture_output=True, text=True, timeout=60)


def _run(branch, **scenario_options):
    result = _run_squirrel(_scenario(branch, **scenario_options))
    if result.returncode != 0 or "ERROR" in result.stdout + result.stderr:
        raise AssertionError(f"{branch} script failed:\n{result.stdout}\n{result.stderr}")

    steps, logs, polls = {}, [], None
    for line in result.stdout.splitlines():
        if line.startswith("STEP "):
            tag, *props = line[5:].split(" | ")
            steps[tag] = props
        elif line.startswith("LOG "):
            logs.append(line[4:])
        elif line.startswith("POLLS "):
            polls = int(line.split()[1])
        elif line.startswith("SPAWN_CALL "):
            _, name, value = line.split()
            steps[name] = int(value)
        elif line.split(" ")[0] in ("POLLS_AFTER_CLOSE", "NOT_FOUND_AFTER_CLOSE",
                                    "POLLS_AFTER_QUIT", "NOT_FOUND_AFTER_QUIT"):
            name, value = line.split()
            steps[name.lower()] = int(value)
    return steps, logs, polls


def _run_client_vm(branch):
    """Load the hook in a client-side VM; returns (exit code, output)."""
    hook = BRANCHES[branch]["hook"][:-4]
    lines = [
        "::MOCK_CLIENT_VM <- true;",
        f'::MOCK_BRANCH <- "{branch}";',
        "::MOCK_MAP_MODEL <- null;",
        "::MOCK_HAS_CUBE_MAKER <- false;",
        'dofile("engine_mock.nut");',
        f'::FILES["sourcebox_bridge.nut"] <- {_verbatim(bridge_script(branch))};',
        f'::FILES["{hook}.nut"] <- {_verbatim(hook_script(False, branch))};',
        f'::RunFile("{hook}", getroottable());',
        "::Advance(1.0);",
        'foreach (line in ::LOGS) print("LOG " + line + "\\n");',
    ]
    result = _run_squirrel("\n".join(lines) + "\n")
    return result.returncode, result.stdout + result.stderr


def _position(prop):
    match = re.search(r"\(([-\d.]+) ([-\d.]+) ([-\d.]+)\)", prop)
    return tuple(float(v) for v in match.groups())


@unittest.skipUnless(SQUIRREL and os.path.isfile(SQUIRREL), "set SOURCEBOX_SQUIRREL to an sq interpreter")
class BridgeScriptRunTests(unittest.TestCase):
    def test_csgo_picker_targets_visible_bots_and_stops_with_a_second_player(self):
        setup = [
            '::MOCK_BRANCH <- "csgo";',
            f'::MOCK_MAP_MODEL <- {_verbatim(CUBE)};',
            '::MOCK_HAS_CUBE_MAKER <- true;',
            'dofile("engine_mock.nut");',
            f'::FILES["sourcebox_bridge.nut"] <- {_verbatim(bridge_script("csgo"))};',
            f'::FILES["sourcebox_command.nut"] <- {_verbatim(command_script(""))};',
        ]
        scenario = r'''
::RunFile("sourcebox_bridge", getroottable());
local teammate = ::MakeProp("player", Vector(20, 0, 64), "teammate");
local blocked = ::MakeProp("player", Vector(30, 0, 64), "blocked");
blocked.team = 3;
::CSGO_BLOCKED_TARGET = blocked;
local cube = ::MakeProp("prop_physics_override", Vector(-40, 0, 64), ::SOURCEBOX_MODEL);

::Advance(1.1);
::PickerToggle();
::Advance(0.2);
assert(::g_sourcebox_picker.target == teammate);
assert(::CALLS.PickerHudDisplay == 1);
local enemy = ::MakeProp("player", Vector(0, 70, 72), "enemy");
enemy.team = 3;
::Advance(0.25);
assert(::g_sourcebox_picker.target == enemy);
::PickerToggle();
::PickerToggle();
::Advance(0.2);
assert(::g_sourcebox_picker.target == enemy);
assert(::CSGO_CONSOLE.len() > 2);
local botYaw = ::g_sourcebox_picker.angles.y;
assert(botYaw > 0.0 && botYaw < 90.0);
assert(::g_sourcebox_picker.angles.x < 0.0);
::PickerNext();
::Advance(0.2);
assert(::g_sourcebox_picker.target == teammate);
::PickerNext();
::Advance(0.2);
assert(::g_sourcebox_picker.target == cube);
assert(::g_sourcebox_picker.angles.y > botYaw && ::g_sourcebox_picker.angles.y < 180.0);
::PickerNext();
assert(::g_sourcebox_picker.target == enemy);
::PLAYER.team = 3;
::Advance(0.25);
assert(::g_sourcebox_picker.target == enemy); // Manual selection stays locked.
::PickerToggle();
::PickerToggle();
::Advance(0.2);
assert(::g_sourcebox_picker.target == teammate);

local count = ::CSGO_CONSOLE.len();
local hudDisplays = ::CALLS.PickerHudDisplay;
::CSGO_EXTRA_PLAYER = Ent("player", Vector());
::Advance(0.7);
assert(!::g_sourcebox_picker.enabled);
assert(::CSGO_CONSOLE.len() == count);
assert(::CALLS.PickerHudDisplay == hudDisplays);
::PickerToggle();
assert(!::g_sourcebox_picker.enabled);

::CSGO_EXTRA_PLAYER = null;
::PickerToggle();
::FILES["sourcebox_command.nut"] = @"::g_sourcebox_command <- ""quit"";";
::Advance(0.2);
assert(!::g_sourcebox_picker.enabled);
assert(::CSGO_CONSOLE.len() == count);
print("CSGO PICKER PASS\n");
'''
        result = _run_squirrel("\n".join(setup) + "\n" + scenario)
        output = result.stdout + result.stderr
        self.assertEqual(result.returncode, 0, output)
        self.assertNotIn("ERROR", output)
        self.assertIn("CSGO PICKER PASS", output)

    def test_portal2_picker_aims_cycles_and_stops(self):
        setup = [
            '::MOCK_BRANCH <- "portal2";',
            f'::MOCK_MAP_MODEL <- {_verbatim(CUBE)};',
            '::MOCK_HAS_CUBE_MAKER <- false;',
            'dofile("engine_mock.nut");',
            f'::FILES["sourcebox_bridge.nut"] <- {_verbatim(bridge_script("portal2"))};',
        ]
        scenario = r'''
::FILES["sourcebox_command.nut"] <- @"::g_sourcebox_command <- ""{}"";";
::RunFile("sourcebox_bridge", getroottable());
local blocked = ::MakeProp("prop_weighted_cube", Vector(25, 0, 64), "blocked");
local cube = ::MakeProp("prop_physics", Vector(0, 50, 64), "cube");
local turret = ::MakeProp("npc_portal_turret_floor", Vector(0, -100, 64), "turret");
::PORTAL2_BLOCKED.append(blocked);

::PORTAL2_MULTIPLAYER = true;
::PickerToggle();
assert(!::g_sourcebox_picker.enabled);
::PORTAL2_MULTIPLAYER = false;
::PickerToggle();
::Advance(1.1);
assert(::g_sourcebox_picker.target == turret);
assert(::PORTAL2_CONSOLE.len() > 2);
assert(::CALLS.PickerHudDisplay == 1);
local turretYaw = ::g_sourcebox_picker.angles.y;
assert(turretYaw < 0.0 && turretYaw > -90.0);
::PickerNext();
::Advance(0.3);
assert(::g_sourcebox_picker.target == cube);
assert(::g_sourcebox_picker.angles.y > turretYaw && ::g_sourcebox_picker.angles.y < 90.0);
::PickerNext();
::Advance(0.1);
assert(::g_sourcebox_picker.target == turret);
::PORTAL2_BLOCKED.append(turret);
::Advance(0.25);
assert(::g_sourcebox_picker.target == cube);
assert(::CALLS.PickerHudDisplay == 1);

::PickerToggle();
assert(::CALLS.PickerHudClear == 1);
::PickerToggle();
::Advance(0.3);
assert(::CALLS.PickerHudDisplay == 2);

::FILES["sourcebox_command.nut"] = @"::g_sourcebox_command <- ""quit"";";
::Advance(0.2);
assert(!::g_sourcebox_picker.enabled);
assert(::CALLS.PickerHudClear == 2);
local commands = ::PORTAL2_CONSOLE.len();
local hudDisplays = ::CALLS.PickerHudDisplay;
::Advance(0.7);
assert(::PORTAL2_CONSOLE.len() == commands);
assert(::CALLS.PickerHudDisplay == hudDisplays);
print("PORTAL 2 PICKER PASS\n");
'''
        result = _run_squirrel("\n".join(setup) + "\n" + scenario)
        output = result.stdout + result.stderr
        self.assertEqual(result.returncode, 0, output)
        self.assertNotIn("ERROR", output)
        self.assertIn("PORTAL 2 PICKER PASS", output)

    def test_l4d2_picker_cycles_visible_targets_and_stops_with_sourcebox(self):
        setup = [
            '::MOCK_BRANCH <- "l4d2";',
            'dofile("engine_mock.nut");',
            f'::FILES["sourcebox_bridge.nut"] <- {_verbatim(bridge_script("l4d2"))};',
        ]
        scenario = r'''
::FILES["sourcebox_command.txt"] <- "{}";
::RunFile("sourcebox_bridge", getroottable());

local ally = Ent("player", Vector(10, 0, 64));
local ghost = Ent("player", Vector(15, 0, 64));
ghost.team = 3;
ghost.ghost = true;
local dead = Ent("infected", Vector(20, 0, 64));
dead.health = 0;
local blocked = Ent("infected", Vector(30, 0, 64));
local prop = Ent("prop_physics_override", Vector(40, 0, 64));
local near = Ent("infected", Vector(80, 80, 64));
local nearPeer = Ent("infected", Vector(80, -80, 64));
local special = Ent("player", Vector(130, 20, 32));
special.team = 3;
local far = Ent("witch", Vector(150, -150, 64));
::PICKER_TARGETS = [::PLAYER, prop];
::PICKER_BLOCKED_POSITIONS = [blocked.origin, special.origin];
local say = function(user, message, eventName = "player_say") {
    if (!(eventName in ::GameEventCallbacks)) return;
    foreach (scope in ::GameEventCallbacks[eventName]) {
        if (scope != null) scope["OnGameEvent_" + eventName]({ userid = user, text = message });
    }
};

assert(!::g_sourcebox_picker.enabled);
::PICKER_HOST_AVAILABLE = false;
say(1, "!picker");
assert(!::g_sourcebox_picker.enabled);
::PICKER_HOST_AVAILABLE = true;
say(2, "!picker");
assert(!::g_sourcebox_picker.enabled);
::Advance(0.15);
assert(!("SnapEyeAngles" in ::CALLS));

say(1, "  !PICKER  ", "player_chat");
say(1, "!picker");
assert(::PICKER_CHAT_MESSAGES.len() == 1);
::Advance(0.15);
assert(::g_sourcebox_picker.target == prop);
::PICKER_TARGETS.append(ally);
::Advance(0.3);
assert(::g_sourcebox_picker.target == ally);
::PICKER_TARGETS.extend([ghost, dead, blocked, near, nearPeer, special, far]);
::Advance(0.3);
assert(::g_sourcebox_picker.target == near);
assert(::PLAYER.aim.y > 0.0);
assert(!("DebugDrawBox" in ::CALLS));
assert(::PICKER_CHAT_MESSAGES.top() == "[SourceBox] Picker on");
say(1, "!pickernext");
assert(::g_sourcebox_picker.target == nearPeer);
say(1, "!pickernext");
assert(::g_sourcebox_picker.target == special);
assert(::SourceBoxL4D2PickerCandidate(special, ::PLAYER.EyePosition(), ::PLAYER).position.z == 96);
say(1, "!pickernext");
assert(::g_sourcebox_picker.target == far);
say(1, "!pickernext");
assert(::g_sourcebox_picker.target == ally);
::Advance(0.3);
assert(::g_sourcebox_picker.target == ally);
say(1, "!pickernext");
assert(::g_sourcebox_picker.target == prop);
say(1, "!pickernext");
assert(::g_sourcebox_picker.target == near);

local allTargets = ::PICKER_TARGETS;
::PICKER_TARGETS = [::PLAYER, near];
local aimsBeforeCover = ::CALLS.SnapEyeAngles;
::PICKER_BLOCKED_POSITIONS.append(near.origin);
::Advance(0.35);
assert(::CALLS.SnapEyeAngles == aimsBeforeCover);
assert(::g_sourcebox_picker.target == null);
::PICKER_TARGETS = allTargets;

::PICKER_BLOCKED_POSITIONS.append(nearPeer.origin);
::Advance(0.3);
assert(::g_sourcebox_picker.target == special);
::PLAYER.incapacitated = true;
local aims = ::CALLS.SnapEyeAngles;
::Advance(0.2);
assert(::g_sourcebox_picker.target == null);
assert(::CALLS.SnapEyeAngles == aims);
::PLAYER.incapacitated = false;

say(1, "!picker");
::Advance(0.2);
assert(::CALLS.SnapEyeAngles == aims);
say(1, "!picker");
::Advance(0.2);
assert(::CALLS.SnapEyeAngles > aims);
::FILES["sourcebox_command.txt"] = "quit";
::Advance(0.3);
assert(::g_sourcebox_stopped);
assert(!::g_sourcebox_picker.enabled);
say(1, "!picker");
assert(!::g_sourcebox_picker.enabled);
aims = ::CALLS.SnapEyeAngles;
::Advance(0.2);
assert(::CALLS.SnapEyeAngles == aims);

::FILES["sourcebox_command.txt"] = "{}";
::Advance(1.1);
assert(!::g_sourcebox_stopped);
assert(!::g_sourcebox_picker.enabled);
::GameEventCallbacks = {};
::Advance(1.1);
assert(::GameEventCallbacks.player_say.len() == 1);
assert(::GameEventCallbacks.player_chat.len() == 1);
::Advance(1.1);
assert(::GameEventCallbacks.player_say.len() == 1);
assert(::GameEventCallbacks.player_chat.len() == 1);
say(1, "!picker");
::Advance(0.2);
assert(::CALLS.SnapEyeAngles > aims);

::NewMap();
::RunFile("sourcebox_bridge", getroottable());
assert(!::g_sourcebox_picker.enabled);
say(1, "!picker");
assert(::g_sourcebox_picker.enabled);
assert(!("DebugDrawBox" in ::CALLS));
print("PICKER PASS\n");
'''
        result = _run_squirrel("\n".join(setup) + "\n" + scenario)
        output = result.stdout + result.stderr
        self.assertEqual(result.returncode, 0, output)
        self.assertNotIn("ERROR", output)
        self.assertIn("PICKER PASS", output)

    def test_l4d2_skips_spawning_when_the_model_cannot_be_precached(self):
        steps, logs, _polls = _run("l4d2", l4d2_precache=False)
        self.assertEqual(steps["autospawn"], [])
        self.assertEqual(steps["command"], [])
        self.assertEqual(steps["SpawnEntityFromTable"], 0)
        self.assertEqual(steps["CreateProp"], 0)
        self.assertIn(f"[SourceBox] auto-spawn skipped: model not precached on this map: {CUBE}", logs)

    def test_l4d2_does_not_create_a_visual_prop_if_physics_spawn_fails(self):
        steps, _logs, _polls = _run("l4d2", l4d2_spawn=False)
        self.assertGreater(steps["SpawnEntityFromTable"], 0)
        self.assertEqual(steps["autospawn"], [])
        self.assertEqual(steps["command"], [])
        self.assertEqual(steps["CreateProp"], 0)

    def test_template_branches_skip_spawns_without_a_cube_template(self):
        for branch in ("portal2", "swarm", "revolution"):
            with self.subTest(branch=branch):
                steps, logs, _polls = _run(branch, has_cube_maker=False)
                self.assertEqual(steps["autospawn"], [])
                self.assertEqual(steps["command"], [])
                self.assertEqual(steps["CreateProp"], 0)
                self.assertEqual(steps["SpawnEntityAtLocation"], 0)
                self.assertIn("[SourceBox] auto-spawn skipped: custom cube template unavailable; load a fresh supported map", logs)
                self.assertIn("[SourceBox] error: custom cube template unavailable; load a fresh supported map", logs)

    def test_revolution_uses_the_map_start_precache_when_lumps_are_ignored(self):
        steps, logs, _ = _run("revolution", has_cube_maker=False, revolution_assets=True)
        self.assertIn("[SourceBox] Revolution cube model loaded during map startup", logs)
        self.assertEqual(len(steps["autospawn"]), 1)
        self.assertEqual(len(steps["command"]), 2)
        self.assertTrue(steps["command"][1].startswith("prop_physics_override (100.5 0.0 16.0)"))
        self.assertEqual(steps["SpawnEntityAtLocation"], 0)
        self.assertEqual(steps["PrecacheModel"], 0)

    def test_csgo_skips_the_nonphysical_fallback_without_a_template(self):
        steps, logs, _ = _run("csgo", has_cube_maker=False)
        self.assertEqual(steps["command"], [])
        self.assertEqual(steps["PrecacheModel"], 0)
        self.assertEqual(steps["CreateProp"], 0)
        self.assertIn("[SourceBox] error: custom cube template unavailable; load a map with Stripper:Source active or use a SourceBox-prepared map", logs)

    def test_csgo_poll_survives_round_cleanup_and_replaces_the_removed_auto_cube(self):
        setup = [
            '::MOCK_BRANCH <- "csgo";',
            '::MOCK_MAP_MODEL <- null;',
            '::MOCK_HAS_CUBE_MAKER <- true;',
            'dofile("engine_mock.nut");',
            f'::FILES["sourcebox_bridge.nut"] <- {_verbatim(bridge_script("csgo"))};',
            f'::FILES["sourcebox_command.nut"] <- {_verbatim(command_script(""))};',
        ]
        scenario = r'''
::RunFile("sourcebox_bridge", getroottable());
::MOCK_MAP_MODEL = ::SOURCEBOX_MODEL;
::Advance(4.0);
assert(::PROPS.len() == 1);
local first = ::PROPS.pop();
first.Destroy();
::QUEUE = [];
::THINKS = ::THINKS.filter(function(index, think) { return think.ent.GetClassname() == "soundent"; });
::CSGO_WARMUP = false;
::Advance(1.5);
assert(::PROPS.len() == 1);
assert(::PROPS[0].IsValid());
'''
        commands = [
            f'::FILES["sourcebox_command.nut"] = {_verbatim(command_script(_command(SESSION_A, 1)))};',
            '::Advance(0.5);',
            'assert(::PROPS.len() == 2);',
            'assert(::PROPS[1].GetClassname() == "prop_physics_override");',
            'print("CSGO ROUND PASS\\n");',
        ]
        result = _run_squirrel("\n".join(setup) + "\n" + scenario + "\n".join(commands))
        output = result.stdout + result.stderr
        self.assertEqual(result.returncode, 0, output)
        self.assertNotIn("ERROR", output)
        self.assertIn("CSGO ROUND PASS", output)

    def test_every_branch_runs_a_full_session(self):
        # L4D2 and Strata see the 30 degree downward look and hit the floor;
        # the others only know the body facing and spawn level, 200 units out
        expected_view_hit = {
            "l4d2": (100.5, 0.0, 16.0),
            "strata": (110.9, 0.0, 10.0),
            "revolution": (100.5, 0.0, 16.0),
            "portal2": (200.0, 0.0, 74.0),
            "csgo": (200.0, 0.0, 74.0),
            "swarm": (200.0, 0.0, 74.0),
        }
        for branch in BRANCHES:
            with self.subTest(branch=branch):
                steps, logs, polls = _run(branch)

                self.assertEqual(steps["before_autospawn"], [])
                self.assertEqual(len(steps["autospawn"]), 1)
                self.assertEqual(_position(steps["autospawn"][0])[2], 16.0)

                self.assertEqual(len(steps["command"]), 2)
                spawned = steps["command"][1]
                for got, want in zip(_position(spawned), expected_view_hit[branch]):
                    self.assertAlmostEqual(got, want, places=1)
                self.assertIn(CUBE, spawned)
                # no tint: the cube keeps the model's own colours
                self.assertTrue(spawned.endswith(" null"), spawned)
                # the reported position is where the cube really is, not the map
                # origin P2CE first spawns it at
                x, y, z = (int(v) for v in expected_view_hit[branch])
                classname = "prop_physics" if branch == "strata" else "prop_physics_override"
                if branch != "l4d2":  # L4D2 writes its result to ems/ instead
                    self.assertIn(f"[SourceBox] spawned: {classname} at ({x} {y} {z}) model {CUBE}", logs)
                self.assertIn(f"[SourceBox] cube after 1s: {classname} at ({x} {y} {z}) model {CUBE}", logs)

                self.assertEqual(len(steps["command_again"]), 2, "same command ran twice")
                self.assertEqual(len(steps["new_session"]), 3, "new session was ignored")
                # after a map change: one new auto-spawn, the old command not replayed
                self.assertEqual(len(steps["new_map"]), 4)
                if branch in ("portal2", "swarm", "csgo", "revolution"):
                    self.assertEqual(steps["SpawnEntityAtLocation"], 4)
                    self.assertEqual(steps["CreateProp"], 0)
                if branch == "l4d2":
                    self.assertEqual(steps["SpawnEntityFromTable"], 4)
                    self.assertEqual(steps["PrecacheModel"], 2)
                    self.assertEqual(steps["CreateProp"], 0)
                # one polling chain, about 10 checks a second over 5 seconds
                self.assertGreaterEqual(polls, 35)
                self.assertLessEqual(polls, 55)
                self.assertIn(f"[SourceBox] bridge loaded ({branch})", logs)
                # killed SourceBox, command file removed: one failed read, then quiet
                if branch != "l4d2":
                    self.assertEqual(steps["polls_after_close"], 1)
                    self.assertEqual(steps["not_found_after_close"], 1)
                    self.assertEqual(steps["polls_after_quit"], 1)
                else:
                    self.assertLessEqual(steps["polls_after_close"], 4)
                    self.assertLessEqual(steps["polls_after_quit"], 4)
                # normal close: the bridge reads "quit" and stops before the file goes
                self.assertEqual(steps["not_found_after_quit"], 0)
                self.assertEqual(logs.count("[SourceBox] SourceBox closed, bridge stopped"), 2)

    def test_client_side_vm_skips_the_bridge_without_errors(self):
        # P2CE runs mapspawn.nut in its client VM too, where Entities does not exist
        for branch in BRANCHES:
            with self.subTest(branch=branch):
                code, output = _run_client_vm(branch)
                self.assertEqual(code, 0, output)
                self.assertNotIn("ERROR", output)
                # silent: not even a "failed to start" line
                self.assertNotIn("[SourceBox]", output)

    def test_portal2_original_mapspawn_runs_before_the_bridge(self):
        _steps, logs, _polls = _run("portal2")
        self.assertLess(logs.index("original mapspawn"), logs.index("[SourceBox] bridge loaded (portal2)"))

    def test_portal2_picker_is_loaded_after_save_restore(self):
        setup = [
            '::MOCK_BRANCH <- "portal2";',
            '::MOCK_MAP_MODEL <- null;',
            '::MOCK_HAS_CUBE_MAKER <- false;',
            'dofile("engine_mock.nut");',
            f'::FILES["mapspawn.nut"] <- {_verbatim(hook_script(False, "portal2"))};',
            f'::FILES["sourcebox_bridge.nut"] <- {_verbatim(bridge_script("portal2"))};',
            f'::FILES["sourcebox_command.nut"] <- {_verbatim(command_script(""))};',
        ]
        scenario = r'''
local oldStarter = Entities.CreateByClassname("logic_auto");
oldStarter.__KeyValueFromString("targetname", "sourcebox_portal2_start");
::RunFile("mapspawn", getroottable());
assert(!oldStarter.IsValid());
assert(!("PickerToggle" in getroottable()));
local starter = Entities.FindByName(null, "sourcebox_portal2_activate");
// The VM and event queue are restored while the native map entities remain.
::QUEUE = [];
local savedStarter = Entities.CreateByClassname("logic_auto");
savedStarter.kv = starter.kv;
::Portal2ActivateMap();
::Advance(0.3);
assert(::CALLS["DoIncludeScript:sourcebox_bridge"] == 1);
assert(!savedStarter.IsValid());
::PickerToggle();
assert(::g_sourcebox_picker.enabled);

// Quickload on the same map can restore an older VM without rerunning mapspawn.
delete getroottable().PickerToggle;
::QUEUE = [];
::Portal2ActivateMap();
::Advance(0.3);
assert(::CALLS["DoIncludeScript:sourcebox_bridge"] == 2);
assert(!::g_sourcebox_picker.enabled);
::PickerToggle();
assert(::g_sourcebox_picker.enabled);
print("PORTAL 2 SAVE RESTORE PASS\n");
'''
        result = _run_squirrel("\n".join(setup) + "\n" + scenario)
        output = result.stdout + result.stderr
        self.assertEqual(result.returncode, 0, output)
        self.assertNotIn("ERROR", output)
        self.assertIn("PORTAL 2 SAVE RESTORE PASS", output)


if __name__ == "__main__":
    unittest.main()
