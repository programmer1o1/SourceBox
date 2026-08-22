-- picker (aimbot) system - gmod 9
-- smooth target switching, extensive npc support

SOURCEBOX = SOURCEBOX or {}
SOURCEBOX.Picker = SOURCEBOX.Picker or {}
local Picker = SOURCEBOX.Picker

-- state
Picker.Enabled = Picker.Enabled or {}
Picker.Target = Picker.Target or {}
Picker.Manual = Picker.Manual or {}
Picker.Targets = Picker.Targets or {}
Picker.TargetIdx = Picker.TargetIdx or {}
Picker.ManualTime = Picker.ManualTime or {}
Picker.LastAngles = Picker.LastAngles or {}
Picker.TargetSwitchTime = Picker.TargetSwitchTime or {}

-- constants
local MAX_DIST = 5000
local SMOOTH_BASE = 0.12
local SMOOTH_FAST = 0.30
local SMOOTH_SWITCH = 0.06
local SMOOTH_SNAP = 2.0
local SWITCH_SMOOTH_DURATION = 0.5
local MANUAL_TIMEOUT = 3.0
local PI = 3.14159265359

-- npc class definitions
local NPC_CLASSES = {
	"npc_combine_s", "npc_combine", "npc_combine_e", "npc_combine_p",
	"npc_metropolice", "npc_combinegunship", "npc_helicopter",
	"npc_combinedropship", "npc_strider", "npc_apcdriver",
	"npc_combine_camera", "npc_turret_floor", "npc_turret_ceiling",
	"npc_turret_ground", "npc_zombie", "npc_zombie_torso",
	"npc_poisonzombie", "npc_fastzombie", "npc_fastzombie_torso",
	"npc_zombine", "npc_headcrab", "npc_headcrab_fast",
	"npc_headcrab_black", "npc_headcrab_poison", "npc_antlion",
	"npc_antlion_worker", "npc_antlionguard", "npc_antlion_grub",
	"npc_vortigaunt", "npc_vortigaunt_slave", "npc_manhack",
	"npc_stalker", "npc_barnacle", "npc_rollermine", "npc_cscanner",
	"npc_clawscanner", "npc_hunter", "npc_sniper", "npc_citizen",
	"npc_alyx", "npc_barney", "npc_monk", "npc_dog", "npc_eli",
	"npc_gman", "npc_kleiner", "npc_magnusson", "npc_mossman",
	"npc_breen", "npc_crow", "npc_pigeon", "npc_seagull",
	"npc_ichthyosaur", "monster_alien_controller", "monster_alien_grunt",
	"monster_alien_slave", "monster_babycrab", "monster_barnacle",
	"monster_barney", "monster_bigmomma", "monster_bloater",
	"monster_bullchicken", "monster_gargantua", "monster_generic",
	"monster_gman", "monster_headcrab", "monster_houndeye",
	"monster_human_assassin", "monster_human_grunt", "monster_ichthyosaur",
	"monster_leech", "monster_scientist", "monster_sentry",
	"monster_snark", "monster_tentacle", "monster_turret",
	"monster_zombie", "boss_", "npc_", "monster_"
}

local function GetPlayerID(ply)
	return ply
end

local function InitPlayer(ply)
	local id = GetPlayerID(ply)
	Picker.Enabled[id] = false
	Picker.Target[id] = nil
	Picker.Manual[id] = false
	Picker.Targets[id] = {}
	Picker.TargetIdx[id] = 0
	Picker.ManualTime[id] = 0
	Picker.LastAngles[id] = vector3(0, 0, 0)
	Picker.TargetSwitchTime[id] = 0
end

local function CanSee(ply, target, tpos)
	local start = _PlayerGetShootPos(ply)
	local dir = vecSub(tpos, start)
	local length = vecLength(dir)
	
	if length < 0.001 then return false end
	
	dir.x = dir.x / length
	dir.y = dir.y / length
	dir.z = dir.z / length
	
	_TraceLine(start, dir, length, ply)
	
	if not _TraceHit() then
		return true
	end
	
	local hitEnt = _TraceGetEnt()
	if hitEnt == target then
		return true
	end
	
	local hitPos = _TraceEndPos()
	if hitPos then
		local d = vecLength(vecSub(hitPos, tpos))
		if d < 200 then
			return true
		end
	end
	
	return false
end

local function IsNPC(ent)
	if not ent or ent <= 0 then return false end
	if IsPlayer(ent) then return false end
	if not _EntExists(ent) then return false end
	
	local class = _EntGetType(ent)
	if not class then return false end
	
	for _, npcClass in pairs(NPC_CLASSES) do
		if string.find(class, npcClass) then
			return true
		end
	end
	
	return false
end

