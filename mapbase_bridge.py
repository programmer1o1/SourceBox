"""
Mapbase bridge helper for SourceBox.
Provides basic path preparation for mapbase-based sourcemods so VScript
features can be dropped in automatically.
"""

import os


class MapbaseBridge:
    def __init__(self, mod_path, verbose=False):
        self.mod_path = os.path.abspath(mod_path)
        self.verbose = verbose
        self.scriptdata_path = os.path.join(self.mod_path, "vscript_io") 
        self.vscripts_path = os.path.join(self.mod_path, "scripts", "vscripts")
        self.command_file = os.path.join(self.scriptdata_path, "python_command.txt")
        self.response_file = os.path.join(self.scriptdata_path, "python_response.txt")

    def prepare_paths(self):
        """create required folders for VScript bridge files"""
        try:
            os.makedirs(self.scriptdata_path, exist_ok=True)
            os.makedirs(self.vscripts_path, exist_ok=True)
            return True
        except Exception as e:
            if self.verbose:
                print(f"[error] mapbase path setup failed: {e}")
            return False

    def install_scripts(self):
        """Install complete, ready-to-use VScript files"""
        scripts = {
            "auto_spawner.nut": self._get_auto_spawner_script(),
            "picker.nut": self._get_picker_script(),
            "python_listener.nut": self._get_python_listener_script(),
            "vscript_server.nut": self._get_vscript_server_script()
        }

        for filename, content in scripts.items():
            dest = os.path.join(self.vscripts_path, filename)
            try:
                with open(dest, "w", encoding="utf-8", newline="\n") as f:
                    f.write(content)
                if self.verbose:
                    print(f"[installed] {filename}")
            except Exception as e:
                if self.verbose:
                    print(f"[warning] failed to write {dest}: {e}")

    def _get_auto_spawner_script(self):
        """return complete auto_spawner.nut script"""
        return """\
if (!("g_auto_spawn_initialized" in getroottable())) {
    ::g_auto_spawn_initialized <- false;
    ::g_spawned_cubes <- [];
    ::g_spawn_attempts <- 0;
    ::g_spawn_method_index <- 0;
}

::CUBE_MODEL <- "models/props/srcbox/srcbox.mdl";
::awp_weapon_classes <- ["weapon_awp"];

::QuitGame <- function() {
    SendToConsole("quit")
}

::GetPlayer <- function() {
    local player = null;
    try {
        player = Entities.FindByClassname(null, "player");
    } catch(e) {}
    return player;
}

::CheckRespawn <- function(self) {
    if (g_auto_spawn_initialized && g_spawned_cubes.len() > 0) {
        local cube = g_spawned_cubes[0];
        if (cube == null || !cube.IsValid()) {
            g_spawned_cubes = [];
            g_auto_spawn_initialized = false;
            g_spawn_attempts = 0;
        }
    }
    return 0.5;
}

::CheckAttackerWeapon <- function(damaged_prop) {
    local host = GetPlayer();
    if (host == null) return;

    local player = null;
    while ((player = Entities.FindByClassname(player, "player")) != null) {
        if (player != host) continue;

        local active_weapon = null;
        try {
            active_weapon = NetProps.GetPropEntity(player, "m_hActiveWeapon");
        } catch(e) {
            continue;
        }

        if (active_weapon == null || !active_weapon.IsValid()) {
            continue;
        }

        local weapon_classname = null;
        try {
            weapon_classname = active_weapon.GetClassname();
        } catch(e) {
            continue;
        }

        if (weapon_classname == null) {
            continue;
        }

        foreach (awp_class in awp_weapon_classes) {
            if (weapon_classname == awp_class) {
                DoEntFireByInstanceHandle(damaged_prop, "RunScriptCode", "QuitGame()", 0.1, null, null);
                return;
            }
        }
    }
}

::SetupCubeDamageOutput <- function(cube) {
    if (cube != null && cube.IsValid()) {
        local current_health = cube.GetHealth();
        if (current_health <= 0) {
            try {
                cube.SetHealth(100);
            } catch(e) {}
        }

        DoEntFireByInstanceHandle(cube, "AddOutput", "OnTakeDamage !self:RunScriptCode:CheckAttackerWeapon(self):0:-1", 0, null, null);
    }
}

::TeleportToCube <- function() {
    if (g_spawned_cubes.len() > 0) {
        local cube = g_spawned_cubes[0];

        if (cube == null || !cube.IsValid()) {
            g_spawned_cubes = [];
            g_auto_spawn_initialized = false;
            g_spawn_attempts = 0;
            return;
        }

        local cube_pos = cube.GetOrigin();
        local player = GetPlayer();

        if (player != null) {
            local teleport_pos = Vector(cube_pos.x, cube_pos.y, cube_pos.z + 100);

            try {
                player.SetOrigin(teleport_pos);
            } catch(e) {}

            try {
                cube.SetRenderColor(255, 0, 0);
            } catch(e) {}
        }
    }
}

::IsPositionReachable <- function(pos) {
    local start = Vector(pos.x, pos.y, pos.z + 10);
    local end = Vector(pos.x, pos.y, pos.z - 500);

    local trace_fraction = 1.0;
    try {
        trace_fraction = TraceLine(start, end, null);
    } catch(e) {
        return false;
    }

    if (trace_fraction >= 1.0) {
        return false;
    }

    local ground_pos = start + (end - start) * trace_fraction;
    local height_above_ground = pos.z - ground_pos.z;

    if (height_above_ground > 150 || height_above_ground < -50) {
        return false;
    }

    local trace_up_start = pos;
    local trace_up_end = Vector(pos.x, pos.y, pos.z + 300);

    local trace_up_fraction = 1.0;
    try {
        trace_up_fraction = TraceLine(trace_up_start, trace_up_end, null);
    } catch(e) {}

    if (trace_up_fraction < 1.0) {
        local hit_pos = trace_up_start + (trace_up_end - trace_up_start) * trace_up_fraction;
        local clearance = hit_pos.z - pos.z;
        if (clearance < 100) {
            return false;
        }
    }

    local player = GetPlayer();

    if (player != null) {
        local player_pos = player.GetOrigin();
        local dist = (pos - player_pos).Length();

        if (dist > 5000) {
            return false;
        }

        if (dist < 200) {
            return false;
        }
    }

    return true;
}

::FindNearPlayerSpawn <- function() {
    local spawn_classes = [
        "info_player_start",
        "info_player_deathmatch",
        "info_player_teamspawn",
        "info_player_terrorist",
        "info_player_counterterrorist",
        "info_player_rebel",
        "info_player_combine",
        "info_player_coop"
    ];

    local spawn_positions = [];

    foreach (classname in spawn_classes) {
        local spawn = null;
        while ((spawn = Entities.FindByClassname(spawn, classname)) != null) {
            spawn_positions.append(spawn.GetOrigin());
        }
    }

    if (spawn_positions.len() == 0) {
        return null;
    }

    local random_spawn = spawn_positions[RandomInt(0, spawn_positions.len() - 1)];
    local test_distances = [300, 500, 700, 900];
    local test_angles = [0, 45, 90, 135, 180, 225, 270, 315];

    foreach (dist in test_distances) {
        foreach (angle_deg in test_angles) {
            local angle = angle_deg * 0.0174533;
            local test_pos = Vector(
                random_spawn.x + cos(angle) * dist,
                random_spawn.y + sin(angle) * dist,
                random_spawn.z + 50
            );

            if (IsPositionReachable(test_pos)) {
                return test_pos;
            }
        }
    }

    return null;
}

::FindNearPropPhysics <- function() {
    local props = [];
    local prop = null;

    while ((prop = Entities.FindByClassname(prop, "prop_physics")) != null) {
        props.append(prop);
        if (props.len() >= 30) break;
    }

    if (props.len() == 0) {
        prop = null;
        while ((prop = Entities.FindByClassname(prop, "prop_dynamic")) != null) {
            props.append(prop);
            if (props.len() >= 30) break;
        }
    }

    for (local attempt = 0; attempt < 10; attempt++) {
        if (props.len() == 0) break;

        local random_prop = props[RandomInt(0, props.len() - 1)];
        local prop_pos = random_prop.GetOrigin();

        local angles = [0, 45, 90, 135, 180, 225, 270, 315];
        local distances = [200, 350, 500];

        foreach (dist in distances) {
            foreach (angle_deg in angles) {
                local angle = angle_deg * 0.0174533;
                local test_pos = Vector(
                    prop_pos.x + cos(angle) * dist,
                    prop_pos.y + sin(angle) * dist,
                    prop_pos.z + 50
                );

                if (IsPositionReachable(test_pos)) {
                    return test_pos;
                }
            }
        }
    }

    return null;
}

::FindWeaponOrItemLocation <- function() {
    local locations = [];

    local weapon = null;
    while ((weapon = Entities.FindByClassname(weapon, "weapon_*")) != null) {
        local pos = weapon.GetOrigin();
        pos.z += 50;
        if (IsPositionReachable(pos)) {
            locations.append(pos);
        }
        if (locations.len() >= 15) break;
    }

    if (locations.len() == 0) {
        local item = null;
        while ((item = Entities.FindByClassname(item, "item_*")) != null) {
            local pos = item.GetOrigin();
            pos.z += 50;
            if (IsPositionReachable(pos)) {
                locations.append(pos);
            }
            if (locations.len() >= 15) break;
        }
    }

    if (locations.len() > 0) {
        return locations[RandomInt(0, locations.len() - 1)];
    }

    return null;
}

::FindNearPlayer <- function() {
    local player = GetPlayer();

    if (player != null) {
        local ppos = player.GetOrigin();
        local test_distances = [400, 600, 800];
        local test_angles = [0, 45, 90, 135, 180, 225, 270, 315];

        foreach (dist in test_distances) {
            foreach (angle_deg in test_angles) {
                local angle = angle_deg * 0.0174533;
                local test_pos = Vector(
                    ppos.x + cos(angle) * dist,
                    ppos.y + sin(angle) * dist,
                    ppos.z + 50
                );

                if (IsPositionReachable(test_pos)) {
                    return test_pos;
                }
            }
        }
    }

    return null;
}

::SpawnCubeAtPosition <- function(pos) {
    local cube = null;

    try {
        cube = SpawnEntityFromTable("prop_physics", {
            origin = pos,
            angles = Vector(0, RandomFloat(0, 360), 0),
            model = CUBE_MODEL,
            health = 100
        });
    } catch(e) {}

    if (cube == null) {
        try {
            cube = SpawnEntityFromTable("prop_dynamic", {
                origin = pos,
                angles = Vector(0, RandomFloat(0, 360), 0),
                model = CUBE_MODEL,
                solid = 6,
                health = 100
            });
        } catch(e) {}
    }

    if (cube != null) {
        SetupCubeDamageOutput(cube);
        return cube;
    }

    return null;
}

::SpawnCubeSmartly <- function() {
    local spawn_methods = [
        { func = FindNearPlayerSpawn, name = "near player spawn" },
        { func = FindNearPropPhysics, name = "near prop_physics" },
        { func = FindWeaponOrItemLocation, name = "near weapon/item" },
        { func = FindNearPlayer, name = "near player" }
    ];

    local start_index = g_spawn_method_index % spawn_methods.len();

    for (local i = 0; i < spawn_methods.len(); i++) {
        local method_index = (start_index + i) % spawn_methods.len();
        local method = spawn_methods[method_index];

        local spawn_pos = method.func();

        if (spawn_pos != null) {
            local cube = SpawnCubeAtPosition(spawn_pos);

            if (cube != null) {
                g_spawned_cubes.append(cube);
                g_spawn_method_index = (method_index + 1) % spawn_methods.len();
                return true;
            }
        }
    }

    return false;
}

::InitializeAutoSpawner <- function(self) {
    if (g_auto_spawn_initialized) {
        return null;
    }

    local current_time = Time();

    if (current_time < 3.0) {
        return 0.5;
    }

    g_spawn_attempts++;

    local success = SpawnCubeSmartly();

    if (success || g_spawn_attempts >= 6) {
        g_auto_spawn_initialized = true;
        return null;
    }

    return 1.0;
}

::StartAutoSpawnerThink <- function() {
    local worldspawn = Entities.FindByClassname(null, "worldspawn");
    if (worldspawn != null) {
        worldspawn.SetContextThink("auto_spawner", InitializeAutoSpawner, 0.0);
        worldspawn.SetContextThink("respawn_checker", CheckRespawn, 0.0);
    }
}

DoEntFire("worldspawn", "RunScriptCode", "StartAutoSpawnerThink()", 1.0, null, null);
"""

    def _get_picker_script(self):
        """return complete picker.nut script"""
        return """\
if (!("g_enabled" in getroottable()))
{
    ::g_enabled <- {};
    ::g_target <- {};
    ::g_manual <- {};
    ::g_targets <- {};
    ::g_targetidx <- {};
    ::g_manualtime <- {};
    ::g_lasthud <- {};
    ::g_first <- true;
}
else
{
    ::g_first <- false;
}

if (!("g_teamplay" in getroottable()))
{
    ::g_teamplay <- null;
}

::MAX_DIST <- 5000.0;
::SMOOTH <- 0.15;
::MANUAL_TIMEOUT <- 3.0;

::NPC_CLASSES <- [
    "npc_combine_s",
    "npc_metropolice",
    "npc_zombie",
    "npc_headcrab",
    "npc_antlion",
    "npc_citizen",
    "npc_barney",
    "npc_alyx",
    "npc_vortigaunt",
    "npc_fastzombie",
    "npc_poisonzombie",
    "npc_zombine",
    "npc_antlionguard",
    "npc_crow",
    "npc_seagull",
    "npc_pigeon",
    "npc_dog",
    "npc_eli",
    "npc_gman",
    "npc_kleiner",
    "npc_mossman",
    "npc_monk",
    "npc_helicopter",
    "npc_combinegunship",
    "npc_combinedropship",
    "npc_strider",
    "npc_turret_floor",
    "npc_manhack",
    "npc_cscanner",
    "npc_clawscanner",
    "npc_rollermine",
    "npc_turret_ceiling",
    "npc_turret_ground",
    "npc_vehicledriver",
    "npc_apcdriver",
    "npc_hunter"
];

::DetectTeamplay <- function()
{
    if (g_teamplay != null)
        return g_teamplay;

    local hasRealTeams = false;
    local teamCounts = {};

    local p = null;
    local count = 0;
    while ((p = Entities.FindByClassname(p, "player")) != null)
    {
        if (p.IsAlive())
        {
            local t = p.GetTeam();
            if (t >= 2)
            {
                if (!(t in teamCounts))
                    teamCounts[t] <- 0;
                teamCounts[t]++;
                count++;
            }
        }
    }

    local numTeams = 0;
    foreach (team, cnt in teamCounts)
    {
        if (cnt > 0)
            numTeams++;
    }

    if (numTeams >= 2)
    {
        g_teamplay = true;
    }
    else
    {
        try
        {
            local val = Convars.GetFloat("mp_teamplay");
            g_teamplay = (val > 0);
        }
        catch (e)
        {
            g_teamplay = false;
        }
    }

    return g_teamplay;
}

::GetPlayer <- function()
{
    local player = null;
    try {
        player = Entities.FindByClassname(null, "player");
    } catch(e) {}

    return player;
}

::InitPlayer <- function(p)
{
    local id = p.entindex().tostring();
    g_enabled[id] <- false;
    g_target[id] <- null;
    g_manual[id] <- false;
    g_targets[id] <- [];
    g_targetidx[id] <- 0;
    g_manualtime[id] <- 0.0;
    g_lasthud[id] <- 0.0;
}

::ShowHud <- function(p, msg)
{
    try {
        ClientPrint(p, 3, msg);
    } catch(e) {
        try {
            local txt = SpawnEntityFromTable("game_text", {
                message = msg,
                channel = 1,
                x = -1,
                y = 0.53,
                effect = 0,
                color = "255 160 0",
                color2 = "255 160 0",
                fadein = 0.0,
                fadeout = 0.0,
                holdtime = 0.55,
                fxtime = 0,
                spawnflags = 1
            });

            if (txt != null)
            {
                DoEntFireByInstanceHandle(txt, "Display", "", 0.0, p, p);
                DoEntFireByInstanceHandle(txt, "Kill", "", 0.6, null, null);
            }
        } catch(e2) {}
    }
}

::ClearHud <- function(p)
{
    try {
        ClientPrint(p, 3, "");
    } catch(e) {
        try {
            local txt = SpawnEntityFromTable("game_text", {
                message = "",
                channel = 1,
                x = -1,
                y = 0.53,
                holdtime = 0
            });

            if (txt != null)
            {
                DoEntFireByInstanceHandle(txt, "Display", "", 0.0, p, p);
                DoEntFireByInstanceHandle(txt, "Kill", "", 0.01, null, null);
            }
        } catch(e2) {}
    }
}

::Toggle <- function(p)
{
    local id = p.entindex().tostring();

    if (!(id in g_enabled))
        InitPlayer(p);

    g_enabled[id] = !g_enabled[id];
    g_target[id] = null;
    g_manual[id] = false;
    g_targetidx[id] = 0;
    g_manualtime[id] = 0.0;
    g_targets[id] = [];

    if (g_enabled[id])
    {
        StartPickerThink(p);
    }
    else
    {
        try {
            p.StopThink("PickerThink");
        } catch(e) {}
        ClearHud(p);
    }
}

::NextTarget <- function(p)
{
    local id = p.entindex().tostring();

    if (!(id in g_enabled) || !g_enabled[id] || !p.IsAlive())
    {
        return;
    }

    g_manual[id] = true;
    g_manualtime[id] = Time();
    g_targets[id] = BuildList(p);

    if (g_targets[id].len() > 0)
    {
        g_targetidx[id]++;
        if (g_targetidx[id] >= g_targets[id].len())
            g_targetidx[id] = 0;

        g_target[id] = g_targets[id][g_targetidx[id]];
    }
}

::BuildList <- function(p)
{
    local list = [];
    local team = p.GetTeam();
    local pos = p.EyePosition();
    local teamplay = DetectTeamplay();

    local e = null;
    while ((e = Entities.FindByClassname(e, "player")) != null)
    {
        if (e == p || !e.IsAlive())
            continue;

        local t = e.GetTeam();

        if (teamplay)
        {
            if (t <= 1 || t == team)
                continue;
        }

        local tpos = e.EyePosition();
        local dist = (tpos - pos).Length();

        if (dist > MAX_DIST || !CanSee(p, e, tpos))
            continue;

        list.append(e);
    }

    foreach (npcClass in NPC_CLASSES)
    {
        e = null;
        while ((e = Entities.FindByClassname(e, npcClass)) != null)
        {
            try {
                if (e.GetHealth() <= 0)
                    continue;
            } catch(ex) {
                continue;
            }

            local tpos = null;
            try {
                tpos = e.EyePosition();
            } catch(ex) {
                tpos = e.GetOrigin() + Vector(0, 0, 32);
            }

            local dist = (tpos - pos).Length();

            if (dist > MAX_DIST || !CanSee(p, e, tpos))
                continue;

            list.append(e);
        }
    }

    if (teamplay)
    {
        e = null;
        while ((e = Entities.FindByClassname(e, "player")) != null)
        {
            if (e == p || !e.IsAlive())
                continue;

            local t = e.GetTeam();
            if (t <= 1 || t != team)
                continue;

            local tpos = e.EyePosition();
            local dist = (tpos - pos).Length();

            if (dist > MAX_DIST || !CanSee(p, e, tpos))
                continue;

            list.append(e);
        }
    }

    local props = ["prop_physics", "prop_physics_multiplayer", "prop_physics_override"];
    foreach (c in props)
    {
        e = null;
        while ((e = Entities.FindByClassname(e, c)) != null)
        {
            local tpos = e.GetOrigin();
            local dist = (tpos - pos).Length();

            if (dist > MAX_DIST || !CanSee(p, e, tpos))
                continue;

            list.append(e);
        }
    }

    return list;
}

::IsValid <- function(p, e)
{
    if (e == null || !e.IsValid())
        return false;

    local c = e.GetClassname();

    if (c == "player")
    {
        if (!e.IsAlive() || e == p)
            return false;

        local t = e.GetTeam();
        local teamplay = DetectTeamplay();

        if (teamplay && t <= 1)
            return false;

        return CanSee(p, e, e.EyePosition());
    }

    foreach (npcClass in NPC_CLASSES)
    {
        if (c == npcClass)
        {
            try {
                if (e.GetHealth() <= 0)
                    return false;
            } catch(ex) {
                return false;
            }

            local tpos = null;
            try {
                tpos = e.EyePosition();
            } catch(ex) {
                tpos = e.GetOrigin() + Vector(0, 0, 32);
            }

            return CanSee(p, e, tpos);
        }
    }

    return CanSee(p, e, e.GetOrigin());
}

::GetBest <- function(p)
{
    local team = p.GetTeam();
    local pos = p.EyePosition();
    local teamplay = DetectTeamplay();

    local bestEnemy = null;
    local bestNPC = null;
    local bestTeam = null;
    local bestProp = null;
    local bestEDist = 999999.0;
    local bestNDist = 999999.0;
    local bestTDist = 999999.0;
    local bestPDist = 999999.0;

    local e = null;
    while ((e = Entities.FindByClassname(e, "player")) != null)
    {
        if (e == p || !e.IsAlive())
            continue;

        local t = e.GetTeam();

        local tpos = e.EyePosition();
        local dist = (tpos - pos).Length();

        if (dist > MAX_DIST || !CanSee(p, e, tpos))
            continue;

        if (teamplay)
        {
            if (t <= 1)
                continue;

            if (t != team)
            {
                if (dist < bestEDist)
                {
                    bestEDist = dist;
                    bestEnemy = e;
                }
            }
            else
            {
                if (dist < bestTDist)
                {
                    bestTDist = dist;
                    bestTeam = e;
                }
            }
        }
        else
        {
            if (dist < bestEDist)
            {
                bestEDist = dist;
                bestEnemy = e;
            }
        }
    }

    foreach (npcClass in NPC_CLASSES)
    {
        e = null;
        while ((e = Entities.FindByClassname(e, npcClass)) != null)
        {
            try {
                if (e.GetHealth() <= 0)
                    continue;
            } catch(ex) {
                continue;
            }

            local tpos = null;
            try {
                tpos = e.EyePosition();
            } catch(ex) {
                tpos = e.GetOrigin() + Vector(0, 0, 32);
            }

            local dist = (tpos - pos).Length();

            if (dist > MAX_DIST || !CanSee(p, e, tpos))
                continue;

            if (dist < bestNDist)
            {
                bestNDist = dist;
                bestNPC = e;
            }
        }
    }

    if (bestEnemy != null)
        return bestEnemy;

    if (bestNPC != null)
        return bestNPC;

    if (bestTeam != null)
        return bestTeam;

    local props = ["prop_physics", "prop_physics_multiplayer", "prop_physics_override"];
    foreach (c in props)
    {
        e = null;
        while ((e = Entities.FindByClassname(e, c)) != null)
        {
            local tpos = e.GetOrigin();
            local dist = (tpos - pos).Length();

            if (dist > MAX_DIST || !CanSee(p, e, tpos))
                continue;

            if (dist < bestPDist)
            {
                bestPDist = dist;
                bestProp = e;
            }
        }
    }

    return bestProp;
}

::CanSee <- function(p, t, tpos)
{
    local start = p.EyePosition();
    local tr = TraceLine(start, tpos, p);

    if (tr == 1.0)
        return true;

    local hitPos = start + (tpos - start) * tr;
    local d = (hitPos - tpos).Length();
    if (d < 100.0)
        return true;

    return false;
}

::CalcAngles <- function(from, to)
{
    local d = to - from;
    local h = d.Length();

    if (h < 0.001)
        return Vector(0, 0, 0);

    local pitch = asin(-d.z / h) * (180.0 / 3.14159);
    local yaw = atan2(d.y, d.x) * (180.0 / 3.14159);

    return Vector(pitch, yaw, 0);
}

::NormAngle <- function(a)
{
    while (a > 180.0) a -= 360.0;
    while (a < -180.0) a += 360.0;
    return a;
}

::Lerp <- function(from, to, amt)
{
    local d = NormAngle(to - from);
    return from + d * amt;
}

::Aim <- function(p, e)
{
    local ppos = p.EyePosition();
    local tpos = null;

    local c = e.GetClassname();
    if (c == "player")
    {
        tpos = e.EyePosition();
    }
    else
    {
        local isNPC = false;
        foreach (npcClass in NPC_CLASSES)
        {
            if (c == npcClass)
            {
                isNPC = true;
                break;
            }
        }

        if (isNPC)
        {
            try {
                tpos = e.EyePosition();
            } catch(ex) {
                tpos = e.GetOrigin() + Vector(0, 0, 32);
            }
        }
        else
        {
            tpos = e.GetOrigin();
        }
    }

    local want = CalcAngles(ppos, tpos);
    local cur = p.EyeAngles();

    local dp = NormAngle(want.x - cur.x);
    local dy = NormAngle(want.y - cur.y);
    local td = sqrt(dp * dp + dy * dy);

    local smooth = SMOOTH;
    if (td < 5.0) smooth *= 0.6;
    else if (td > 30.0) smooth *= 1.3;

    local np = Lerp(cur.x, want.x, smooth);
    local ny = Lerp(cur.y, want.y, smooth);

    if (np > 89.0) np = 89.0;
    if (np < -89.0) np = -89.0;

    while (ny > 180.0) ny -= 360.0;
    while (ny < -180.0) ny += 360.0;

    p.SetAngles(Vector(np, ny, 0));
}

::PickerThinkFunc <- function(self)
{
    local p = GetPlayer();

    if (p == null || !p.IsValid() || !p.IsAlive()) {
        return 0.015;
    }

    local id = p.entindex().tostring();

    if (!(id in g_enabled))
        InitPlayer(p);

    if (!g_enabled[id])
        return 0.015;

    local t = Time();

    if (t - g_lasthud[id] > 0.54)
    {
        ShowHud(p, "PICKER ON");
        g_lasthud[id] = t;
    }

    if (g_manual[id] && t - g_manualtime[id] > MANUAL_TIMEOUT)
        g_manual[id] = false;

    if (g_manual[id])
    {
        if (g_target[id] == null || !IsValid(p, g_target[id]))
        {
            g_manual[id] = false;
        }
        else
        {
            local best = GetBest(p);
            if (best != null)
            {
                local curEnemy = false;
                local curClass = g_target[id].GetClassname();

                if (curClass == "player")
                {
                    local ct = g_target[id].GetTeam();
                    local pt = p.GetTeam();
                    local teamplay = DetectTeamplay();

                    if (teamplay)
                    {
                        if (ct != pt && ct > 1)
                            curEnemy = true;
                    }
                    else
                    {
                        curEnemy = true;
                    }
                }

                local bestEnemy = false;
                local bestClass = best.GetClassname();

                if (bestClass == "player")
                {
                    local bt = best.GetTeam();
                    local pt = p.GetTeam();
                    local teamplay = DetectTeamplay();

                    if (teamplay)
                    {
                        if (bt != pt && bt > 1)
                            bestEnemy = true;
                    }
                    else
                    {
                        bestEnemy = true;
                    }
                }

                if (bestEnemy && !curEnemy)
                {
                    g_manual[id] = false;
                    g_target[id] = best;
                }
                else if (bestEnemy && curEnemy)
                {
                    local ppos = p.EyePosition();
                    local cd = (g_target[id].EyePosition() - ppos).Length();
                    local bd = (best.EyePosition() - ppos).Length();

                    if (bd < cd * 0.5)
                    {
                        g_manual[id] = false;
                        g_target[id] = best;
                    }
                }
            }
        }
    }
    else
    {
        local nt = GetBest(p);
        if (nt != null)
            g_target[id] = nt;
    }

    if (g_target[id] != null)
        Aim(p, g_target[id]);

    return 0.015;
}

::StartPickerThink <- function(p)
{
    try {
        p.SetContextThink("PickerThink", PickerThinkFunc, 0.0);
    } catch(e) {}
}

::PickerToggle <- function() {
    local player = GetPlayer();
    if (player != null && player.IsValid())
    {
        Toggle(player);
    }
}

::PickerNext <- function() {
    local player = GetPlayer();
    if (player != null && player.IsValid())
    {
        NextTarget(player);
    }
}
"""

    def _get_python_listener_script(self):
        """return complete python_listener.nut script"""
        return """\
if (!("g_think_functions" in getroottable())) {
    ::g_think_functions <- {};
    ::g_think_delays <- {};
}

if (!("RegisterThinkFunction" in getroottable())) {
    ::RegisterThinkFunction <- function(name, func, initial_delay = 0.0) {
        g_think_functions[name] <- func;
        g_think_delays[name] <- Time() + initial_delay;
    }
}

if (!("g_perf_filter_ready" in getroottable())) {
    ::g_perf_filter_ready <- false;

    ::ApplyPerfFilter <- function() {
        local ok = false;
        try {
            SendToConsole("con_filter_enable 1");
            SendToConsole("con_filter_text_out \\"SCRIPT PERF WARNING\\"");
            local cur = Convars.GetStr("con_filter_text_out");
            if (cur != null && cur.find("SCRIPT PERF WARNING") != null) {
                ok = true;
            }
        } catch(e) {}

        if (!ok) {
            try {
                Convars.SetStr("con_filter_enable", "1");
                Convars.SetStr("con_filter_text_out", "SCRIPT PERF WARNING");
                ok = true;
            } catch(e) {}
        }

        if (ok) {
            g_perf_filter_ready = true;
            return null;
        }
        return 0.5;
    };

    RegisterThinkFunction("perf_filter", ApplyPerfFilter, 0.0);
}

if (!("UnregisterThinkFunction" in getroottable())) {
    ::UnregisterThinkFunction <- function(name) {
        if (name in g_think_functions) {
            delete g_think_functions[name];
            delete g_think_delays[name];
        }
    }
}

function MasterThink(self = null) {
    local current_time = Time();

    foreach (name, func in g_think_functions) {
        if (current_time >= g_think_delays[name]) {
            try {
                local delay = func();
                if (delay == null || delay < 0.0) delay = 0.1;
                g_think_delays[name] = current_time + delay;
            } catch(e) {}
        }
    }

    return 0.01;
}

if (!("g_python_session_id" in getroottable())) {
    ::g_python_session_id <- 0
}
if (!("g_python_last_command_id" in getroottable())) {
    ::g_python_last_command_id <- 0
}

::last_command_id <- g_python_last_command_id
::current_session_id <- g_python_session_id

function CheckPythonCommand() {
    local command_str = null

    try {
        command_str = FileToString("python_command.txt")
    } catch(e) {
        return 0.1
    }

    if (command_str == null || command_str.len() == 0) {
        return 0.1
    }

    local session_id = ExtractNumber(command_str, "session")

    if (session_id > 0 && session_id != current_session_id) {
        current_session_id = session_id
        ::g_python_session_id <- session_id

        last_command_id = 0
        ::g_python_last_command_id <- 0
    }

    ParseAndExecuteCommand(command_str)
    return 0.1
}

function ParseAndExecuteCommand(json_str) {
    local session_id = ExtractNumber(json_str, "session")

    if (session_id == 0) {
        return
    }

    if (current_session_id > 0 && session_id != current_session_id) {
        return
    }

    local command_id = ExtractNumber(json_str, "id")

    if (command_id <= 0) {
        return
    }

    if (command_id <= last_command_id) {
        return
    }

    last_command_id = command_id
    ::g_python_last_command_id <- command_id

    local command = ExtractString(json_str, "command")

    if (command == null || command.len() == 0) {
        SendResponse("error", "empty command")
        return
    }

    try {
        if (command == "spawn_model") {
            local model = ExtractString(json_str, "model")
            local distance = ExtractNumber(json_str, "distance")
            if (distance == 0) distance = 200

            if (model == null || model.len() == 0) {
                SendResponse("error", "no model specified")
                return
            }

            SpawnModelAtCrosshair(model, distance)
        } else if (command == "reinstall_awp") {
            if ("SetupDamageOutput" in getroottable()) {
                try {
                    SetupDamageOutput()
                    SendResponse("success", "awp outputs reinstalled")
                } catch(e) {
                    SendResponse("error", "awp reinstall failed")
                }
            } else {
                SendResponse("error", "awp function not found")
            }
        } else {
            SendResponse("error", "unknown command")
        }
    } catch(e) {
        SendResponse("error", "execution failed: " + e)
    }
}

function ExtractString(json_str, key) {
    try {
        local key_str = "\\"" + key + "\\""
        local key_pos = json_str.find(key_str)
        if (key_pos == null) return null

        local value_start = json_str.find("\\"", key_pos + key_str.len())
        if (value_start == null) return null
        value_start++

        local value_end = json_str.find("\\"", value_start)
        if (value_end == null) return null

        return json_str.slice(value_start, value_end)
    } catch(e) {
        return null
    }
}

function ExtractNumber(json_str, key) {
    try {
        local key_str = "\\"" + key + "\\":"
        local key_pos = json_str.find(key_str)
        if (key_pos == null) return 0

        local value_start = key_pos + key_str.len()
        while (value_start < json_str.len()) {
            local char = json_str.slice(value_start, value_start + 1)
            if (char != " " && char != "\\t" && char != "\\n") break
            value_start++
        }

        local value_end = value_start
        while (value_end < json_str.len()) {
            local char = json_str.slice(value_end, value_end + 1)
            if (char == "," || char == "}" || char == " ") break
            value_end++
        }

        if (value_end <= value_start) return 0

        local num_str = json_str.slice(value_start, value_end)
        try {
            return num_str.tointeger()
        } catch(e) {
            return 0
        }
    } catch(e) {
        return 0
    }
}

function GetLocalPlayer() {
    local player = null
    try {
        player = Entities.FindByClassname(null, "player")
    } catch(e) {}
    return player
}

function SpawnModelAtCrosshair(model_path, distance) {
    local player = GetLocalPlayer()
    if (player == null) {
        SendResponse("error", "no player")
        return
    }

    local eye_pos = null
    local eye_angles = null

    try {
        eye_pos = player.EyePosition()
        eye_angles = player.EyeAngles()
    } catch(e) {
        SendResponse("error", "failed to get player view")
        return
    }

    if (eye_pos == null || eye_angles == null) {
        SendResponse("error", "invalid player view")
        return
    }

    local pitch = eye_angles.x * 0.0174533
    local yaw = eye_angles.y * 0.0174533

    local forward_x = cos(yaw) * cos(pitch)
    local forward_y = sin(yaw) * cos(pitch)
    local forward_z = -sin(pitch)

    local end_pos = Vector(
        eye_pos.x + (forward_x * distance),
        eye_pos.y + (forward_y * distance),
        eye_pos.z + (forward_z * distance)
    )

    local trace_fraction = 1.0
    try {
        trace_fraction = TraceLine(eye_pos, end_pos, player)
    } catch(e) {}

    local spawn_pos = end_pos

    if (trace_fraction < 1.0) {
        spawn_pos = eye_pos + (end_pos - eye_pos) * trace_fraction
    }

    spawn_pos.z += 10

    if (model_path.find("models/") != 0) {
        model_path = "models/" + model_path
    }

    local prop = null

    try {
        prop = SpawnEntityFromTable("prop_physics", {
            origin = spawn_pos,
            angles = Vector(0, 0, 0),
            model = model_path
        })
    } catch(e) {}

    if (prop == null) {
        try {
            prop = SpawnEntityFromTable("prop_dynamic", {
                origin = spawn_pos,
                angles = Vector(0, 0, 0),
                model = model_path,
                solid = 6
            })
        } catch(e) {}
    }

    if (prop != null) {
        SendResponse("spawned", model_path)
    } else {
        SendResponse("error", "spawn failed - invalid model or missing asset")
    }
}

function SendResponse(status, message) {
    local response = "{\\"status\\":\\"" + status + "\\",\\"message\\":\\"" + message + "\\"}"
    try {
        StringToFile("python_response.txt", response)
    } catch(e) {}
}

RegisterThinkFunction("python_bridge", CheckPythonCommand, 0.0)

if (!("g_master_think_active" in getroottable())) {
    ::g_master_think_active <- true
    try {
        local worldspawn = Entities.FindByClassname(null, "worldspawn")
        if (worldspawn != null) {
            worldspawn.SetContextThink("MasterThink", MasterThink, 0.0)
        }
    } catch(e) {}
}
"""

    def _get_vscript_server_script(self):
        """return complete vscript_server.nut script"""
        return """\
IncludeScript("auto_spawner.nut")
IncludeScript("picker.nut")
IncludeScript("python_listener.nut")
"""

    @staticmethod
    def looks_mapbase(path):
        """quick check if a path is the mapbase folder or sits beside it"""
        if not path:
            return False

        abs_path = os.path.abspath(path)
        base_name = os.path.basename(abs_path).lower()
        if base_name == "mapbase":
            return True

        parent_dir = os.path.dirname(abs_path)
        return os.path.isdir(os.path.join(parent_dir, "mapbase"))