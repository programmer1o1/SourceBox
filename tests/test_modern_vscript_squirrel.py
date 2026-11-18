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


def _scenario(branch):
    transport = BRANCHES[branch]["transport"]
    hook = BRANCHES[branch]["hook"][:-4]
    cmd_key = "sourcebox_command.txt" if transport == "file" else "sourcebox_command.nut"
    wrap = (lambda text: text) if transport == "file" else command_script
    with_original = branch == "portal2"

    lines = [
        f'::MOCK_BRANCH <- "{branch}";',
        'dofile("engine_mock.nut");',
        f'::FILES["sourcebox_bridge.nut"] <- {_verbatim(bridge_script(branch))};',
        f'::FILES["{hook}.nut"] <- {_verbatim(hook_script(with_original))};',
        f'::FILES["{cmd_key}"] <- {_verbatim(wrap(""))};',
    ]
    if with_original:
        lines.append('::FILES["sourcebox_original_mapspawn.nut"] <- @"printl(""original mapspawn"")";')
    lines += [
        'local show = function(tag) {',
        '    local s = "STEP " + tag;',
        '    foreach (p in ::PROPS) s += " | " + p.cls + " " + p.origin + " " + p.model + " " + p.tint;',
        '    print(s + "\\n");',
        '};',
        f'::RunFile("{hook}", getroottable());',
        '::Advance(2.0); show("before_autospawn");',
        '::Advance(2.0); show("autospawn");',
        f'::FILES["{cmd_key}"] <- {_verbatim(wrap(_command(SESSION_A, 1)))};',
        '::Advance(0.5); show("command");',
        '::Advance(1.0); show("command_again");',
        f'::FILES["{cmd_key}"] <- {_verbatim(wrap(_command(SESSION_B, 1)))};',
        '::Advance(0.5); show("new_session");',
        '::NewMap();',
        f'::RunFile("{hook}", getroottable());',
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
        '::Advance(1.5);',
        'local before_quit = polls();',
        'local not_found_before_quit = not_found();',
        f'::FILES["{cmd_key}"] <- {_verbatim(wrap("quit"))};',
        '::Advance(0.4);',
        f'delete ::FILES["{cmd_key}"];',
        '::Advance(3.0);',
        'print("POLLS_AFTER_QUIT " + (polls() - before_quit) + "\\n");',
        'print("NOT_FOUND_AFTER_QUIT " + (not_found() - not_found_before_quit) + "\\n");',
        'foreach (line in ::LOGS) print("LOG " + line + "\\n");',
    ]
    return "\n".join(lines) + "\n"


def _run(branch):
    with tempfile.TemporaryDirectory() as temp:
        shutil.copy(MOCK, temp)
        script = Path(temp) / "scenario.nut"
        script.write_text(_scenario(branch), encoding="utf-8", newline="\n")
        result = subprocess.run([SQUIRREL, script.name], cwd=temp, capture_output=True, text=True, timeout=60)
    if result.returncode != 0 or "ERROR" in result.stdout:
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
        'dofile("engine_mock.nut");',
        f'::FILES["sourcebox_bridge.nut"] <- {_verbatim(bridge_script(branch))};',
        f'::FILES["{hook}.nut"] <- {_verbatim(hook_script(False))};',
        f'::RunFile("{hook}", getroottable());',
        "::Advance(1.0);",
        'foreach (line in ::LOGS) print("LOG " + line + "\\n");',
    ]
    with tempfile.TemporaryDirectory() as temp:
        shutil.copy(MOCK, temp)
        script = Path(temp) / "client.nut"
        script.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
        result = subprocess.run([SQUIRREL, script.name], cwd=temp, capture_output=True, text=True, timeout=60)
    return result.returncode, result.stdout + result.stderr


def _position(prop):
    match = re.search(r"\(([-\d.]+) ([-\d.]+) ([-\d.]+)\)", prop)
    return tuple(float(v) for v in match.groups())


@unittest.skipUnless(SQUIRREL and os.path.isfile(SQUIRREL), "set SOURCEBOX_SQUIRREL to an sq interpreter")
class BridgeScriptRunTests(unittest.TestCase):
    def test_every_branch_runs_a_full_session(self):
        # L4D2 and Strata see the 30 degree downward look and hit the floor;
        # the others only know the body facing and spawn level, 200 units out
        expected_view_hit = {
            "l4d2": (110.9, 0.0, 10.0),
            "strata": (110.9, 0.0, 10.0),
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
                # one polling chain, about 10 checks a second over 5 seconds
                self.assertGreaterEqual(polls, 35)
                self.assertLessEqual(polls, 55)
                self.assertIn(f"[SourceBox] bridge loaded ({branch})", logs)
                # killed SourceBox, command file removed: one failed read, then quiet
                self.assertEqual(steps["polls_after_close"], 1)
                if branch != "l4d2":
                    self.assertEqual(steps["not_found_after_close"], 1)
                # normal close: the bridge reads "quit" and stops before the file goes
                self.assertEqual(steps["polls_after_quit"], 1)
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


if __name__ == "__main__":
    unittest.main()
