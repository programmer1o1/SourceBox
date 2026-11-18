// Stand-in for the VScript engine API of one branch, set by ::MOCK_BRANCH, used by
// tests/test_modern_vscript_squirrel.py. Functions a branch does not have are not
// defined (or throw, for methods), the way calling them fails in the real game.
// World: a flat floor at z = 0. The player stands at the origin.

local B = ::MOCK_BRANCH;
::NOW <- 0.0;
::QUEUE <- [];
::THINKS <- [];
::PROPS <- [];
::FILES <- {};
::LOGS <- [];
::PRECACHED <- [];
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

::HAS_EYEANGLES <- (B == "l4d2" || B == "strata");

class Ent {
    cls = null; origin = null; scope = null; kv = null; tint = null; model = null;
    constructor(c, o) { cls = c; origin = o; kv = {}; }
    function GetOrigin() { return origin; }
    function GetClassname() { return cls; }
    function GetModelName() { return model == null ? "" : model; }
    function SetOrigin(o) { origin = o; }
    function Teleport(o, angles) {
        if (::MOCK_BRANCH != "strata") throw "the index 'Teleport' does not exist";
        ::Count("Teleport");
        origin = o;
    }
    function EyePosition() { return origin + Vector(0, 0, 64); }
    function EyeAngles() {
        if (!::HAS_EYEANGLES) throw "the index 'EyeAngles' does not exist";
        return Vector(30, 0, 0); // looking 30 degrees down, along +x
    }
    function GetForwardVector() { return Vector(1, 0, 0); }
    function ValidateScriptScope() { if (scope == null) scope = {}; return true; }
    function GetScriptScope() { return scope; }
    function __KeyValueFromString(k, v) { kv[k] <- v; return true; }
    function PrecacheModel(m) {
        if (::MOCK_BRANCH != "strata") throw "the index 'PrecacheModel' does not exist";
        ::PRECACHED.append(m);
    }
}

::WORLD <- Ent("worldspawn", Vector(0, 0, 0));
::PLAYER <- Ent(B == "swarm" ? "asw_marine" : "player", Vector(0, 0, 0));

::Entities <- {
    FindByClassname = function(prev, cls) {
        if (prev != null) return null;
        if (cls == "worldspawn") return ::WORLD;
        if (cls == ::PLAYER.cls) return ::PLAYER;
        return null;
    }
};

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
    ::GetListenServerHost <- function() { return ::PLAYER; };
    ::FileToString <- function(name) { Count("FileToString"); return (name in ::FILES) ? ::FILES[name] : null; };
    ::StringToFile <- function(name, text) { ::FILES[name] <- text; };
    ::PrecacheModel <- function(m) { ::PRECACHED.append(m); return 1; };
    ::SpawnEntityFromTable <- function(cls, t) {
        local e = ::MakeProp(cls, t.origin, t.model);
        if ("rendercolor" in t) e.tint = t.rendercolor;
        return e;
    };
    ::TraceLine <- function(t) {
        local f = ::FloorFraction(t.start, t.end);
        t.pos <- t.start + (t.end - t.start) * f;
        t.hit <- f < 1.0;
        return true;
    };
    ::AddThinkToEnt <- function(ent, fname) { ::THINKS.append({ ent = ent, fname = fname, next = ::NOW }); };
    ::DoIncludeScript <- function(name, scope) { return ::RunFile(name, scope); };
} else {
    ::EntFireByHandle <- function(target, action, value, delay, activator, caller) {
        if (action == "RunScriptCode") {
            ::QUEUE.append({ at = ::NOW + delay, code = value });
        } else if (action == "Color") {
            target.tint = value;
        }
    };
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
    ::CreateProp <- function(cls, pos, model, activity) { Count("CreateProp"); return ::MakeProp(cls, pos, model); };
    ::TraceLine <- function(start, end, ignore) { return ::FloorFraction(start, end); };
    if (B == "portal2" || B == "strata") {
        ::GetPlayer <- function() { return ::PLAYER; };
    }
    if (B == "csgo") {
        ::PrecacheModel <- function(m) { ::PRECACHED.append(m); };
    }
    if (B == "strata") {
        ::TraceLineEx <- function(start, end, mask, ignore, group) {
            Count("TraceLineEx");
            local f = ::FloorFraction(start, end);
            local p = start + (end - start) * f;
            return { GetEndPos = function() { return p; } };
        };
        ::CreateEntityByName <- function(cls, kv) {
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
            if (think.next <= ::NOW + 0.0001) {
                local delay = think.ent.GetScriptScope()[think.fname].call(think.ent.GetScriptScope());
                think.next = ::NOW + delay;
            }
        }
    }
}

::NewMap <- function() {
    // a map change empties the event queue and the think list; the root table
    // survives here, which is the harder case for duplicate protection
    ::QUEUE <- [];
    ::THINKS <- [];
    ::WORLD.scope = null;
}
