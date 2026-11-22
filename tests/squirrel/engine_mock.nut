// Stand-in for the VScript engine API of one branch, set by ::MOCK_BRANCH, used by
// tests/test_modern_vscript_squirrel.py. Functions a branch does not have are not
// defined (or throw, for methods), the way calling them fails in the real game.
// World: a flat floor at z = 0. The player stands at the origin.

local B = ::MOCK_BRANCH;
local uses_cube_template = (B == "swarm" || B == "portal2" || B == "csgo" || B == "revolution");
::NOW <- 0.0;
::QUEUE <- [];
::THINKS <- [];
::PROPS <- [];
::FILES <- {};
::LOGS <- [];
::PRECACHED <- [];
::WORLD_SPAWNED <- true;
::CALLS <- {};

::Count <- function(name) {
    if (!(name in ::CALLS)) ::CALLS[name] <- 0;
    ::CALLS[name] += 1;
}

class Vector {
    x = 0.0; y = 0.0; z = 0.0;
    constructor(a = 0, b = 0, c = 0) { x = a.tofloat(); y = b.tofloat(); z = c.tofloat(); }
    function _add(o) { return Vector(x + o.x, y + o.y, z + o.z); }
    function _sub(o) { return Vector(x - o.x, y - o.y, z - o.z); }
    function _mul(s) { return Vector(x * s, y * s, z * s); }
    function Length() { return sqrt(x * x + y * y + z * z); }
    function _tostring() { return format("(%.1f %.1f %.1f)", x, y, z); }
}
::QAngle <- Vector;

::HAS_EYEANGLES <- (B == "l4d2" || B == "strata" || B == "revolution");

class Ent {
    cls = null; origin = null; scope = null; kv = null; tint = null; model = null;
    team = 2; health = 100; valid = true; ghost = false; incapacitated = false;
    index = 0; aim = null; outputFunction = null;
    constructor(c, o) { cls = c; origin = o; kv = {}; }
    function GetOrigin() { return origin; }
    function GetClassname() { return cls; }
    function GetModelName() { return model == null ? "" : model; }
    function IsValid() { return valid; }
    function GetCenter() { return origin; }
    function GetHealth() { return health; }
    function GetTeam() {
        if (::MOCK_BRANCH == "l4d2") throw "the index 'GetTeam' does not exist";
        return team;
    }
    function IsDead() { return health <= 0; }
    function IsDying() { return false; }
    function IsGhost() { return ghost; }
    function IsIncapacitated() { return incapacitated; }
    function IsHangingFromLedge() { return false; }
    function SetOrigin(o) { origin = o; }
    function Teleport(o, angles) {
        if (::MOCK_BRANCH != "strata") throw "the index 'Teleport' does not exist";
        ::Count("Teleport");
        origin = o;
    }
    function EyePosition() { return origin + Vector(0, 0, 64); }
    function EyeAngles() {
        if (!::HAS_EYEANGLES) throw "the index 'EyeAngles' does not exist";
        return aim == null ? Vector(30, 0, 0) : aim;
    }
    function SnapEyeAngles(angles) { ::Count("SnapEyeAngles"); aim = angles; }
    function GetForwardVector() { return Vector(1, 0, 0); }
    function ValidateScriptScope() { if (scope == null) scope = {}; return true; }
    function GetScriptScope() { return scope; }
    function __KeyValueFromString(k, v) {
        kv[k] <- v;
        if (k == "classname") cls = v;
        return true;
    }
    function __KeyValueFromFloat(k, v) { kv[k] <- v; return true; }
    function ConnectOutput(output, name) { outputFunction = name; }
    function Destroy() { valid = false; }
    function PrecacheModel(m) {
        if (::MOCK_BRANCH != "strata" && ::MOCK_BRANCH != "l4d2" && ::MOCK_BRANCH != "csgo") {
            throw "the index 'PrecacheModel' does not exist";
        }
        ::Count("PrecacheModel");
        if (::MOCK_BRANCH == "l4d2" && !::MOCK_L4D2_PRECACHE) return 0;
        ::PRECACHED.append(m);
        if (::MOCK_BRANCH == "csgo") return;
        return 1;
    }
}

::WORLD <- Ent("worldspawn", Vector(0, 0, 0));
::PLAYER <- Ent(B == "swarm" ? "asw_marine" : "player", Vector(0, 0, 0));

