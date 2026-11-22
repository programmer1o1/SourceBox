// SourceBox bridge for the newer VScript branches:
// Left 4 Dead 2, Portal 2, CS:GO, Alien Swarm and Strata Source (P2CE, Portal: Revolution).
//
// SourceBox writes two lines above this file when it installs it:
//   ::SOURCEBOX_BRANCH    "l4d2" | "portal2" | "csgo" | "swarm" | "strata" | "revolution"
//   ::SOURCEBOX_TRANSPORT "file"    - commands arrive in ems/sourcebox_command.txt (L4D2)
//                         "include" - commands arrive as scripts/vscripts/sourcebox_command.nut
//
// Every engine call that only some branches have is wrapped in try/catch, so a
// missing function falls through to the next option instead of stopping the script.

// Some games (P2CE, for one) also run mapspawn.nut in their client-side script
// VM, which cannot spawn anything and has no Entities. The bridge belongs to the
// server VM only, so it leaves quietly here.
if (!("Entities" in getroottable())) {
    return;
}

::SOURCEBOX_MODEL <- "models/props/srcbox/srcbox.mdl";
::SOURCEBOX_USES_CUBE_TEMPLATE <- (::SOURCEBOX_BRANCH == "swarm" ||
    ::SOURCEBOX_BRANCH == "portal2" || ::SOURCEBOX_BRANCH == "csgo" || ::SOURCEBOX_BRANCH == "revolution");
::SOURCEBOX_POLL <- 0.1;
::SOURCEBOX_PICKER_POLL <- 0.02;
::SOURCEBOX_AUTOSPAWN_DELAY <- 3.0;
::SOURCEBOX_FORCE_SERVER_PHYSICS <- 8192;
// MASK_SOLID, for Strata traces
::SOURCEBOX_MASK_SOLID <- 33570827;

// a new generation per map load stops polls queued by an older load
if (!("g_sourcebox_gen" in getroottable())) {
    ::g_sourcebox_gen <- 0;
}
::g_sourcebox_gen <- ::g_sourcebox_gen + 1;

// the first command seen after a load is only remembered, never run, so a
// command left over from before the map change does not spawn again
::g_sourcebox_primed <- false;
::g_sourcebox_session <- "";
::g_sourcebox_last_id <- 0;
::g_sourcebox_command <- "";
::g_sourcebox_autospawned <- false;
::g_sourcebox_stopped <- false;
::g_sourcebox_autospawn_at <- 0.0;
::g_sourcebox_portal2_next_poll <- 0.0;
::g_sourcebox_picker_hud_at <- 0.0;
if (::SOURCEBOX_BRANCH == "portal2" && ("SourceBoxClearPortal2PickerHud" in getroottable())) {
    ::SourceBoxClearPortal2PickerHud();
}
::g_sourcebox_portal2_hud_visible <- false;

if (::SOURCEBOX_BRANCH == "csgo") {
    if ("g_sourcebox_csgo_timer" in getroottable() && ::g_sourcebox_csgo_timer != null &&
        ::g_sourcebox_csgo_timer.IsValid()) {
        ::g_sourcebox_csgo_timer.Destroy();
    }
    ::g_sourcebox_csgo_timer <- null;
    ::g_sourcebox_csgo_timer_attempted <- false;
    ::g_sourcebox_csgo_next_poll <- 0.0;
    ::g_sourcebox_csgo_round <- null;
    ::g_sourcebox_csgo_warmup <- null;
    ::g_sourcebox_csgo_auto_cube <- null;
}

::SourceBoxLog <- function(message) {
    try {
        printl("[SourceBox] " + message);
    } catch (e) {}
}

// ---------------------------------------------------------------- command input

// the command text, or null once the command file is gone: SourceBox deletes
// it when it closes, and the bridge then stops polling
::SourceBoxReadCommand <- function() {
    if (::SOURCEBOX_TRANSPORT == "file") {
        local text = null;
        try {
            text = FileToString("sourcebox_command.txt");
        } catch (e) {}
        return text;
    }

    // the command file always sets this to a string, so if it is still null
    // afterwards the file is gone. DoIncludeScript's own result can't be used:
    // P2CE reports success even when the script is missing.
    ::g_sourcebox_command <- null;
    try {
        DoIncludeScript("sourcebox_command", getroottable());
    } catch (e) {}
    return ::g_sourcebox_command;
}

