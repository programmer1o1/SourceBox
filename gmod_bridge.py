"""
Garry's Mod Bridge for SourceBox (GMod 9-13)
Automatically installs Lua addon to sourcemods and retail installs
"""

import os
import json
import time
import platform
import re
import psutil

class GModBridge:
    # gmod versions as sourcemods (9-12)
    GMOD_SOURCEMODS = {
        'gmod9': 'GMod 9',
        'garrysmod10classic': 'GMod 10 Classic',
        'garrysmod': 'GMod 11',
        'garrysmod12': 'GMod 12'
    }

    # retail gmod 13 install (steamapps/common/GarrysMod/garrysmod)
    GMOD_RETAIL = {
        'gmod13': {
            'name': 'GMod 13',
            'install_dir': 'GarrysMod',
            'game_dir': 'garrysmod'
        }
    }
    
    def __init__(self):
        self.data_path = None
        self.addon_path = None
        self.command_file = None
        self.response_file = None
        self.session_id = int(time.time())
        self.command_id = 0
        self.active_gmod = None
        self.gmod_version = None
        self.is_gmod9 = False
        
        self._detect_gmod()
    
    def _get_steam_path_from_process(self):
        """detect steam from running process"""
        try:
            for proc in psutil.process_iter(['name', 'exe']):
                try:
                    proc_name = proc.info['name']
                    if proc_name and proc_name.lower() in ['steam.exe', 'steam']:
                        exe_path = proc.info.get('exe')
                        if exe_path and os.path.exists(exe_path):
                            steam_dir = os.path.dirname(exe_path)
                            if os.path.exists(os.path.join(steam_dir, 'steamapps')):
                                return steam_dir
                            
                            parent_dir = os.path.dirname(steam_dir)
                            if os.path.exists(os.path.join(parent_dir, 'steamapps')):
                                return parent_dir
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    continue
        except:
            pass
        return None
    
    def _get_steam_install_path(self):
        """get steam installation directory"""
        system = platform.system()
        
        if system == 'Windows':
            try:
                import winreg
                registry_paths = [
                    r"SOFTWARE\Wow6432Node\Valve\Steam",
                    r"SOFTWARE\Valve\Steam"
                ]
                
                for reg_path in registry_paths:
                    try:
                        hkey = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, reg_path)
                        install_path, _ = winreg.QueryValueEx(hkey, "InstallPath")
                        winreg.CloseKey(hkey)
                        if install_path and os.path.exists(install_path):
                            return install_path
                    except (FileNotFoundError, OSError):
                        continue
            except ImportError:
                pass
            
            process_path = self._get_steam_path_from_process()
            if process_path:
                return process_path
            
            for path in [r"C:\Program Files (x86)\Steam", r"C:\Program Files\Steam"]:
                if os.path.exists(path):
                    return path
            
        elif system == 'Linux':
            for path in ["~/.local/share/Steam", "~/.steam/steam", "~/.steam/root"]:
                expanded = os.path.expanduser(path)
                if os.path.islink(expanded):
                    expanded = os.path.realpath(expanded)
                if os.path.exists(expanded):
                    return expanded
            
            flatpak_steam = "~/.var/app/com.valvesoftware.Steam/.local/share/Steam"
            expanded_flatpak = os.path.expanduser(flatpak_steam)
            if os.path.exists(expanded_flatpak):
                return expanded_flatpak
            
            process_path = self._get_steam_path_from_process()
            if process_path:
                return process_path
        
        return None
    
    def _parse_library_folders_vdf(self, steam_path):
        """parse libraryfolders.vdf"""
        vdf_path = os.path.join(steam_path, 'steamapps', 'libraryfolders.vdf')
        if not os.path.exists(vdf_path):
            vdf_path = os.path.join(steam_path, 'SteamApps', 'libraryfolders.vdf')
        
        if not os.path.exists(vdf_path):
            return [steam_path]
        
        libraries = [steam_path]
        
        try:
            with open(vdf_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            path_pattern = r'"path"\s+"([^"]+)"'
            matches = re.findall(path_pattern, content)
            
            for match in matches:
                library_path = match.replace('\\\\', '\\')
                if os.path.exists(library_path) and library_path not in libraries:
                    libraries.append(library_path)
            
            return libraries
        except:
            return [steam_path]

    def _get_retail_gmod_path(self, library_path):
        """return retail gmod13 garrysmod directory if it exists"""
        retail_info = self.GMOD_RETAIL['gmod13']
        for steamapps_dir in ['steamapps', 'SteamApps']:
            game_root = os.path.join(library_path, steamapps_dir, 'common', retail_info['install_dir'])
            mod_path = os.path.join(game_root, retail_info['game_dir'])
            if os.path.exists(mod_path):
                return mod_path
        return None
    
    def _detect_gmod(self):
        """detect gmod installation"""
        print("\n" + "="*70)
        print("GARRY'S MOD BRIDGE")
        print("="*70)
        print("\n[scan] detecting steam libraries...")
        
        steam_path = self._get_steam_install_path()
        
        if not steam_path:
            print("  [error] steam installation not found")
            print("="*70 + "\n")
            return
        
        print(f"  [steam] {steam_path}")
        
        all_libraries = self._parse_library_folders_vdf(steam_path)
        print(f"  [libraries] found {len(all_libraries)} steam libraries")
        
        print("\n[scan] detecting gmod installations...")
        
        running_gmod = self._detect_running_gmod()
        
        # first scan sourcemod variants (gmod 9-12)
        for library_path in all_libraries:
            sourcemods_path = os.path.join(library_path, 'steamapps', 'sourcemods')
            if not os.path.exists(sourcemods_path):
                sourcemods_path = os.path.join(library_path, 'SteamApps', 'sourcemods')
            
            if os.path.exists(sourcemods_path):
                for mod_folder, mod_name in self.GMOD_SOURCEMODS.items():
                    mod_path = os.path.join(sourcemods_path, mod_folder)
                    if os.path.exists(mod_path):
                        data_path = os.path.join(mod_path, 'data')
                        
                        is_gmod9 = mod_folder == 'gmod9'
                        
                        if is_gmod9:
                            addon_path = os.path.join(mod_path, 'lua', 'init')
                        else:
                            addon_path = os.path.join(mod_path, 'addons', 'sourcebox')
                        
                        os.makedirs(data_path, exist_ok=True)
                        
                        if running_gmod and running_gmod == mod_folder:
                            self._setup_paths(data_path, addon_path, mod_name, is_gmod9, mod_folder)
                            self._install_lua_addon()
                            print(f"  [found] {mod_name} (RUNNING)")
                            print(f"  [library] {library_path}")
                            return
                        elif not self.active_gmod:
                            print(f"  [installed] {mod_name} (in {library_path})")

        # then scan retail gmod 13 install
        for library_path in all_libraries:
            retail_path = self._get_retail_gmod_path(library_path)
            if not retail_path:
                continue
            
            data_path = os.path.join(retail_path, 'data')
            addon_path = os.path.join(retail_path, 'addons', 'sourcebox')
            os.makedirs(data_path, exist_ok=True)
            
            if running_gmod in ['gmod13', 'garrysmod']:
                self._setup_paths(data_path, addon_path, self.GMOD_RETAIL['gmod13']['name'], False, 'gmod13')
                self._install_lua_addon()
                print(f"  [found] {self.GMOD_RETAIL['gmod13']['name']} (RUNNING)")
                print(f"  [library] {library_path}")
                return
            elif not self.active_gmod:
                print(f"  [installed] {self.GMOD_RETAIL['gmod13']['name']} (in {library_path})")
                            
    def _detect_running_gmod(self):
        """detect running gmod"""
        try:
            for proc in psutil.process_iter(['name', 'exe', 'cmdline']):
                try:
                    proc_name = proc.info.get('name')
                    if not proc_name:
                        continue
                    
                    cmdline = proc.info.get('cmdline')
                    if not cmdline:
                        continue
                    
                    cmdline_str = ' '.join(cmdline).lower()
                    exe_path = proc.info.get('exe') or ''
                    exe_lower = exe_path.lower()
                    proc_lower = proc_name.lower()
                    
                    # hl2 based binaries or gmod specific binaries
                    if proc_lower in ['hl2.exe', 'hl2_linux', 'gmod.exe', 'gmod', 'gmod64', 'gmod32', 'gmod_linux']:
                        for i, arg in enumerate(cmdline):
                            if arg.lower() == '-game' and i + 1 < len(cmdline):
                                game_arg = cmdline[i + 1].strip('"').lower()
                                
                                if 'gmod9' in game_arg or 'garrysmod9' in game_arg:
                                    return 'gmod9'
                                elif 'garrysmod12' in game_arg:
                                    return 'garrysmod12'
                                elif 'garrysmod10classic' in game_arg:
                                    return 'garrysmod10classic'
                                elif 'garrysmod' in game_arg:
                                    # differentiate sourcemod vs retail by path hint
                                    if 'sourcemods' in game_arg or 'sourcemods' in exe_lower:
                                        return 'garrysmod'
                                    return 'gmod13'
                        
                        # fallback: detect retail gmod if binary path clearly in GarrysMod
                        if 'garrysmod' in exe_lower and 'sourcemods' not in exe_lower:
                            return 'gmod13'
                        
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    continue
        except:
            pass
        
        return None
        
    def _setup_paths(self, data_path, addon_path, gmod_name, is_gmod9=False, gmod_version=None):
        """setup paths"""
        self.data_path = data_path
        self.addon_path = addon_path
        self.active_gmod = gmod_name
        self.is_gmod9 = is_gmod9
        self.gmod_version = gmod_version or ('gmod9' if is_gmod9 else None)
        self.command_file = os.path.join(data_path, "sourcebox_command.txt")
        self.response_file = os.path.join(data_path, "sourcebox_response.txt")
        
        try:
            if os.path.exists(self.command_file):
                os.remove(self.command_file)
            if os.path.exists(self.response_file):
                os.remove(self.response_file)
        except:
            pass
    
    def _install_lua_addon(self):
        """install lua addon automatically"""
        if not self.addon_path:
            return
        
        print("\n[install] creating lua addon...")
        
        try:
            if self.is_gmod9:
                # gmod 9 uses init folder structure
                os.makedirs(self.addon_path, exist_ok=True)
                
                # write picker script
                picker_content = self._get_gmod9_picker_lua()
                with open(os.path.join(self.addon_path, 'sv_picker_gmod9.lua'), 'w') as f:
                    f.write(picker_content)
                
                # write spawner script
                spawner_content = self._get_gmod9_spawner_lua()
                with open(os.path.join(self.addon_path, 'sv_auto_spawner_gmod9.lua'), 'w') as f:
                    f.write(spawner_content)
                
                # write bridge script
                bridge_content = self._get_gmod9_bridge_lua()
                with open(os.path.join(self.addon_path, 'sv_python_listener_gmod9.lua'), 'w') as f:
                    f.write(bridge_content)
                
                print(f"  [created] {self.addon_path}")
                print(f"  [files] sv_picker_gmod9.lua, sv_auto_spawner_gmod9.lua, sv_python_listener_gmod9.lua")
                print(f"  [gmod 9] scripts will auto-load from lua/init/")
                
            else:
                # gmod 10-12 uses addons structure
                lua_path = os.path.join(self.addon_path, 'lua')
                autorun_path = os.path.join(lua_path, 'autorun')
                sourcebox_path = os.path.join(autorun_path, 'sourcebox')
                
                os.makedirs(sourcebox_path, exist_ok=True)
                # write addon metadata
                if self.gmod_version == 'gmod13':
                    addon_content = '''"AddonInfo"
{
	"name"		"SourceBox"
	"version"	"1.0"
	"author_name"	"SourceBox Team"
	"info"		"Python bridge for Garry's Mod"
	"override"	"0"
}
'''
                    with open(os.path.join(self.addon_path, 'addon.txt'), 'w') as f:
                        f.write(addon_content)
                else:
                    info_content = '''sourcebox
{
	name		"SourceBox"
	version		"1.0"
	author		"SourceBox Team"
	info		"Python bridge for Garry's Mod"
}
'''
                    with open(os.path.join(self.addon_path, 'info.txt'), 'w') as f:
                        f.write(info_content)
                
                # write sourcebox_init.lua
                init_content = self._get_init_lua()
                with open(os.path.join(autorun_path, 'sourcebox_init.lua'), 'w') as f:
                    f.write(init_content)
                
                # write sv_python_bridge.lua
                bridge_content = self._get_bridge_lua()
                with open(os.path.join(sourcebox_path, 'sv_python_bridge.lua'), 'w') as f:
                    f.write(bridge_content)
                
                # write sv_picker.lua
                picker_content = self._get_picker_lua()
                with open(os.path.join(sourcebox_path, 'sv_picker.lua'), 'w') as f:
                    f.write(picker_content)
                
                # write sv_auto_spawner.lua
                spawner_content = self._get_spawner_lua()
                with open(os.path.join(sourcebox_path, 'sv_auto_spawner.lua'), 'w') as f:
                    f.write(spawner_content)
                
                print(f"  [created] {self.addon_path}")
                print(f"  [files] info.txt, sourcebox_init.lua, sv_*.lua")
            
        except Exception as e:
            print(f"  [error] failed to install addon: {e}")
    
    def _get_gmod9_picker_lua(self):
        """get gmod 9 picker script"""
        return '''-- picker (aimbot) system - gmod 9
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
'''
    
    def _get_gmod9_spawner_lua(self):
        """get gmod 9 spawner script"""
        return '''-- auto-spawner system - gmod 9

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
'''
    
    def _get_gmod9_bridge_lua(self):
        """get gmod 9 bridge script"""
        return r"""-- bridge system - gmod 9
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
"""

    def _get_init_lua(self):
        """get gmod 10-12 init script"""
        return '''if not SERVER then return end

SOURCEBOX = SOURCEBOX or {}
SOURCEBOX.Version = "1.0"

local function WriteFile(path, content)
    if file and file.Write then
        file.Write(path, content)
        return true
    else
        local f = file.Open(path, "w", "DATA")
        if f then
            f:Write(content)
            f:Close()
            return true
        end
        return false
    end
end

local function ReadFile(path)
    if file and file.Read then
        return file.Read(path, "DATA")
    else
        local f = file.Open(path, "r", "DATA")
        if f then
            local content = f:Read(f:Size())
            f:Close()
            return content
        end
        return nil
    end
end

SOURCEBOX.WriteFile = WriteFile
SOURCEBOX.ReadFile = ReadFile

print("[SourceBox] Initializing...")
print("[SourceBox] Version: " .. SOURCEBOX.Version)

include("sourcebox/sv_python_bridge.lua")
include("sourcebox/sv_picker.lua")
include("sourcebox/sv_auto_spawner.lua")

print("[SourceBox] Loaded successfully!")
'''
    
    def _get_bridge_lua(self):
        """get gmod 10-12 bridge script"""
        # Use the provided GMod 10-12 bridge code
        return '''if not SERVER then return end

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
'''
    
    def _get_picker_lua(self):
        """get gmod 10-12 picker script"""
        # Use the provided GMod 10-12 picker code
        return '''if not SERVER then return end

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
'''
    
    def _get_spawner_lua(self):
        """get gmod 10-12 spawner script"""
        # Use the provided GMod 10-12 spawner code
        return '''if not SERVER then return end

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
'''
    
    def is_connected(self):
        """check if bridge is ready"""
        return self.data_path is not None and os.path.exists(self.data_path)
    
    def spawn_model(self, model_path, distance=200):
        """spawn model at crosshair"""
        if not self.is_connected():
            return False
        
        self.command_id += 1
        
        data = {
            "command": "spawn_model",
            "model": model_path,
            "distance": distance,
            "id": self.command_id,
            "session": self.session_id
        }
        
        try:
            with open(self.command_file, 'w') as f:
                f.write(json.dumps(data))
                f.flush()
                os.fsync(f.fileno())
            
            print(f"[GMod Command #{self.command_id}] {model_path}")
            time.sleep(0.05)
            return True
        except Exception as e:
            print(f"[GMod Bridge] Error sending command: {e}")
            return False
        
    def ping(self):
        """test connection"""
        if not self.is_connected():
            return False
        
        self.command_id += 1
        
        data = {
            "command": "ping",
            "id": self.command_id,
            "session": self.session_id
        }
        
        try:
            with open(self.command_file, 'w') as f:
                f.write(json.dumps(data))
            return True
        except:
            return False
    
    def cleanup(self):
        """cleanup temporary files"""
        try:
            if self.command_file and os.path.exists(self.command_file):
                os.remove(self.command_file)
            if self.response_file and os.path.exists(self.response_file):
                os.remove(self.response_file)
        except:
            pass
