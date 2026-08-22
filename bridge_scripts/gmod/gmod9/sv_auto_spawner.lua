-- auto-spawner system - gmod 9

SOURCEBOX = SOURCEBOX or {}
SOURCEBOX.Spawner = SOURCEBOX.Spawner or {}
local Spawner = SOURCEBOX.Spawner

local CUBE_MODEL = "models/props/srcbox/srcbox.mdl"
local spawned_cubes = {}
local spawn_initialized = false
local spawn_attempts = 0

local function IsPositionReachable(pos)
	local start = vecAdd(pos, vector3(0, 0, 10))
	local endpos = vecAdd(pos, vector3(0, 0, -500))
	local dir = vecSub(endpos, start)
	local length = vecLength(dir)
	
	dir.x = dir.x / length
	dir.y = dir.y / length
	dir.z = dir.z / length
	
	_TraceLine(start, dir, length)
	
	if not _TraceHit() then return false end
	
	local groundPos = _TraceEndPos()
	local heightAboveGround = pos.z - groundPos.z
	
	if heightAboveGround > 150 or heightAboveGround < -50 then return false end
	
	return true
end

local function FindNearPlayerSpawn()
	local spawns = _EntitiesFindByClass("info_player_deathmatch")
	if not spawns or table.getn(spawns) == 0 then
		spawns = _EntitiesFindByClass("info_player_start")
	end
	if not spawns or table.getn(spawns) == 0 then
		spawns = _EntitiesFindByClass("info_player_teamspawn")
	end
	if not spawns or table.getn(spawns) == 0 then
		spawns = _EntitiesFindByClass("info_player_combine")
	end
	if not spawns or table.getn(spawns) == 0 then
		spawns = _EntitiesFindByClass("info_player_rebel")
	end
	if not spawns or table.getn(spawns) == 0 then return nil end
	
	local spawnCount = table.getn(spawns)
	local spawn = spawns[math.random(1, spawnCount)]
	local spawnPos = _EntGetPos(spawn)
	
	local distances = {300, 500, 700}
	local angles = {0, 45, 90, 135, 180, 225, 270, 315}
	
	for _, dist in pairs(distances) do
		for _, ang in pairs(angles) do
			local rad = math.rad(ang)
			local testPos = vector3(
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
	_EntPrecacheModel(CUBE_MODEL)
	
	local cube = _EntCreate("prop_physics")
	if not cube or not _EntExists(cube) then return nil end
	
	_EntSetModel(cube, CUBE_MODEL)
	_EntSetPos(cube, pos)
	_EntSetAngAngle(cube, vector3(0, math.random(0, 360), 0))
	_EntSetMoveType(cube, MOVETYPE_VPHYSICS)
	_EntSetSolid(cube, SOLID_VPHYSICS)
	
	_EntSpawn(cube)
	_EntActivate(cube)
	
	if _phys.HasPhysics(cube) then
		_phys.Wake(cube)
		_phys.EnableMotion(cube, true)
		_phys.SetMass(cube, 50)
		_phys.EnableGravity(cube, true)
		_phys.EnableCollisions(cube, true)
	end
	
	_EntSetCollisionGroup(cube, COLLISION_GROUP_NONE)
	
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
			return
		end
	end
	
	if spawn_attempts >= 6 then
		spawn_initialized = true
	end
end

AddTimer(3, 1, InitializeSpawner)