::SourceBoxRespond <- function(status, message) {
    if (::SOURCEBOX_TRANSPORT == "file") {
        try {
            StringToFile("sourcebox_response.txt",
                "{\"status\":\"" + status + "\",\"message\":\"" + message + "\"}");
            return;
        } catch (e) {}
    }
    ::SourceBoxLog(status + ": " + message);
}

::SourceBoxString <- function(json, key) {
    local key_str = "\"" + key + "\"";
    local key_pos = json.find(key_str);
    if (key_pos == null) {
        return null;
    }
    local start = json.find("\"", key_pos + key_str.len());
    if (start == null) {
        return null;
    }
    start++;
    local finish = json.find("\"", start);
    if (finish == null) {
        return null;
    }
    return json.slice(start, finish);
}

// the raw text of a numeric value; the session id is compared as text because
// it does not fit the 32-bit integers of Portal 2, L4D2, CS:GO and Alien Swarm
::SourceBoxRaw <- function(json, key) {
    local key_str = "\"" + key + "\":";
    local key_pos = json.find(key_str);
    if (key_pos == null) {
        return "";
    }
    local start = key_pos + key_str.len();
    local finish = start;
    while (finish < json.len()) {
        local ch = json.slice(finish, finish + 1);
        if (ch == "," || ch == "}" || ch == " ") {
            break;
        }
        finish++;
    }
    return json.slice(start, finish);
}

::SourceBoxNumber <- function(json, key) {
    local raw = ::SourceBoxRaw(json, key);
    if (raw.len() == 0) {
        return 0;
    }
    try {
        return raw.tointeger();
    } catch (e) {}
    return 0;
}

::SourceBoxHandle <- function(json) {
    local session = "";
    local id = 0;
    if (json != null && json.len() > 0) {
        session = ::SourceBoxRaw(json, "session");
        id = ::SourceBoxNumber(json, "id");
    }

    if (!::g_sourcebox_primed) {
        ::g_sourcebox_primed <- true;
        ::g_sourcebox_session <- session;
        ::g_sourcebox_last_id <- id;
        return;
    }

    if (session.len() == 0 || id <= 0) {
        return;
    }
    if (session != ::g_sourcebox_session) {
        ::g_sourcebox_session <- session;
        ::g_sourcebox_last_id <- 0;
    }
    if (id <= ::g_sourcebox_last_id) {
        return;
    }
    ::g_sourcebox_last_id <- id;

    local command = ::SourceBoxString(json, "command");
    if (command == "spawn_model") {
        local model = ::SourceBoxString(json, "model");
        local distance = ::SourceBoxNumber(json, "distance");
        if (distance <= 0) {
            distance = 200;
        }
        if (model == null || model.len() == 0) {
            ::SourceBoxRespond("error", "no model specified");
            return;
        }
        ::SourceBoxSpawnAtView(model, distance);
    } else {
        ::SourceBoxRespond("error", "unknown command");
    }
}

// ---------------------------------------------------------------- player and view

::SourceBoxPickerHud <- function(player, clear = false) {
    local now = Time();
    if (!clear && (::g_sourcebox_portal2_hud_visible || now < ::g_sourcebox_picker_hud_at)) {
        return;
    }
    ::g_sourcebox_picker_hud_at = now + 0.5;
    local settings = {
        message = "PICKER ON", channel = 1, x = -1, y = 0.53,
        color = "255 160 0 255", color2 = "255 160 0 255",
        effect = 0, fadein = 0, fadeout = 0, holdtime = 0.65, spawnflags = 0
    };
    if (::SOURCEBOX_BRANCH == "portal2") {
        // A single message avoids overlapping draws during HUD refreshes.
        // Clear it by replacing the same channel when Picker stops.
        settings.channel = 5;
        settings.message = clear ? " " : "PICKER ON";
        settings.holdtime = clear ? 0.0 : 86400.0;
    }
    try {
        local text = Entities.CreateByClassname("game_text");
        if (text != null) {
            foreach (key, value in settings) {
                text.__KeyValueFromString(key, value.tostring());
            }
            EntFireByHandle(text, "Display", "", 0.0, player, null);
            ::g_sourcebox_portal2_hud_visible = ::SOURCEBOX_BRANCH == "portal2" && !clear;
            EntFireByHandle(text, "Kill", "", 0.05, null, null);
        }
    } catch (error) {
        ::g_sourcebox_picker_hud_at = now + 2.0;
    }
}