local function IsProp(ent)
	if not ent or ent <= 0 then return false end
	if IsPlayer(ent) then return false end
	if not _EntExists(ent) then return false end
	
	local class = _EntGetType(ent)
	if not class then return false end
	
	return (string.find(class, "prop_physics") ~= nil or 
	        string.find(class, "prop_dynamic") ~= nil or
	        string.find(class, "prop_ragdoll") ~= nil)
end

local function GetTargetPos(ent)
	if IsPlayer(ent) then
		return _PlayerGetShootPos(ent)
	end
	
	local pos = _EntGetPos(ent)
	
	if IsNPC(ent) then
		return vecAdd(pos, vector3(0, 0, 36))
	end
	
	return pos
end

local function GetAllEntities()
	local allEnts = {}
	local found = {}
	
	for _, npcClass in pairs(NPC_CLASSES) do
		local ents = _EntitiesFindByClass(npcClass)
		if ents then
			for _, ent in pairs(ents) do
				if _EntExists(ent) and not found[ent] then
					table.insert(allEnts, ent)
					found[ent] = true
				end
			end
		end
	end
	
	local propClasses = {"prop_physics", "prop_dynamic", "prop_ragdoll"}
	for _, class in pairs(propClasses) do
		local props = _EntitiesFindByClass(class)
		if props then
			for _, prop in pairs(props) do
				if _EntExists(prop) and not found[prop] then
					table.insert(allEnts, prop)
					found[prop] = true
				end
			end
		end
	end
	
	return allEnts
end

local function BuildList(ply)
	local list = {}
	local pos = _PlayerGetShootPos(ply)
	local allEnts = GetAllEntities()
	
	for _, ent in pairs(allEnts) do
		if IsNPC(ent) and _EntExists(ent) then
			local tpos = GetTargetPos(ent)
			local dist = vecLength(vecSub(tpos, pos))
			
			if dist <= MAX_DIST and CanSee(ply, ent, tpos) then
				table.insert(list, ent)
			end
		end
	end
	
	for i = 1, _MaxPlayers() do
		if IsPlayerOnline(i) and i ~= ply and _PlayerInfo(i, "alive") then
			local tpos = GetTargetPos(i)
			local dist = vecLength(vecSub(tpos, pos))
			
			if dist <= MAX_DIST and CanSee(ply, i, tpos) then
				table.insert(list, i)
			end
		end
	end
	
	for _, ent in pairs(allEnts) do
		if IsProp(ent) and _EntExists(ent) then
			local tpos = GetTargetPos(ent)
			local dist = vecLength(vecSub(tpos, pos))
			
			if dist <= MAX_DIST and CanSee(ply, ent, tpos) then
				table.insert(list, ent)
			end
		end
	end
	
	return list
end

local function GetBest(ply)
	local pos = _PlayerGetShootPos(ply)
	local bestNPC = nil
	local bestPlayer = nil
	local bestProp = nil
	local bestNPCDist = 999999
	local bestPlayerDist = 999999
	local bestPropDist = 999999
	local allEnts = GetAllEntities()
	
	for _, ent in pairs(allEnts) do
		if IsNPC(ent) and _EntExists(ent) then
			local tpos = GetTargetPos(ent)
			local dist = vecLength(vecSub(tpos, pos))
			
			if dist <= MAX_DIST and dist < bestNPCDist and CanSee(ply, ent, tpos) then
				bestNPCDist = dist
				bestNPC = ent
			end
		end
	end
	
	if bestNPC then return bestNPC end
	
	for i = 1, _MaxPlayers() do
		if IsPlayerOnline(i) and i ~= ply and _PlayerInfo(i, "alive") then
			local tpos = GetTargetPos(i)
			local dist = vecLength(vecSub(tpos, pos))
			
			if dist <= MAX_DIST and dist < bestPlayerDist and CanSee(ply, i, tpos) then
				bestPlayerDist = dist
				bestPlayer = i
			end
		end
	end
	
	if bestPlayer then return bestPlayer end
	
	for _, ent in pairs(allEnts) do
		if IsProp(ent) and _EntExists(ent) then
			local tpos = GetTargetPos(ent)
			local dist = vecLength(vecSub(tpos, pos))
			
			if dist <= MAX_DIST and dist < bestPropDist and CanSee(ply, ent, tpos) then
				bestPropDist = dist
				bestProp = ent
			end
		end
	end
	
	return bestProp
end

local function CalcAngles(from, to)
	local diff = vecSub(to, from)
	local length = vecLength(diff)
	
	if length < 0.001 then
		return vector3(0, 0, 0)
	end
	
	diff.x = diff.x / length
	diff.y = diff.y / length
	diff.z = diff.z / length
	
	local pitch = math.asin(-diff.z) * (180.0 / PI)
	local yaw = math.atan2(diff.y, diff.x) * (180.0 / PI)
	
	return vector3(pitch, yaw, 0)