::PickerHudInput <- function(text, action, player) {
    if (action == "Display") {
        assert(text.IsValid() && player == ::PLAYER);
        if (::MOCK_BRANCH == "portal2") {
            assert(text.kv.channel.tointeger() == 5);
            if (text.kv.message == " ") {
                assert(text.kv.holdtime.tointeger() == 0);
                ::Count("PickerHudClear");
                return;
            }
            assert(text.kv.holdtime.tofloat() > 10.0);
        }
        assert(text.kv.message == "PICKER ON" && text.kv.x.tostring() == "-1");
        assert(fabs(text.kv.y.tofloat() - 0.53) < 0.001);
        assert(text.kv.color == "255 160 0 255" && text.kv.spawnflags.tointeger() == 0);
        ::Count("PickerHudDisplay");
    } else if (action == "Kill") {
        text.Destroy();
    }
};

::Entities <- {
    FindByClassname = function(prev, cls) {
        if (prev != null) return null;
        if (cls == "worldspawn") return ::WORLD_SPAWNED ? ::WORLD : null;
        if (cls == ::PLAYER.cls) return ::PLAYER;
        return null;
    }
};

if (uses_cube_template) {
    ::MAP_PROP <- Ent("prop_dynamic_override", Vector(0, 0, 0));
    ::MAP_PROP.model = ::MOCK_MAP_MODEL;
    ::Entities.FindByModel <- function(prev, model) {
        return ::MAP_PROP.model == model ? ::MAP_PROP : null;
    };
    ::MAP_CUBE_MAKER <- {
        SpawnEntityAtLocation = function(position, angles) {
            ::Count("SpawnEntityAtLocation");
            local cube = ::MakeProp("prop_physics_override", position, ::MOCK_MAP_MODEL);
            cube.__KeyValueFromString("targetname", "sourcebox_cube_prop");
        }
    };
    ::Entities.FindByName <- function(prev, name) {
        if (name == "sourcebox_cube_maker") {
            return ::MOCK_HAS_CUBE_MAKER && prev == null ? ::MAP_CUBE_MAKER : null;
        }
        if (::MOCK_BRANCH == "revolution" && name == "sourcebox_cube_precache") {
            local prop = ::REVOLUTION_CUBE_REFERENCE;
            return prev == null && prop != null && prop.kv.targetname == name ? prop : null;
        }
        if (::MOCK_BRANCH == "portal2" && name.find("sourcebox_portal2_") == 0) {
            local after_previous = prev == null;
            foreach (starter in ::PORTAL2_STARTERS) {
                if (after_previous && starter.IsValid() && starter.kv.targetname == name) return starter;
                if (starter == prev) after_previous = true;
            }
            return null;
        }
        local after_previous = prev == null;
        foreach (prop in ::PROPS) {
            if (after_previous && ("targetname" in prop.kv) && prop.kv.targetname == name) {
                return prop;
            }
            if (prop == prev) {
                after_previous = true;
            }
        }
        return null;
    };
}

::Time <- function() { return ::NOW; }
::RandomFloat <- function(lo, hi) { return lo + (hi - lo) * 0.25; }
::printl <- function(s) { ::LOGS.append(s); }

// a line against the floor: the fraction of the way to z = 0, or 1
::FloorFraction <- function(start, end) {
    if (end.z >= 0 || start.z < 0) return 1.0;
    return start.z / (start.z - end.z);
}

::MakeProp <- function(cls, pos, model) {
    local e = Ent(cls, pos);
    e.model = model;
    ::PROPS.append(e);
    return e;
}

// ---- functions per branch