::SourceBoxClearPortal2PickerHud <- function() {
    if (!::g_sourcebox_portal2_hud_visible) {
        return;
    }
    try {
        local player = GetPlayer();
        if (player != null && player.IsValid()) {
            ::SourceBoxPickerHud(player, true);
        }
    } catch (error) {}
    ::g_sourcebox_portal2_hud_visible = false;
}

::SourceBoxSmoothPickerAim <- function(picker, player, delta) {
    local pitch = atan2(-delta.z, sqrt(delta.x * delta.x + delta.y * delta.y)) * 57.2957795;
    local yaw = atan2(delta.y, delta.x) * 57.2957795;
    local now = Time();
    if (picker.angles == null) {
        local forward = player.GetForwardVector();
        local horizontal = sqrt(forward.x * forward.x + forward.y * forward.y);
        picker.angles = Vector(atan2(-forward.z, horizontal) * 57.2957795,
            atan2(forward.y, forward.x) * 57.2957795, 0);
        picker.updated = now - ::SOURCEBOX_PICKER_POLL;
    }
    local current = picker.angles;
    local elapsed = now - picker.updated;
    if (elapsed > 0.05) elapsed = 0.05;
    local blend = 1.0 - pow(0.5, elapsed / 0.08);
    local deltaYaw = yaw - current.y;
    while (deltaYaw > 180.0) deltaYaw -= 360.0;
    while (deltaYaw < -180.0) deltaYaw += 360.0;
    local newYaw = current.y + deltaYaw * blend;
    if (newYaw > 180.0) newYaw -= 360.0;
    if (newYaw < -180.0) newYaw += 360.0;
    picker.angles = Vector(current.x + (pitch - current.x) * blend, newYaw, 0);
    picker.updated = now;
    SendToConsole(format("setang %.4f %.4f", picker.angles.x, picker.angles.y));
}

::SourceBoxPlayer <- function() {
    local player = null;
    if (::SOURCEBOX_BRANCH == "swarm") {
        // Alien Swarm is top-down: use the first marine as "the player"
        try {
            player = Entities.FindByClassname(null, "asw_marine");
        } catch (e) {}
        if (player != null) {
            return player;
        }
    }
    try {
        player = GetPlayer();
    } catch (e) {}
    if (player == null) {
        try {
            player = GetListenServerHost();
        } catch (e) {}
    }
    if (player == null) {
        try {
            player = PlayerInstanceFromIndex(1);
        } catch (e) {}
    }
    if (player == null) {
        try {
            player = Entities.FindByClassname(null, "player");
        } catch (e) {}
    }
    return player;
}

::SourceBoxEye <- function(player) {
    try {
        return player.EyePosition();
    } catch (e) {}
    return player.GetOrigin() + Vector(0, 0, 64);
}

::SourceBoxForward <- function(player) {
    // L4D2 and Strata expose the view angles; the others only the body facing
    local angles = null;
    try {
        angles = player.EyeAngles();
    } catch (e) {}
    if (angles != null) {
        local pitch = angles.x * 0.0174533;
        local yaw = angles.y * 0.0174533;
        return Vector(cos(yaw) * cos(pitch), sin(yaw) * cos(pitch), -sin(pitch));
    }
    try {
        return player.GetForwardVector();
    } catch (e) {}
    return Vector(1, 0, 0);
}

// returns the first solid point on the line, or end if nothing is in the way
::SourceBoxTrace <- function(start, end, ignore) {
    if (::SOURCEBOX_BRANCH == "l4d2") {
        try {
            local trace = { start = start, end = end, ignore = ignore };
            TraceLine(trace);
            if ("pos" in trace) {
                return trace.pos;
            }
            return end;
        } catch (e) {}
    }
    if (::SOURCEBOX_BRANCH == "strata" || ::SOURCEBOX_BRANCH == "revolution") {
        try {
            local result = TraceLineEx(start, end, ::SOURCEBOX_MASK_SOLID, ignore, 0);
            return result.GetEndPos();
        } catch (e) {}
    }
    try {
        local fraction = TraceLine(start, end, ignore);
        return start + (end - start) * fraction;
    } catch (e) {}
    return end;
}