end

local function NormAngle(a)
	while a > 180 do a = a - 360 end
	while a < -180 do a = a + 360 end
	return a
end

local function LerpAngleSmooth(from, to, amt)
	local d = NormAngle(to - from)
	local t = 1 - amt
	local eased = 1 - (t * t * t)
	return from + d * eased
end

local function Aim(ply, ent)
	local ppos = _PlayerGetShootPos(ply)
	local tpos = GetTargetPos(ent)
	local want = CalcAngles(ppos, tpos)
	local cur = _EntGetAngAngle(ply)
	local id = GetPlayerID(ply)
	
	if not Picker.LastAngles[id] then
		Picker.LastAngles[id] = cur
	end
	
	local dp = NormAngle(want.x - cur.x)
	local dy = NormAngle(want.y - cur.y)
	local td = math.sqrt(dp * dp + dy * dy)
	
	local timeSinceSwitch = _CurTime() - (Picker.TargetSwitchTime[id] or 0)
	local justSwitched = timeSinceSwitch < SWITCH_SMOOTH_DURATION
	
	local smooth = SMOOTH_BASE
	
	if justSwitched then
		smooth = SMOOTH_SWITCH
	elseif td < SMOOTH_SNAP then
		smooth = 1.0
	elseif td < 10 then
		smooth = SMOOTH_FAST
	else
		local falloff = math.min(td / 60.0, 1.0)
		smooth = SMOOTH_BASE * (1.0 - falloff * 0.5)
	end
	
	local np = LerpAngleSmooth(cur.x, want.x, smooth)
	local ny = LerpAngleSmooth(cur.y, want.y, smooth)
	
	if np > 89 then np = 89 end
	if np < -89 then np = -89 end
	
	ny = NormAngle(ny)
	
	Picker.LastAngles[id] = vector3(np, ny, 0)
	_EntSetAngAngle(ply, vector3(np, ny, 0))
end

local function PickerThink()
	for i = 1, _MaxPlayers() do
		if IsPlayerOnline(i) and _PlayerInfo(i, "alive") then
			local id = GetPlayerID(i)
			
			if not Picker.Enabled[id] then
				InitPlayer(i)
			end
			
			if Picker.Enabled[id] then
				if Picker.Manual[id] and _CurTime() - Picker.ManualTime[id] > MANUAL_TIMEOUT then
					Picker.Manual[id] = false
					Picker.Target[id] = nil
				end
				
				if not Picker.Manual[id] or not Picker.Target[id] or not _EntExists(Picker.Target[id]) then
					if not Picker.Manual[id] then
						local nt = GetBest(i)
						if nt and nt ~= Picker.Target[id] then
							Picker.TargetSwitchTime[id] = _CurTime()
							Picker.Target[id] = nt
						end
					end
				end
				
				if Picker.Target[id] and _EntExists(Picker.Target[id]) then
					Aim(i, Picker.Target[id])
				end
			end
		end
	end
end

local function Toggle(ply)
	local id = GetPlayerID(ply)
	
	if not Picker.Enabled[id] then
		InitPlayer(ply)
	end
	
	Picker.Enabled[id] = not Picker.Enabled[id]
	Picker.Target[id] = nil
	Picker.Manual[id] = false
end

local function NextTarget(ply)
	local id = GetPlayerID(ply)
	
	if not Picker.Enabled[id] then
		return
	end
	
	if not _PlayerInfo(ply, "alive") then
		return
	end
	
	Picker.Manual[id] = true
	Picker.ManualTime[id] = _CurTime()
	Picker.Targets[id] = BuildList(ply)
	
	if table.getn(Picker.Targets[id]) > 0 then
		Picker.TargetIdx[id] = Picker.TargetIdx[id] + 1
		if Picker.TargetIdx[id] > table.getn(Picker.Targets[id]) then
			Picker.TargetIdx[id] = 1
		end
		
		local newTarget = Picker.Targets[id][Picker.TargetIdx[id]]
		
		if newTarget ~= Picker.Target[id] then
			Picker.TargetSwitchTime[id] = _CurTime()
		end
		
		Picker.Target[id] = newTarget
	end
end

AddThinkFunction(PickerThink)

CONCOMMAND("picker_toggle", function(args)
	for i = 1, _MaxPlayers() do
		if IsPlayerOnline(i) then
			Toggle(i)
		end
	end
end)

CONCOMMAND("picker_next", function(args)
	for i = 1, _MaxPlayers() do
		if IsPlayerOnline(i) then
			NextTarget(i)
		end
	end
end)
