if not SERVER then return end

SOURCEBOX.Bridge = SOURCEBOX.Bridge or {}
local Bridge = SOURCEBOX.Bridge

Bridge.CommandFile = "sourcebox_command.txt"
Bridge.ResponseFile = "sourcebox_response.txt"
Bridge.SessionID = 0
Bridge.LastCommandID = 0
Bridge.CheckInterval = 0.1

local function InitializeBridge()
    Bridge.SessionID = os.time()
    SOURCEBOX.WriteFile(Bridge.CommandFile, "")
    SOURCEBOX.WriteFile(Bridge.ResponseFile, "")
    print("[Bridge] Initialized - Session: " .. Bridge.SessionID)
end

local function SendResponse(status, message)
    local response = '{"status":"' .. status .. '","message":"' .. message .. '"}'
    SOURCEBOX.WriteFile(Bridge.ResponseFile, response)
end

local function ParseJSON(str)
    local data = {}
    local session = string.match(str, '"session"%s*:%s*(%d+)')
    if session then data.session = tonumber(session) end
    local id = string.match(str, '"id"%s*:%s*(%d+)')
    if id then data.id = tonumber(id) end
    local command = string.match(str, '"command"%s*:%s*"([^"]+)"')
    if command then data.command = command end
    local model = string.match(str, '"model"%s*:%s*"([^"]+)"')
    if model then data.model = model end
    local distance = string.match(str, '"distance"%s*:%s*(%d+)')
    if distance then data.distance = tonumber(distance) end
    return data
end

local function GetPlayer()
    if player and player.GetAll then
        local players = player.GetAll()
        if #players > 0 then return players[1] end
    end
    return nil
end

local function SpawnModelAtCrosshair(modelPath, distance)
    local ply = GetPlayer()
    if not ply or not ply:IsValid() then
        SendResponse("error", "no player found")
        return
    end
    
    distance = distance or 200
    
    local eyePos = ply:EyePos()
    local eyeAngles = ply:EyeAngles()
    local forward = eyeAngles:Forward()
    local endPos = eyePos + (forward * distance)
    
    local trace = {}
    trace.start = eyePos
    trace.endpos = endPos
    trace.filter = ply
    
    local tr = util.TraceLine(trace)
    local spawnPos = tr.HitPos or endPos
    spawnPos.z = spawnPos.z + 10
    
    if not string.find(modelPath, "models/") then
        modelPath = "models/" .. modelPath
    end
    
    local prop = ents.Create("prop_physics")
    if not prop or not prop:IsValid() then
        SendResponse("error", "failed to create entity")
        return
    end
    
    prop:SetModel(modelPath)
    prop:SetPos(spawnPos)
    prop:SetAngles(Angle(0, math.random(0, 360), 0))
    prop:SetMoveType(MOVETYPE_VPHYSICS)
    prop:SetSolid(SOLID_VPHYSICS)
    prop:PhysicsInit(SOLID_VPHYSICS)
    prop:Spawn()
    prop:Activate()
    
    local phys = prop:GetPhysicsObject()
    if phys:IsValid() then
        phys:Wake()
        phys:EnableMotion(true)
        phys:SetMass(50)
    end
    
    prop:SetCollisionGroup(COLLISION_GROUP_NONE)
    
    if prop.SetNoDraw then prop:SetNoDraw(false) end
    if prop.SetNotSolid then prop:SetNotSolid(false) end
    if prop.SetRenderMode then prop:SetRenderMode(RENDERMODE_NORMAL) end
    if prop.DrawShadow then prop:DrawShadow(true) end
    if prop.SetNetworked then prop:SetNetworked(true) end
    if prop.UpdateTransmitState then prop:UpdateTransmitState() end
    
    SendResponse("spawned", modelPath)
end

local function ExecuteCommand(data)
    if not data.command then
        SendResponse("error", "no command")
        return
    end
    
    if data.command == "spawn_model" then
        if not data.model or data.model == "" then
            SendResponse("error", "no model specified")
            return
        end
        SpawnModelAtCrosshair(data.model, data.distance)
    elseif data.command == "ping" then
        SendResponse("success", "pong")
    else
        SendResponse("error", "unknown command: " .. data.command)
    end
end

local function CheckCommands()
    local content = SOURCEBOX.ReadFile(Bridge.CommandFile)
    if not content or content == "" then return end
    
    local data = ParseJSON(content)
    if not data.session or not data.id then return end
    
    if Bridge.SessionID > 0 and data.session ~= Bridge.SessionID then
        Bridge.SessionID = data.session
        Bridge.LastCommandID = 0
    end
    
    if data.id <= Bridge.LastCommandID then return end
    Bridge.LastCommandID = data.id
    
    SOURCEBOX.WriteFile(Bridge.CommandFile, "")
    
    ExecuteCommand(data)
end

InitializeBridge()

if timer and timer.Create then
    timer.Create("SourceBox_Bridge", Bridge.CheckInterval, 0, CheckCommands)
else
    local lastCheck = CurTime()
    hook.Add("Think", "SourceBox_Bridge", function()
        if CurTime() - lastCheck >= Bridge.CheckInterval then
            CheckCommands()
            lastCheck = CurTime()
        end
    end)
end

concommand.Add("sourcebox_spawn", function(ply, cmd, args)
    if #args < 1 then
        print("Usage: sourcebox_spawn <model_path> [distance]")
        return
    end
    SpawnModelAtCrosshair(args[1], tonumber(args[2]) or 200)
end)

print("[Bridge] Python communication ready")