// ---------------------------------------------------------------- spawning

::SourceBoxRevolutionCubeIsPrecached <- function() {
    local prop = Entities.FindByName(null, "sourcebox_cube_precache");
    return prop != null && prop.IsValid() && prop.GetModelName() == ::SOURCEBOX_MODEL;
}

::SourceBoxSpawnProblem <- function(model) {
    if (::SOURCEBOX_BRANCH == "l4d2") {
        try {
            if (IsModelPrecached(model)) {
                return null;
            }
            local world = Entities.FindByClassname(null, "worldspawn");
            if (world != null && world.PrecacheModel(model) > 0 && IsModelPrecached(model)) {
                return null;
            }
        } catch (e) {}
        return "model not precached on this map: " + model;
    }

    if (!::SOURCEBOX_USES_CUBE_TEMPLATE) {
        return null;
    }

    if (model == ::SOURCEBOX_MODEL) {
        if (Entities.FindByName(null, "sourcebox_cube_maker") != null) {
            return null;
        }
        if (::SOURCEBOX_BRANCH == "revolution" && ::SourceBoxRevolutionCubeIsPrecached()) {
            return null;
        }
        if (::SOURCEBOX_BRANCH == "csgo") {
            return "custom cube template unavailable; load a map with Stripper:Source active or use a SourceBox-prepared map";
        }
        return "custom cube template unavailable; load a fresh supported map";
    }

    // Keep the precache check for commands that request a different model.
    try {
        local existing = Entities.FindByModel(null, model);
        if (existing != null && existing.GetModelName() == model) {
            return null;
        }
    } catch (e) {}
    return "model not precached on this map: " + model;
}

::SourceBoxCreateTemplateCube <- function(position) {
    try {
        local maker = Entities.FindByName(null, "sourcebox_cube_maker");
        if (maker == null) {
            return null;
        }

        // The maker spawns synchronously and returns no handle. Its template
        // preserves the cube name so we can identify the new instance.
        local existing = {};
        local cube = null;
        while ((cube = Entities.FindByName(cube, "sourcebox_cube_prop")) != null) {
            existing[cube] <- true;
        }
        maker.SpawnEntityAtLocation(position, Vector(0, 0, 0));
        while ((cube = Entities.FindByName(cube, "sourcebox_cube_prop")) != null) {
            if (!(cube in existing) && cube.GetModelName() == ::SOURCEBOX_MODEL) {
                return cube;
            }
        }
    } catch (e) {
        ::SourceBoxLog("could not spawn physics cube: " + e);
    }
    return null;
}

// cubes keep the model's own colours here (no tint, unlike the TF2-branch bridge)
::SourceBoxCreateProp <- function(model, position) {
    if (::SOURCEBOX_USES_CUBE_TEMPLATE && model == ::SOURCEBOX_MODEL) {
        local cube = ::SourceBoxCreateTemplateCube(position);
        if (cube != null || ::SOURCEBOX_BRANCH != "revolution" || !::SourceBoxRevolutionCubeIsPrecached()) {
            return cube;
        }
        try {
            cube = CreateEntityByName("prop_physics_override", {
                model = model, spawnflags = ::SOURCEBOX_FORCE_SERVER_PHYSICS
            });
        } catch (e) {}
        if (cube != null) {
            ::SourceBoxPlace(cube, position);
        }
        return cube;
    }
    local prop = null;

    if (::SOURCEBOX_BRANCH == "l4d2") {
        try {
            prop = SpawnEntityFromTable("prop_physics_override", {
                origin = position,
                model = model,
                spawnflags = ::SOURCEBOX_FORCE_SERVER_PHYSICS
            });
        } catch (e) {}
    }

    if (prop == null && ::SOURCEBOX_BRANCH == "strata") {
        try {
            Entities.FindByClassname(null, "worldspawn").PrecacheModel(model);
        } catch (e) {}
        try {
            prop = CreateEntityByName("prop_physics_override", {
                origin = "" + position.x + " " + position.y + " " + position.z,
                model = model
            });
        } catch (e) {}
    }

    if (prop == null && ::SOURCEBOX_BRANCH != "l4d2") {
        try {
            PrecacheModel(model);
        } catch (e) {}
        foreach (classname in ["prop_physics_override", "prop_physics", "prop_dynamic_override"]) {
            try {
                prop = CreateProp(classname, position, model, 0);
            } catch (e) {}
            if (prop != null) {
                break;
            }
        }
    }

    if (prop != null) {
        ::SourceBoxPlace(prop, position);
    }
    return prop;
}

