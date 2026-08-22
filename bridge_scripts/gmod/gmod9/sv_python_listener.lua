-- bridge system - gmod 9
-- file-based communication for external control

SOURCEBOX = SOURCEBOX or {}
SOURCEBOX.Bridge = SOURCEBOX.Bridge or {}
local Bridge = SOURCEBOX.Bridge

Bridge.CommandFile = "data/sourcebox_command.txt"
Bridge.ResponseFile = "data/sourcebox_response.txt"
Bridge.SessionID = 0
Bridge.LastCommandID = 0
Bridge.CheckInterval = 0.1
Bridge.LastCheckTime = 0

local function InitializeBridge()
	_file.Write(Bridge.CommandFile, "")
	_file.Write(Bridge.ResponseFile, "")
end

local function SendResponse(status, message)
	local response = '{"status":"' .. status .. '","message":"' .. message .. '"}'
	_file.Write(Bridge.ResponseFile, response)
end

local function ParseJSON(str)
	local data = {}
	
	local s, e = string.find(str, '"session"%s*:%s*')
	if s then
		local numStart = e + 1
		local numEnd = numStart
		while numEnd <= string.len(str) do
			local char = string.sub(str, numEnd, numEnd)
			if char >= "0" and char <= "9" then
				numEnd = numEnd + 1
			else
				break
			end
		end
		data.session = tonumber(string.sub(str, numStart, numEnd - 1))
	end
	
	s, e = string.find(str, '"id"%s*:%s*')
	if s then
		local numStart = e + 1
		local numEnd = numStart
		while numEnd <= string.len(str) do
			local char = string.sub(str, numEnd, numEnd)
			if char >= "0" and char <= "9" then
				numEnd = numEnd + 1
			else
				break
			end
		end
		data.id = tonumber(string.sub(str, numStart, numEnd - 1))
	end
	
	s, e = string.find(str, '"command"%s*:%s*"')
	if s then
		local cmdStart = e + 1
		local cmdEnd = string.find(str, '"', cmdStart)
		if cmdEnd then
			data.command = string.sub(str, cmdStart, cmdEnd - 1)
		end
	end
	
	s, e = string.find(str, '"model"%s*:%s*"')
	if s then
		local modelStart = e + 1
		local modelEnd = string.find(str, '"', modelStart)
		if modelEnd then
			data.model = string.sub(str, modelStart, modelEnd - 1)
		end
	end
	
	s, e = string.find(str, '"distance"%s*:%s*')
	if s then
		local numStart = e + 1
		local numEnd = numStart
		while numEnd <= string.len(str) do
			local char = string.sub(str, numEnd, numEnd)
			if char >= "0" and char <= "9" then
				numEnd = numEnd + 1
			else
				break
			end
		end
		data.distance = tonumber(string.sub(str, numStart, numEnd - 1))
	end
	
	return data
end

local function GetPlayer()
	for i = 1, _MaxPlayers() do
		if IsPlayerOnline(i) and _PlayerInfo(i, "alive") then
			return i
		end
	end
	return nil
end

local function SpawnModelAtCrosshair(modelPath, distance)
	local ply = GetPlayer()
	if not ply then
		SendResponse("error", "no player found")
		return
	end
	
	distance = distance or 200
	
	local eyePos = _PlayerGetShootPos(ply)
	local forward = _PlayerGetShootAng(ply)
	local endPos = vecAdd(eyePos, vecMul(forward, distance))
	
	local dir = vecSub(endPos, eyePos)
	local length = vecLength(dir)
	dir.x = dir.x / length
	dir.y = dir.y / length
	dir.z = dir.z / length
	
	_TraceLine(eyePos, dir, length, ply)
	
	local spawnPos = endPos
	if _TraceHit() then
		spawnPos = _TraceEndPos()
	end
	spawnPos.z = spawnPos.z + 10
	
	if not string.find(modelPath, "models/") then
		modelPath = "models/" .. modelPath
	end
	
	_EntPrecacheModel(modelPath)
	
	local prop = _EntCreate("prop_physics")
	if not prop or not _EntExists(prop) then
		SendResponse("error", "failed to create entity")
		return
	end
	
	_EntSetModel(prop, modelPath)
	_EntSetPos(prop, spawnPos)
	_EntSetAngAngle(prop, vector3(0, math.random(0, 360), 0))
	_EntSetMoveType(prop, MOVETYPE_VPHYSICS)
	_EntSetSolid(prop, SOLID_VPHYSICS)
	
	_EntSpawn(prop)
	_EntActivate(prop)
	
	if _phys.HasPhysics(prop) then
		_phys.Wake(prop)
		_phys.EnableMotion(prop, true)
		_phys.SetMass(prop, 50)
		_phys.EnableGravity(prop, true)
		_phys.EnableCollisions(prop, true)
	end
	
	_EntSetCollisionGroup(prop, COLLISION_GROUP_NONE)
	
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
	local content = _file.Read(Bridge.CommandFile)
	if not content or content == "" then 
		return 
	end
	
	local data = ParseJSON(content)
	if not data.session or not data.id then 
		return 
	end
	
	-- session changed - reset command counter
	if Bridge.SessionID ~= 0 and data.session ~= Bridge.SessionID then
		Bridge.SessionID = data.session
		Bridge.LastCommandID = 0
	end
	
	-- first command - accept session
	if Bridge.SessionID == 0 then
		Bridge.SessionID = data.session
	end
	
	-- ignore old commands
	if data.id <= Bridge.LastCommandID then 
		return 
	end
	
	Bridge.LastCommandID = data.id
	_file.Write(Bridge.CommandFile, "")
	
	ExecuteCommand(data)
end

local function BridgeThink()
	if _CurTime() - Bridge.LastCheckTime >= Bridge.CheckInterval then
		CheckCommands()
		Bridge.LastCheckTime = _CurTime()
	end
end

InitializeBridge()
AddThinkFunction(BridgeThink)

CONCOMMAND("sourcebox_spawn", function(playerid, args)
	if not args or args == "" then
		_Msg("usage: sourcebox_spawn <model_path> [distance]\n")
		return
	end
	
	local spacePos = string.find(args, " ")
	local modelPath
	local distance = 200
	
	if spacePos then
		modelPath = string.sub(args, 1, spacePos - 1)
		local distStr = string.sub(args, spacePos + 1)
		distance = tonumber(distStr) or 200
	else
		modelPath = args
	end
	
	if not modelPath or modelPath == "" then
		_Msg("usage: sourcebox_spawn <model_path> [distance]\n")
		return
	end
	
	SpawnModelAtCrosshair(modelPath, distance)
end)