if (B == "l4d2") {
    ::PLAYER.index = 1;
    ::PICKER_HOST_AVAILABLE <- true;
    ::PICKER_TARGETS <- [];
    ::PICKER_BLOCKED_POSITIONS <- [];
    ::PICKER_CHAT_MESSAGES <- [];
    ::GameEventCallbacks <- {};
    ::NetProps <- {
        GetPropInt = function(entity, name) {
            if (name != "m_iTeamNum") throw "unexpected netprop";
            return entity.team;
        }
    };
    ::ClientPrint <- function(player, destination, message) {
        assert(player == ::PLAYER && destination == 3);
        ::PICKER_CHAT_MESSAGES.append(message);
    };
    ::RegisterScriptGameEventListener <- function(name) {};
    ::__CollectEventCallbacks <- function(scope, prefix, channel, register) {
        local callbacks = getroottable()[channel];
        foreach (key, callback in scope) {
            if (key.find(prefix) != 0) continue;
            local eventName = key.slice(prefix.len());
            if (!(eventName in callbacks)) {
                callbacks[eventName] <- [];
                register(eventName);
            }
            if (callbacks[eventName].find(scope) == null) {
                callbacks[eventName].append(scope.weakref());
            }
        }
    };
    ::GetListenServerHost <- function() { return ::PICKER_HOST_AVAILABLE ? ::PLAYER : null; };
    ::GetPlayerFromUserID <- function(userID) { return userID == ::PLAYER.index ? ::PLAYER : null; };
    ::Entities.FindByClassnameWithin <- function(prev, classname, origin, radius) {
        local passed = prev == null;
        foreach (target in ::PICKER_TARGETS) {
            if (passed && target.cls == classname && (target.origin - origin).Length() <= radius) return target;
            if (target == prev) passed = true;
        }
        return null;
    };
    ::DebugDrawBox <- function(origin, mins, maxs, r, g, b, alpha, duration) {
        Count("DebugDrawBox");
    };
    ::FileToString <- function(name) { Count("FileToString"); return (name in ::FILES) ? ::FILES[name] : null; };
    ::StringToFile <- function(name, text) { ::FILES[name] <- text; };
    ::IsModelPrecached <- function(m) { return ::PRECACHED.find(m) != null; };
    ::SpawnEntityFromTable <- function(cls, t) {
        Count("SpawnEntityFromTable");
        if (!::IsModelPrecached(t.model) || cls != "prop_physics_override" || t.spawnflags != 8192) {
            print("ERROR: invalid L4D2 physics spawn\n");
            return null;
        }
        if (!::MOCK_L4D2_SPAWN) return null;
        local e = ::MakeProp(cls, t.origin, t.model);
        if ("rendercolor" in t) e.tint = t.rendercolor;
        return e;
    };
    ::CreateProp <- function(cls, pos, model, activity) {
        Count("CreateProp");
        return ::MakeProp(cls, pos, model);
    };
    ::TraceLine <- function(t) {
        foreach (position in ::PICKER_BLOCKED_POSITIONS) {
            if ((t.end - position).Length() < 0.1) {
                t.hit <- true;
                t.pos <- t.start + (t.end - t.start) * 0.5;
                return true;
            }
        }
        foreach (target in ::PICKER_TARGETS) {
            if (target == t.ignore || (target.cls != "player" && target.cls != "infected" && target.cls != "witch")) continue;
            if ((t.end - target.GetCenter()).Length() < 0.1 || (t.end - target.EyePosition()).Length() < 0.1) {
                t.hit <- true;
                t.enthit <- t.mask == 1174421507 ? target : ::WORLD;
                t.pos <- t.end;
                return true;
            }
        }
        local f = ::FloorFraction(t.start, t.end);
        t.pos <- t.start + (t.end - t.start) * f;
        t.hit <- f < 1.0;
        return true;
    };
    ::AddThinkToEnt <- function(ent, fname) { ::THINKS.append({ ent = ent, fname = fname, next = ::NOW }); };
    ::DoIncludeScript <- function(name, scope) { return ::RunFile(name, scope); };
} else {
    ::EntFireByHandle <- function(target, action, value, delay, activator, caller) {
        if (target.cls == "game_text") {
            ::PickerHudInput(target, action, activator);
        } else if (target.cls == "logic_auto" && action == "Kill") {
            target.Destroy();
        } else if (action == "RunScriptCode") {
            ::QUEUE.append({ at = ::NOW + delay, code = value });
        } else if (action == "Enable" && "RefireTime" in target.kv) {
            assert(target.outputFunction != null);
            ::THINKS.append({ ent = target, fname = target.outputFunction, next = ::NOW });
        } else if (action == "Color") {
            target.tint = value;
        }
    };
    if (B == "portal2" || B == "csgo" || B == "revolution") {
        ::DoEntFire <- function(target, action, value, delay, activator, caller) {
            assert(target == "worldspawn" && action == "RunScriptCode");
            ::Count("DoEntFire");
            ::QUEUE.append({ at = ::NOW + delay, code = value });
        };
        ::Entities.CreateByClassname <- function(classname) {
            local entity = Ent(classname, Vector());
            if (classname == "logic_auto") {
                ::PORTAL2_STARTERS.append(entity);
            } else if (classname == "logic_timer") {
                entity.ValidateScriptScope();
                entity.GetScriptScope().self <- entity;
            }
            return entity;
        };
    }
    // like P2CE: a missing script prints "Script not found" and the call still
    // reports success, so its return value says nothing about the file
    ::DoIncludeScript <- function(name, scope) {
        Count("DoIncludeScript:" + name);
        if (!((name + ".nut") in ::FILES)) {
            Count("Script not found");
            ::LOGS.append("Script not found (scripts/vscripts/" + name + ".nut)");
            return true;
        }
        ::RunFile(name, scope);
        return true;
    };
    ::CreateProp <- function(cls, pos, model, activity) {
        Count("CreateProp");
        if (uses_cube_template && ::Entities.FindByModel(null, model) == null && ::PRECACHED.find(model) == null) {
            // An engine fatal cannot be caught by Squirrel. Let the test runner
            // see the failure even if the bridge catches the mock exception.
            print("ERROR: UTIL_SetModel: not precached: " + model + "\n");
            throw "model not precached";
        }
        return ::MakeProp(cls, pos, model);
    };
    ::TraceLine <- function(start, end, ignore) { return ::FloorFraction(start, end); };
    if (B == "portal2" || B == "strata" || B == "revolution") {
        ::GetPlayer <- function() { return ::PLAYER; };
    }
    if (B == "portal2") {
        ::PORTAL2_MULTIPLAYER <- false;
        ::PORTAL2_BLOCKED <- [];
        ::PORTAL2_CONSOLE <- [];
        ::PORTAL2_STARTERS <- [];
        ::Portal2ActivateMap <- function() {
            foreach (starter in ::PORTAL2_STARTERS) {
                if (!starter.IsValid()) continue;
                local output = split(starter.kv.OnMapSpawn, "\x1b");
                assert(output.len() == 5 && output[0] == "worldspawn" && output[1] == "RunScriptCode");
                assert(output[2].len() < 256 && output[4] == "-1");
                ::QUEUE.append({ at = ::NOW + 0.2 + output[3].tofloat(), code = output[2] });
            }
        };
        ::IsMultiplayer <- function() { return ::PORTAL2_MULTIPLAYER; };
        ::SendToConsole <- function(command) { ::PORTAL2_CONSOLE.append(command); };
        ::Entities.FindByClassnameWithin <- function(prev, classname, origin, radius) {
            local after_previous = prev == null;
            foreach (prop in ::PROPS) {
                if (after_previous && prop.cls == classname && (prop.origin - origin).Length() <= radius) return prop;
                if (prop == prev) after_previous = true;
            }
            return null;
        };
        ::TraceLine = function(start, end, ignore) {
            foreach (target in ::PORTAL2_BLOCKED) {
                if ((target.origin - end).Length() < 0.01) return 0.5;
            }
            foreach (target in ::PROPS) {
                if (target != ignore && (target.origin - end).Length() < 0.01) return 0.9;
            }
            return ::FloorFraction(start, end);
        };
    }
    if (B == "csgo") {
        ::CSGO_EXTRA_PLAYER <- null;
        ::CSGO_BLOCKED_TARGET <- null;
        ::CSGO_CONSOLE <- [];
        ::SendToConsole <- function(command) { ::CSGO_CONSOLE.append(command); };
        ::TraceLine = function(start, end, ignore) {
            local blocked = ::CSGO_BLOCKED_TARGET;
            if (blocked != null && ((blocked.EyePosition() - end).Length() < 0.01 ||
                (blocked.GetCenter() - end).Length() < 0.01)) return 0.5;
            return ::FloorFraction(start, end);
        };
        ::Entities.FindByClassname = function(prev, cls) {
            if (cls == "worldspawn") return prev == null && ::WORLD_SPAWNED ? ::WORLD : null;
            if (cls == "player") return prev == null ? ::PLAYER : ::CSGO_EXTRA_PLAYER;
            local after_previous = prev == null;
            foreach (prop in ::PROPS) {
                if (after_previous && prop.cls == cls) return prop;
                if (prop == prev) after_previous = true;
            }
            return null;
        };
        ::Entities.First <- function() { return ::PLAYER; };
        ::Entities.Next <- function(previous) {
            local after_previous = previous == ::PLAYER;
            foreach (prop in ::PROPS) {
                if (after_previous) return prop;
                if (prop == previous) after_previous = true;
            }
            return null;
        };
        ::CSGO_ROUND <- 0;
        ::CSGO_WARMUP <- true;
        ::ScriptGetRoundsPlayed <- function() { return ::CSGO_ROUND; };
        ::ScriptIsWarmupPeriod <- function() { return ::CSGO_WARMUP; };
    }
    if (B == "strata" || B == "revolution") {
        ::REVOLUTION_CUBE_REFERENCE <- null;
        ::TraceLineEx <- function(start, end, mask, ignore, group) {
            Count("TraceLineEx");
            local f = ::FloorFraction(start, end);
            local p = start + (end - start) * f;
            return { GetEndPos = function() { return p; } };
        };
        ::CreateEntityByName <- function(cls, kv) {
            if (::MOCK_BRANCH == "revolution") {
                if (cls == "prop_dynamic_override") {
                    assert(kv.solid == 0 && kv.rendermode == 10);
                    ::Count("RevolutionCubePrecache");
                    ::REVOLUTION_CUBE_REFERENCE = Ent(cls, Vector());
                    ::REVOLUTION_CUBE_REFERENCE.model = kv.model;
                    return ::REVOLUTION_CUBE_REFERENCE;
                }
                assert(::REVOLUTION_CUBE_REFERENCE != null && ::REVOLUTION_CUBE_REFERENCE.model == kv.model);
                assert(cls == "prop_physics_override" && kv.spawnflags == 8192);
                return ::MakeProp(cls, Vector(0, 0, 0), kv.model);
            }
            // as in P2CE: the origin keyvalue is ignored and the prop starts at
            // the map origin; prop_physics_override reports as prop_physics
            Count("CreateEntityByName");
            if (cls == "prop_physics_override") cls = "prop_physics";
            return ::MakeProp(cls, Vector(0, 0, 0), kv.model);
        };
    }
}