// P2CE's CreateEntityByName ignores the origin keyvalue and spawns at the map
// origin, so any prop that is not where it was asked to be is moved there.
// Teleport moves the physics object too; SetOrigin is the fallback.
::SourceBoxPlace <- function(prop, position) {
    local current = null;
    try {
        current = prop.GetOrigin();
    } catch (e) {}
    if (current != null && (current - position).Length() < 1.0) {
        return;
    }
    try {
        prop.Teleport(position, Vector(0, 0, 0));
        return;
    } catch (e) {}
    try {
        prop.SetOrigin(position);
    } catch (e) {}
}

// "prop_physics_override at (110 0 10) model models/props/srcbox/srcbox.mdl"
::SourceBoxDescribe <- function(prop) {
    local text = "";
    try {
        text += prop.GetClassname();
    } catch (e) {}
    try {
        local o = prop.GetOrigin();
        text += " at (" + o.x.tointeger() + " " + o.y.tointeger() + " " + o.z.tointeger() + ")";
    } catch (e) {}
    try {
        text += " model " + prop.GetModelName();
    } catch (e) {}
    return text;
}

// report where a new cube is a second later, so a cube that fell out of the
// world or was removed straight away shows up in the console
::g_sourcebox_watch <- null;
::SourceBoxWatch <- function(prop) {
    ::g_sourcebox_watch <- { prop = prop, at = Time() + 1.0 };
}

::SourceBoxCheckWatch <- function() {
    local watch = ::g_sourcebox_watch;
    if (watch == null || Time() < watch.at) {
        return;
    }
    ::g_sourcebox_watch <- null;
    local where = ::SourceBoxDescribe(watch.prop);
    if (where.len() == 0) {
        where = "gone (the game removed it)";
    }
    ::SourceBoxLog("cube after 1s: " + where);
}

::SourceBoxSpawnAtView <- function(model, distance) {
    if (model.find("models/") != 0) {
        model = "models/" + model;
    }

    local player = ::SourceBoxPlayer();
    if (player == null) {
        ::SourceBoxRespond("error", "no player");
        return;
    }

    local problem = ::SourceBoxSpawnProblem(model);
    if (problem != null) {
        ::SourceBoxRespond("error", problem);
        return;
    }
    local eye = ::SourceBoxEye(player);
    local forward = ::SourceBoxForward(player);
    local end = eye + forward * distance;
    local hit = ::SourceBoxTrace(eye, end, player);
    if ((::SOURCEBOX_USES_CUBE_TEMPLATE || ::SOURCEBOX_BRANCH == "l4d2") &&
        model == ::SOURCEBOX_MODEL && (end - hit).Length() > 1.0) {
        // Leave room for the cube's collision hull when the trace hits a wall.
        if ((hit - eye).Length() <= 12.0) {
            ::SourceBoxRespond("error", "no room to spawn the cube");
            return;
        }
        hit = hit - forward * 12.0;
    }
    local prop = ::SourceBoxCreateProp(model, hit + Vector(0, 0, 10));

    if (prop != null) {
        ::SourceBoxRespond("spawned", ::SourceBoxDescribe(prop));
        ::SourceBoxWatch(prop);
    } else {
        ::SourceBoxRespond("error", "spawn failed - invalid model or missing asset");
    }
}

