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