// like the engine's DoIncludeScript: a script's own error is printed and the
// include returns false, so a try around the include never sees it
::RunFile <- function(name, scope) {
    local key = name + ".nut";
    if (!(key in ::FILES)) return false;
    try {
        local fn = compilestring(::FILES[key], key);
        fn.call(scope);
    } catch (e) {
        print("AN ERROR HAS OCCURED [" + e + "] in " + key + "\n");
        return false;
    }
    return true;
}

// the client-side script VM (P2CE runs mapspawn.nut there too) has no entity API
if (("MOCK_CLIENT_VM" in getroottable()) && ::MOCK_CLIENT_VM) {
    foreach (name in ["Entities", "EntFireByHandle", "CreateProp", "CreateEntityByName",
                      "TraceLine", "TraceLineEx", "GetPlayer", "SpawnEntityFromTable",
                      "AddThinkToEnt", "FileToString", "StringToFile"]) {
        if (name in getroottable()) delete getroottable()[name];
    }
}

// ---- driving the clock

::Advance <- function(seconds) {
    local stop = ::NOW + seconds;
    while (::NOW < stop - 0.0001) {
        ::NOW += 0.05;
        local due = [];
        local rest = [];
        foreach (item in ::QUEUE) {
            if (item.at <= ::NOW + 0.0001) due.append(item); else rest.append(item);
        }
        ::QUEUE <- rest;
        foreach (item in due) {
            compilestring(item.code).call(getroottable());
        }
        foreach (think in ::THINKS) {
            if (think.ent.IsValid() && think.next <= ::NOW + 0.0001) {
                local delay = think.ent.GetScriptScope()[think.fname].call(think.ent.GetScriptScope());
                if (delay == null) delay = think.ent.kv.RefireTime;
                think.next = ::NOW + delay;
            }
        }
    }
}

::NewMap <- function() {
    // a map change empties the event queue and the think list; the root table
    // survives here, which is the harder case for duplicate protection
    ::QUEUE <- [];
    foreach (think in ::THINKS) {
        if (think.ent != ::WORLD) think.ent.Destroy();
    }
    ::THINKS <- [];
    ::PRECACHED <- [];
    ::WORLD.scope = null;
    if (::MOCK_BRANCH == "portal2") ::PORTAL2_STARTERS = [];
    if (::MOCK_BRANCH == "revolution") ::REVOLUTION_CUBE_REFERENCE = null;
}