// one cube per map, somewhere near the player that they can see
::SourceBoxAutoSpawn <- function() {
    local player = ::SourceBoxPlayer();
    if (player == null) {
        return false;
    }
    local problem = ::SourceBoxSpawnProblem(::SOURCEBOX_MODEL);
    if (problem != null) {
        ::SourceBoxLog("auto-spawn skipped: " + problem);
        return false;
    }
    local eye = ::SourceBoxEye(player);
    local feet = player.GetOrigin();

    for (local attempt = 0; attempt < 12; attempt++) {
        local angle = RandomFloat(0.0, 6.2832);
        local radius = RandomFloat(128.0, 512.0);
        local above = feet + Vector(cos(angle) * radius, sin(angle) * radius, 64);

        // skip spots behind walls
        if ((::SourceBoxTrace(eye, above, player) - above).Length() > 1.0) {
            continue;
        }

        local ground = ::SourceBoxTrace(above, above - Vector(0, 0, 1024), player);
        local prop = ::SourceBoxCreateProp(::SOURCEBOX_MODEL, ground + Vector(0, 0, 16));
        if (prop != null) {
            if (::SOURCEBOX_BRANCH == "csgo") {
                ::g_sourcebox_csgo_auto_cube = prop;
            }
            ::SourceBoxLog("auto-spawned cube: " + ::SourceBoxDescribe(prop));
            ::SourceBoxWatch(prop);
            return true;
        }
    }
    return false;
}

// ---------------------------------------------------------------- polling

::SourceBoxCSGOCheckRound <- function() {
    local round = ScriptGetRoundsPlayed();
    local warmup = ScriptIsWarmupPeriod();
    local cube = ::g_sourcebox_csgo_auto_cube;
    if (::g_sourcebox_csgo_round != null &&
        (round != ::g_sourcebox_csgo_round || warmup != ::g_sourcebox_csgo_warmup) &&
        cube != null && !cube.IsValid()) {
        ::g_sourcebox_csgo_auto_cube = null;
        ::g_sourcebox_autospawned = false;
        ::g_sourcebox_autospawn_at = Time() + 1.0;
    }
    ::g_sourcebox_csgo_round = round;
    ::g_sourcebox_csgo_warmup = warmup;
}

::SourceBoxCSGOStartTimer <- function() {
    ::g_sourcebox_csgo_timer_attempted = true;
    local timer = null;
    try {
        timer = Entities.CreateByClassname("logic_timer");
        if (timer == null) {
            throw "logic_timer unavailable";
        }
        // CS:GO keeps soundent entities across round cleanup. The native timer
        // keeps thinking even when the game's queued I/O events are discarded.
        if (!timer.__KeyValueFromString("classname", "soundent")) {
            throw "could not preserve the timer";
        }
        timer.__KeyValueFromFloat("RefireTime", ::SOURCEBOX_PICKER_POLL);
        timer.ValidateScriptScope();
        timer.GetScriptScope().SourceBoxTimerTick <- function() {
            local now = Time();
            if (now >= ::g_sourcebox_csgo_next_poll) {
                ::SourceBoxTick();
                ::g_sourcebox_csgo_next_poll = now + ::SOURCEBOX_POLL;
            }
            if (::g_sourcebox_stopped) {
                self.Destroy();
            } else {
                ::SourceBoxCSGOPickerThink();
            }
        };
        timer.ConnectOutput("OnTimer", "SourceBoxTimerTick");
        EntFireByHandle(timer, "Enable", "", 0.0, null, null);
        ::g_sourcebox_csgo_timer = timer;
        return true;
    } catch (error) {
        if (timer != null && timer.IsValid()) {
            timer.Destroy();
        }
        ::SourceBoxLog("could not start the CS:GO round timer: " + error);
        return false;
    }
}

::SourceBoxTick <- function() {
    if (::g_sourcebox_stopped && ::SOURCEBOX_BRANCH != "l4d2") {
        return;
    }
    local command = null;
    try {
        command = ::SourceBoxReadCommand();
    } catch (e) {}
    if (command == null || command == "quit") {
        if (!::g_sourcebox_stopped) {
            ::g_sourcebox_stopped <- true;
            if (::SOURCEBOX_BRANCH == "portal2") {
                ::SourceBoxClearPortal2PickerHud();
            }
            if (::SOURCEBOX_BRANCH == "l4d2" || ::SOURCEBOX_BRANCH == "portal2" || ::SOURCEBOX_BRANCH == "csgo") {
                ::g_sourcebox_picker.enabled = false;
                ::g_sourcebox_picker.target = null;
            }
            ::SourceBoxLog("SourceBox closed, bridge stopped");
        }
        return;
    }
    if (::g_sourcebox_stopped) {
        ::g_sourcebox_stopped <- false;
        ::SourceBoxLog("SourceBox reconnected");
    }
    try {
        ::SourceBoxHandle(command);
    } catch (e) {}

    try {
        ::SourceBoxCheckWatch();
    } catch (e) {}

    if (::SOURCEBOX_BRANCH == "csgo") {
        try {
            ::SourceBoxCSGOCheckRound();
        } catch (e) {}
    }

    if (!::g_sourcebox_autospawned && Time() >= ::g_sourcebox_autospawn_at) {
        ::g_sourcebox_autospawned <- true;
        try {
            ::SourceBoxAutoSpawn();
        } catch (e) {}
    }
}

