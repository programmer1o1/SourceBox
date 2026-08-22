
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

::InitPlayer <- function(p)
{
    local id = p.GetEntityIndex().tostring();
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
        spawnflags = 0
    });
    
    if (txt != null)
    {
        EntFireByHandle(txt, "Display", "", 0.0, p, p);
        EntFireByHandle(txt, "Kill", "", 0.6, null, null);
    }
}

::ClearHud <- function(p)
{
    local txt = SpawnEntityFromTable("game_text", {
        message = "",
        channel = 1,
        x = -1,
        y = 0.53,
        holdtime = 0
    });
    
    if (txt != null)
    {
        EntFireByHandle(txt, "Display", "", 0.0, p, p);
        EntFireByHandle(txt, "Kill", "", 0.01, null, null);
    }
}

::Toggle <- function(p)
{
    local id = p.GetEntityIndex().tostring();
    
    if (!(id in g_enabled))
        InitPlayer(p);
    
    g_enabled[id] = !g_enabled[id];
    g_target[id] = null;
    g_manual[id] = false;
    g_targetidx[id] = 0;
    g_manualtime[id] = 0.0;
    g_targets[id] = [];
    
    if (!g_enabled[id])
        ClearHud(p);
}

::NextTarget <- function(p)
{
    local id = p.GetEntityIndex().tostring();
    
    if (!(id in g_enabled) || !g_enabled[id] || !p.IsAlive())
        return;
    
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
    
    return CanSee(p, e, e.GetOrigin());
}

::GetBest <- function(p)
{
    local team = p.GetTeam();
    local pos = p.EyePosition();
    local teamplay = DetectTeamplay();
    
    local bestEnemy = null;
    local bestTeam = null;
    local bestProp = null;
    local bestEDist = 999999.0;
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
    
    if (bestEnemy != null)
        return bestEnemy;
    
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
    local trace = {
        start = start,
        end = tpos,
        ignore = p
    };
    
    TraceLineEx(trace);
    
    if ("enthit" in trace && trace.enthit == t)
        return true;
    
    if ("pos" in trace)
    {
        local d = (trace.pos - tpos).Length();
        if (d < 100.0)
            return true;
    }
    
    return false;
}

::CalcAngles <- function(from, to)
{
    local d = to - from;
    local h = d.Length();
    
    if (h < 0.001)
        return QAngle(0, 0, 0);
    
    local pitch = asin(-d.z / h) * (180.0 / 3.14159);
    local yaw = atan2(d.y, d.x) * (180.0 / 3.14159);
    
    return QAngle(pitch, yaw, 0);
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
    local tpos = e.GetClassname() == "player" ? e.EyePosition() : e.GetOrigin();
    
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
    
    p.SnapEyeAngles(QAngle(np, ny, 0));
}

::PickerThink <- function()
{
    local t = Time();
    
    local p = null;
    try { p = GetListenServerHost() } catch(e) {}
    if (p == null) { 
        try { p = Entities.FindByClassname(null, "player") } catch(e) {} 
    }
    
    if (p == null || !p.IsAlive()) {
        return 0.015;
    }
    
    local id = p.GetEntityIndex().tostring();
    
    if (!(id in g_enabled))
        InitPlayer(p);
    
    if (t - g_lasthud[id] > 0.54)
    {
        if (g_enabled[id])
            ShowHud(p, "PICKER ON");
        else
            ClearHud(p);
        
        g_lasthud[id] = t;
    }
    
    if (!g_enabled[id])
        return 0.015;
    
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

::OnGameEvent_round_start <- function(params)
{
    g_teamplay = null;
    
    foreach (id, _ in g_enabled)
    {
        g_target[id] = null;
        g_manual[id] = false;
        g_targetidx[id] = 0;
        g_manualtime[id] = 0.0;
        g_targets[id] = [];
    }
}

__CollectGameEventCallbacks(this);

::PickerToggle <- function() {
    local player = null
    try { player = GetListenServerHost() } catch(e) {}
    if (player == null) { try { player = Entities.FindByClassname(null, "player") } catch(e) {} }
    if (player != null) Toggle(player)
}

::PickerNext <- function() {
    local player = null
    try { player = GetListenServerHost() } catch(e) {}
    if (player == null) { try { player = Entities.FindByClassname(null, "player") } catch(e) {} }
    if (player != null) NextTarget(player)
}

if ("RegisterThinkFunction" in getroottable()) {
    RegisterThinkFunction("picker", PickerThink, 0.0)
} else {
    ::DelayedRegisterPicker <- function() {
        if ("RegisterThinkFunction" in getroottable()) {
            RegisterThinkFunction("picker", PickerThink, 0.0)
        }
    }
    
    DoEntFire("worldspawn", "RunScriptCode", "DelayedRegisterPicker()", 1.0, null, null)
}
