if not SERVER then return end

SOURCEBOX.Spawner = SOURCEBOX.Spawner or {}
local Spawner = SOURCEBOX.Spawner

local CUBE_MODEL = "models/props/srcbox/srcbox.mdl"
local spawned_cubes = {}
local spawn_initialized = false
local spawn_attempts = 0

local function IsPositionReachable(pos)
    local traceDown = {}
    traceDown.start = pos + Vector(0, 0, 10)
    traceDown.endpos = pos + Vector(0, 0, -500)
    local tr = util.TraceLine(traceDown)
    if not tr.Hit then return false end
    
    local groundPos = tr.HitPos
    local heightAboveGround = pos.z - groundPos.z
    if heightAboveGround > 150 or heightAboveGround < -50 then return false end
    return true
end

local function FindNearPlayerSpawn()
    local spawns = ents.FindByClass("info_player_*")
    if #spawns == 0 then spawns = ents.FindByClass("info_player_deathmatch") end
    if #spawns == 0 then spawns = ents.FindByClass("info_player_start") end
    if #spawns == 0 then return nil end
    
    local spawn = spawns[math.random(1, #spawns)]
    local spawnPos = spawn:GetPos()
    
    local distances = {300, 500, 700}
    local angles = {0, 45, 90, 135, 180, 225, 270, 315}
    
    for _, dist in pairs(distances) do
        for _, ang in pairs(angles) do
            local rad = math.rad(ang)
            local testPos = Vector(
                spawnPos.x + math.cos(rad) * dist,
                spawnPos.y + math.sin(rad) * dist,
                spawnPos.z + 50
            )
            if IsPositionReachable(testPos) then return testPos end
        end
    end
    return nil
end

local function SpawnCubeAtPosition(pos)
    local cube = ents.Create("prop_physics")
    if not cube or not cube:IsValid() then return nil end
    
    cube:SetModel(CUBE_MODEL)
    cube:SetPos(pos)
    cube:SetAngles(Angle(0, math.random(0, 360), 0))
    cube:SetMoveType(MOVETYPE_VPHYSICS)
    cube:SetSolid(SOLID_VPHYSICS)
    cube:PhysicsInit(SOLID_VPHYSICS)
    cube:Spawn()
    cube:Activate()
    
    local phys = cube:GetPhysicsObject()
    if phys:IsValid() then
        phys:Wake()
        phys:EnableMotion(true)
        phys:SetMass(50)
    end
    
    cube:SetCollisionGroup(COLLISION_GROUP_NONE)
    if cube.SetNoDraw then cube:SetNoDraw(false) end
    if cube.SetNotSolid then cube:SetNotSolid(false) end
    if cube.SetRenderMode then cube:SetRenderMode(RENDERMODE_NORMAL) end
    if cube.DrawShadow then cube:DrawShadow(true) end
    if cube.SetNetworked then cube:SetNetworked(true) end
    if cube.UpdateTransmitState then cube:UpdateTransmitState() end
    
    return cube
end

local function InitializeSpawner()
    if spawn_initialized then return end
    spawn_attempts = spawn_attempts + 1
    
    local spawnPos = FindNearPlayerSpawn()
    if spawnPos then
        local cube = SpawnCubeAtPosition(spawnPos)
        if cube then
            table.insert(spawned_cubes, cube)
            spawn_initialized = true
            print("[Auto-Spawner] Cube spawned at " .. tostring(spawnPos))
            return
        end
    end
    
    if spawn_attempts >= 6 then
        spawn_initialized = true
    end
end

if timer and timer.Simple then
    timer.Simple(3, InitializeSpawner)
else
    local initTime = CurTime() + 3
    hook.Add("Think", "SourceBox_SpawnerInit", function()
        if CurTime() >= initTime then
            InitializeSpawner()
            hook.Remove("Think", "SourceBox_SpawnerInit")
        end
    end)
end

print("[Auto-Spawner] Loaded")