::SourceBoxSchedule <- function(gen, delay) {
    local world = Entities.FindByClassname(null, "worldspawn");
    local code = "::SourceBoxPoll(" + gen + ")";
    if (world != null) {
        EntFireByHandle(world, "RunScriptCode", code, delay, null, null);
    } else if (::SOURCEBOX_BRANCH == "csgo" || ::SOURCEBOX_BRANCH == "portal2" || ::SOURCEBOX_BRANCH == "revolution") {
        // mapspawn can run before worldspawn is available to scripts.
        // Resolve the target when the event fires.
        DoEntFire("worldspawn", "RunScriptCode", code, delay, null, null);
    }
}

::SourceBoxPoll <- function(gen) {
    if (gen != ::g_sourcebox_gen) {
        return;
    }
    if (::SOURCEBOX_BRANCH == "csgo" && !::g_sourcebox_csgo_timer_attempted &&
        ::SourceBoxCSGOStartTimer()) {
        return;
    }
    local delay = ::SOURCEBOX_POLL;
    local now = Time();
    if (::SOURCEBOX_BRANCH != "portal2" || now >= ::g_sourcebox_portal2_next_poll) {
        ::SourceBoxTick();
        ::g_sourcebox_portal2_next_poll = now + ::SOURCEBOX_POLL;
    }
    if (!::g_sourcebox_stopped) {
        if (::SOURCEBOX_BRANCH == "portal2") {
            ::SourceBoxPortal2PickerThink();
            if (::g_sourcebox_picker.enabled) {
                delay = ::SOURCEBOX_PICKER_POLL;
            }
        } else if (::SOURCEBOX_BRANCH == "csgo") {
            ::SourceBoxCSGOPickerThink();
        }
        ::SourceBoxSchedule(gen, delay);
    }
}

::SourceBoxStart <- function() {
    ::g_sourcebox_autospawn_at <- Time() + ::SOURCEBOX_AUTOSPAWN_DELAY;

    if (::SOURCEBOX_BRANCH == "portal2") {
        local first = Entities.FindByName(null, "sourcebox_portal2_activate");
        if (first != null) {
            local extra = Entities.FindByName(first, "sourcebox_portal2_activate");
            while (extra != null) {
                local next = Entities.FindByName(extra, "sourcebox_portal2_activate");
                EntFireByHandle(extra, "Kill", "", 0.0, null, null);
                extra = next;
            }
        }
    }

    if (::SOURCEBOX_BRANCH == "l4d2") {
        // L4D2 has no EntFireByHandle; a think function on worldspawn polls instead
        local world = Entities.FindByClassname(null, "worldspawn");
        if (world == null) {
            return;
        }
        world.ValidateScriptScope();
        local nextPoll = 0.0;
        world.GetScriptScope().SourceBoxThink <- function() {
            local now = Time();
            if (now >= nextPoll) {
                ::SourceBoxTick();
                nextPoll = now + ::SOURCEBOX_POLL;
            }
            if (::g_sourcebox_stopped) {
                // FileToString can quietly check for a restarted SourceBox.
                return 1.0;
            }
            // Keep file polling at its usual rate while updating the aim more often.
            return ::SourceBoxL4D2PickerThink(now) ? 0.03 : ::SOURCEBOX_POLL;
        };
        AddThinkToEnt(world, "SourceBoxThink");
    } else {
        ::SourceBoxSchedule(::g_sourcebox_gen, 1.0);
    }
    ::SourceBoxLog("bridge loaded (" + ::SOURCEBOX_BRANCH + ")");
}

try {
    ::SourceBoxStart();
} catch (e) {
    ::SourceBoxLog("bridge failed to start: " + e);
}
