
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

        ::CheckRespawn <- function() {
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
            local host = null;
            try { host = GetListenServerHost() } catch(e) {}
            if (host == null) { 
                try { host = Entities.FindByClassname(null, "player") } catch(e) {} 
            }
            
            if (host == null) return;
            
            local player = null;
            while ((player = Entities.FindByClassname(player, "player")) != null) {
                if (player != host) continue;
                
                // use netprops to get active weapon 
                local active_weapon = null;
                try {
                    active_weapon = NetProps.GetPropEntity(player, "m_hActiveWeapon");
                } catch(e) {
                    continue;
                }
                
                if (active_weapon == null || !active_weapon.IsValid()) {
                    continue;
                }
                
                // check if the active weapon classname matches awp
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
                        EntFireByHandle(damaged_prop, "RunScriptCode", "QuitGame()", 0.1, null, null);
                        return;
                    }
                }
            }
        }

        ::SetupCubeDamageOutput <- function(cube) {
            if (cube != null && cube.IsValid()) {
                // set initial health for damage tracking
                local current_health = cube.GetHealth();
                if (current_health <= 0) {
                    try {
                        cube.SetHealth(100);
                    } catch(e) {}
                }
                
                // attach damage output to trigger awp check
                EntFireByHandle(cube, "AddOutput", "OnTakeDamage !self:RunScriptCode:CheckAttackerWeapon(self):0:-1", 0, null, null);
            }
        }

        // for testing, or just looking for the cube "script TeleportToCube()"
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
                
                local player = null;
                try { player = GetListenServerHost() } catch(e) {}
                if (player == null) { 
                    try { player = Entities.FindByClassname(null, "player") } catch(e) {} 
                }
                
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
            local trace_down = {
                start = Vector(pos.x, pos.y, pos.z + 10),
                end = Vector(pos.x, pos.y, pos.z - 500)
            };
            
            try {
                TraceLineEx(trace_down);
            } catch(e) {
                return false;
            }
            
            if (!trace_down.hit || !("pos" in trace_down)) {
                return false;
            }
            
            local ground_pos = trace_down.pos;
            local height_above_ground = pos.z - ground_pos.z;
            
            if (height_above_ground > 150 || height_above_ground < -50) {
                return false;
            }
            
            local trace_up = {
                start = pos,
                end = Vector(pos.x, pos.y, pos.z + 300)
            };
            
            try {
                TraceLineEx(trace_up);
            } catch(e) {}
            
            if (trace_up.hit && "pos" in trace_up) {
                local clearance = trace_up.pos.z - pos.z;
                if (clearance < 100) {
                    return false;
                }
            }
            
            local player = null;
            try { player = GetListenServerHost() } catch(e) {}
            if (player == null) { 
                try { player = Entities.FindByClassname(null, "player") } catch(e) {} 
            }
            
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
            local player = null;
            try { player = GetListenServerHost() } catch(e) {}
            if (player == null) { 
                try { player = Entities.FindByClassname(null, "player") } catch(e) {} 
            }
            
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
                    angles = QAngle(0, RandomFloat(0, 360), 0),
                    model = CUBE_MODEL,
                    health = 100
                });
            } catch(e) {}
            
            if (cube == null) {
                try {
                    cube = SpawnEntityFromTable("prop_dynamic", {
                        origin = pos,
                        angles = QAngle(0, RandomFloat(0, 360), 0),
                        model = CUBE_MODEL,
                        solid = 6,
                        health = 100
                    });
                } catch(e) {}
            }
            
            if (cube != null) {
                try {
                    cube.SetRenderColor(0, 230, 255);
                } catch(e) {}
                
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

        ::InitializeAutoSpawner <- function() {
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

        ::OnGameEvent_round_start <- function(params) {
            foreach (cube in g_spawned_cubes) {
                if (cube != null && cube.IsValid()) {
                    try {
                        cube.Kill();
                    } catch(e) {}
                }
            }
            
            g_spawned_cubes = [];
            g_auto_spawn_initialized = false;
            g_spawn_attempts = 0;
        }

        __CollectGameEventCallbacks(this);

        if ("RegisterThinkFunction" in getroottable()) {
            RegisterThinkFunction("auto_spawner", InitializeAutoSpawner, 0.0);
            RegisterThinkFunction("respawn_checker", CheckRespawn, 0.0);
        } else {
            ::DelayedRegisterAutoSpawner <- function() {
                if ("RegisterThinkFunction" in getroottable()) {
                    RegisterThinkFunction("auto_spawner", InitializeAutoSpawner, 0.0);
                    RegisterThinkFunction("respawn_checker", CheckRespawn, 0.0);
                }
            }
            
            DoEntFire("worldspawn", "RunScriptCode", "DelayedRegisterAutoSpawner()", 2.0, null, null);
        }
        