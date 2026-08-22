if not SERVER then return end

SOURCEBOX.Picker = SOURCEBOX.Picker or {}
local Picker = SOURCEBOX.Picker

Picker.Enabled = Picker.Enabled or {}
Picker.Target = Picker.Target or {}
Picker.Manual = Picker.Manual or {}
Picker.Targets = Picker.Targets or {}
Picker.TargetIdx = Picker.TargetIdx or {}
Picker.ManualTime = Picker.ManualTime or {}

local MAX_DIST = 5000
local SMOOTH = 0.15
local MANUAL_TIMEOUT = 3.0

local function GetPlayerID(ply)
    if ply.UserID then return ply:UserID()
    elseif ply.UniqueID then return ply:UniqueID()
    else return tostring(ply) end
end

local function InitPlayer(ply)
    local id = GetPlayerID(ply)
    Picker.Enabled[id] = false
    Picker.Target[id] = nil
    Picker.Manual[id] = false
    Picker.Targets[id] = {}
    Picker.TargetIdx[id] = 0
    Picker.ManualTime[id] = 0
end

local function CanSee(ply, target, tpos)
    local start = ply:EyePos()
    local trace = {}
    trace.start = start
    trace.endpos = tpos
    trace.filter = ply
    local tr = util.TraceLine(trace)
    
    if tr.Entity == target then return true end
    if tr.HitPos and tr.HitPos:Distance(tpos) < 100 then return true end
    return false
end

local function IsNPC(ent)
    if not ent or not ent:IsValid() then return false end
    local class = ent:GetClass()
    local npc_classes = {"npc_", "monster_", "boss_"}
    for _, prefix in pairs(npc_classes) do
        if string.find(class, prefix) then return true end
    end
    if ent:IsNPC() then return true end
    return false
end

local function GetTargetPos(ent)
    if ent:IsPlayer() or IsNPC(ent) then
        return ent:EyePos()
    else
        return ent:GetPos()
    end
end

local function GetBest(ply)
    local pos = ply:EyePos()
    local bestNPC, bestPlayer, bestProp = nil, nil, nil
    local bestNPCDist, bestPlayerDist, bestPropDist = 999999, 999999, 999999
    
    for _, npc in pairs(ents.GetAll()) do
        if IsNPC(npc) and npc:IsValid() and npc:Health() > 0 then
            local tpos = GetTargetPos(npc)
            local dist = pos:Distance(tpos)
            if dist <= MAX_DIST and dist < bestNPCDist and CanSee(ply, npc, tpos) then
                bestNPCDist = dist
                bestNPC = npc
            end
        end
    end
    if bestNPC then return bestNPC end
    
    for _, target in pairs(player.GetAll()) do
        if target ~= ply and target:Alive() then
            local tpos = GetTargetPos(target)
            local dist = pos:Distance(tpos)
            if dist <= MAX_DIST and dist < bestPlayerDist and CanSee(ply, target, tpos) then
                bestPlayerDist = dist
                bestPlayer = target
            end
        end
    end
    if bestPlayer then return bestPlayer end
    
    for _, ent in pairs(ents.FindByClass("prop_physics*")) do
        local tpos = GetTargetPos(ent)
        local dist = pos:Distance(tpos)
        if dist <= MAX_DIST and dist < bestPropDist and CanSee(ply, ent, tpos) then
            bestPropDist = dist
            bestProp = ent
        end
    end
    
    return bestProp
end

local function CalcAngles(from, to)
    return (to - from):Angle()
end

local function NormAngle(a)
    while a > 180 do a = a - 360 end
    while a < -180 do a = a + 360 end
    return a
end

local function LerpAngle(from, to, amt)
    local d = NormAngle(to - from)
    return from + d * amt
end

local function Aim(ply, ent)
    local ppos = ply:EyePos()
    local tpos = GetTargetPos(ent)
    local want = CalcAngles(ppos, tpos)
    local cur = ply:EyeAngles()
    
    local dp = NormAngle(want.p - cur.p)
    local dy = NormAngle(want.y - cur.y)
    local td = math.sqrt(dp * dp + dy * dy)
    
    local smooth = SMOOTH
    if td < 5 then smooth = smooth * 0.6
    elseif td > 30 then smooth = smooth * 1.3 end
    
    local np = LerpAngle(cur.p, want.p, smooth)
    local ny = LerpAngle(cur.y, want.y, smooth)
    
    if np > 89 then np = 89 end
    if np < -89 then np = -89 end
    while ny > 180 do ny = ny - 360 end
    while ny < -180 do ny = ny + 360 end
    
    ply:SetEyeAngles(Angle(np, ny, 0))
end

local function PickerThink()
    for _, ply in pairs(player.GetAll()) do
        if ply:Alive() then
            local id = GetPlayerID(ply)
            if not Picker.Enabled[id] then InitPlayer(ply) end
            
            if Picker.Enabled[id] then
                if Picker.Manual[id] and CurTime() - Picker.ManualTime[id] > MANUAL_TIMEOUT then
                    Picker.Manual[id] = false
                end
                
                if not Picker.Manual[id] then
                    local nt = GetBest(ply)
                    if nt then Picker.Target[id] = nt end
                end
                
                if Picker.Target[id] and Picker.Target[id]:IsValid() then
                    Aim(ply, Picker.Target[id])
                end
            end
        end
    end
end

local function Toggle(ply)
    local id = GetPlayerID(ply)
    if not Picker.Enabled[id] then InitPlayer(ply) end
    Picker.Enabled[id] = not Picker.Enabled[id]
    Picker.Target[id] = nil
    Picker.Manual[id] = false
end

local function NextTarget(ply)
    local id = GetPlayerID(ply)
    if not Picker.Enabled[id] or not ply:Alive() then return end
    
    Picker.Manual[id] = true
    Picker.ManualTime[id] = CurTime()
    
    local list = {}
    local pos = ply:EyePos()
    for _, npc in pairs(ents.GetAll()) do
        if IsNPC(npc) and npc:IsValid() and npc:Health() > 0 then
            local tpos = GetTargetPos(npc)
            local dist = pos:Distance(tpos)
            if dist <= MAX_DIST and CanSee(ply, npc, tpos) then
                table.insert(list, npc)
            end
        end
    end
    for _, target in pairs(player.GetAll()) do
        if target ~= ply and target:Alive() then
            local tpos = GetTargetPos(target)
            local dist = pos:Distance(tpos)
            if dist <= MAX_DIST and CanSee(ply, target, tpos) then
                table.insert(list, target)
            end
        end
    end
    for _, ent in pairs(ents.FindByClass("prop_physics*")) do
        local tpos = GetTargetPos(ent)
        local dist = pos:Distance(tpos)
        if dist <= MAX_DIST and CanSee(ply, ent, tpos) then
            table.insert(list, ent)
        end
    end
    
    Picker.Targets[id] = list
    if #Picker.Targets[id] > 0 then
        Picker.TargetIdx[id] = Picker.TargetIdx[id] + 1
        if Picker.TargetIdx[id] > #Picker.Targets[id] then
            Picker.TargetIdx[id] = 1
        end
        Picker.Target[id] = Picker.Targets[id][Picker.TargetIdx[id]]
    end
end

hook.Add("Think", "SourceBox_Picker", PickerThink)

concommand.Add("picker_toggle", function(ply)
    if ply:IsValid() then Toggle(ply) end
end)

concommand.Add("picker_next", function(ply)
    if ply:IsValid() then NextTarget(ply) end
end)

print("[Picker] Loaded - Commands: picker_toggle, picker_next")
print("[Picker] Targets: NPCs (priority), Players, Props")
