// SourceBox bridge for the newer VScript branches:
// Left 4 Dead 2, Portal 2, CS:GO, Alien Swarm and Strata Source (P2CE, Portal: Revolution).
//
// SourceBox writes two lines above this file when it installs it:
//   ::SOURCEBOX_BRANCH    "l4d2" | "portal2" | "csgo" | "swarm" | "strata"
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
::SOURCEBOX_POLL <- 0.1;
::SOURCEBOX_AUTOSPAWN_DELAY <- 3.0;
// MASK_SOLID, for Strata's TraceLineEx
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
    if (::SOURCEBOX_BRANCH == "strata") {
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

// cubes keep the model's own colours here (no tint, unlike the TF2-branch bridge)
::SourceBoxCreateProp <- function(model, position) {
    local prop = null;

    if (::SOURCEBOX_BRANCH == "l4d2") {
        try {
            PrecacheModel(model);
        } catch (e) {}
        try {
            prop = SpawnEntityFromTable("prop_physics_override", {
                origin = position,
                model = model
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

    if (prop == null) {
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

    local eye = ::SourceBoxEye(player);
    local hit = ::SourceBoxTrace(eye, eye + ::SourceBoxForward(player) * distance, player);
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
            ::SourceBoxLog("auto-spawned cube: " + ::SourceBoxDescribe(prop));
            ::SourceBoxWatch(prop);
            return true;
        }
    }
    return false;
}

// ---------------------------------------------------------------- polling

::SourceBoxTick <- function() {
    if (::g_sourcebox_stopped) {
        return;
    }
    local command = null;
    try {
        command = ::SourceBoxReadCommand();
    } catch (e) {}
    if (command == null || command == "quit") {
        // SourceBox closed: it sends "quit" first, and if it was killed instead
        // its files are simply gone. Either way, stop for the rest of this map.
        ::g_sourcebox_stopped <- true;
        ::SourceBoxLog("SourceBox closed, bridge stopped");
        return;
    }
    try {
        ::SourceBoxHandle(command);
    } catch (e) {}

    try {
        ::SourceBoxCheckWatch();
    } catch (e) {}

    if (!::g_sourcebox_autospawned && Time() >= ::g_sourcebox_autospawn_at) {
        ::g_sourcebox_autospawned <- true;
        try {
            ::SourceBoxAutoSpawn();
        } catch (e) {}
    }
}

::SourceBoxSchedule <- function(gen, delay) {
    local world = Entities.FindByClassname(null, "worldspawn");
    if (world != null) {
        EntFireByHandle(world, "RunScriptCode", "::SourceBoxPoll(" + gen + ")", delay, null, null);
    }
}

::SourceBoxPoll <- function(gen) {
    if (gen != ::g_sourcebox_gen) {
        return;
    }
    ::SourceBoxTick();
    if (!::g_sourcebox_stopped) {
        ::SourceBoxSchedule(gen, ::SOURCEBOX_POLL);
    }
}

::SourceBoxStart <- function() {
    ::g_sourcebox_autospawn_at <- Time() + ::SOURCEBOX_AUTOSPAWN_DELAY;

    if (::SOURCEBOX_BRANCH == "l4d2") {
        // L4D2 has no EntFireByHandle; a think function on worldspawn polls instead
        local world = Entities.FindByClassname(null, "worldspawn");
        if (world == null) {
            return;
        }
        world.ValidateScriptScope();
        world.GetScriptScope().SourceBoxThink <- function() {
            ::SourceBoxTick();
            // a think cannot be removed from here; once stopped it just idles
            return ::g_sourcebox_stopped ? 60.0 : ::SOURCEBOX_POLL;
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
