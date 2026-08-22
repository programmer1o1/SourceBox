
if (!("g_think_functions" in getroottable())) {
    ::g_think_functions <- {};
    ::g_think_delays <- {};
}

if (!("RegisterThinkFunction" in getroottable())) {
    ::RegisterThinkFunction <- function(name, func, initial_delay = 0.0) {
        g_think_functions[name] <- func;
        g_think_delays[name] <- Time() + initial_delay;
    }
}

// ensure we silence “SCRIPT PERF WARNING …” 
if (!("g_perf_filter_ready" in getroottable())) {
    ::g_perf_filter_ready <- false;

    ::ApplyPerfFilter <- function() {
        local ok = false;
        try {
            SendToConsole("con_filter_enable 1");
            SendToConsole("con_filter_text_out \"SCRIPT PERF WARNING\"");
            local cur = Convars.GetStr("con_filter_text_out");
            if (cur != null && cur.find("SCRIPT PERF WARNING") != null) {
                ok = true;
            }
        } catch(e) {}

        if (!ok) {
            try {
                Convars.SetStr("con_filter_enable", "1");
                Convars.SetStr("con_filter_text_out", "SCRIPT PERF WARNING");
                ok = true;
            } catch(e) {}
        }

        if (ok) {
            g_perf_filter_ready = true;
            return null;  
        }
        return 0.5;        // retry every 0.5s until it sticks
    };

    RegisterThinkFunction("perf_filter", ApplyPerfFilter, 0.0);
}

if (!("UnregisterThinkFunction" in getroottable())) {
    ::UnregisterThinkFunction <- function(name) {
        if (name in g_think_functions) {
            delete g_think_functions[name];
            delete g_think_delays[name];
        }
    }
}

function MasterThink() {
    local current_time = Time();
    
    foreach (name, func in g_think_functions) {
        if (current_time >= g_think_delays[name]) {
            try {
                local delay = func();
                if (delay == null || delay < 0.0) delay = 0.1;
                g_think_delays[name] = current_time + delay;
            } catch(e) {}
        }
    }
    
    return 0.01;
}

if (!("g_python_session_id" in getroottable())) {
    ::g_python_session_id <- 0
}
if (!("g_python_last_command_id" in getroottable())) {
    ::g_python_last_command_id <- 0
}

::last_command_id <- g_python_last_command_id
::current_session_id <- g_python_session_id

function CheckPythonCommand() {
    local command_str = null
    
    try {
        command_str = FileToString("python_command.txt")
    } catch(e) {
        return 0.1
    }
    
    if (command_str == null || command_str.len() == 0) {
        return 0.1
    }
    
    local session_id = ExtractNumber(command_str, "session")
    
    if (session_id > 0 && session_id != current_session_id) {
        current_session_id = session_id
        ::g_python_session_id <- session_id
        
        last_command_id = 0
        ::g_python_last_command_id <- 0
    }
    
    ParseAndExecuteCommand(command_str)
    return 0.1
}

function ParseAndExecuteCommand(json_str) {
    local session_id = ExtractNumber(json_str, "session")
    
    if (session_id == 0) {
        return
    }
    
    if (current_session_id > 0 && session_id != current_session_id) {
        return
    }
    
    local command_id = ExtractNumber(json_str, "id")
    
    if (command_id <= 0) {
        return
    }
    
    if (command_id <= last_command_id) {
        return
    }
    
    last_command_id = command_id
    ::g_python_last_command_id <- command_id
    
    local command = ExtractString(json_str, "command")
    
    if (command == null || command.len() == 0) {
        SendResponse("error", "empty command")
        return
    }
    
    try {
        if (command == "spawn_model") {
            local model = ExtractString(json_str, "model")
            local distance = ExtractNumber(json_str, "distance")
            if (distance == 0) distance = 200
            
            if (model == null || model.len() == 0) {
                SendResponse("error", "no model specified")
                return
            }
            
            SpawnModelAtCrosshair(model, distance)
        } else if (command == "reinstall_awp") {
            if ("SetupDamageOutput" in getroottable()) {
                try {
                    SetupDamageOutput()
                    SendResponse("success", "awp outputs reinstalled")
                } catch(e) {
                    SendResponse("error", "awp reinstall failed")
                }
            } else {
                SendResponse("error", "awp function not found")
            }
        } else {
            SendResponse("error", "unknown command")
        }
    } catch(e) {
        SendResponse("error", "execution failed: " + e)
    }
}

function ExtractString(json_str, key) {
    try {
        local key_str = "\"" + key + "\""
        local key_pos = json_str.find(key_str)
        if (key_pos == null) return null
        
        local value_start = json_str.find("\"", key_pos + key_str.len())
        if (value_start == null) return null
        value_start++
        
        local value_end = json_str.find("\"", value_start)
        if (value_end == null) return null
        
        return json_str.slice(value_start, value_end)
    } catch(e) {
        return null
    }
}

function ExtractNumber(json_str, key) {
    try {
        local key_str = "\"" + key + "\":" 
        local key_pos = json_str.find(key_str)
        if (key_pos == null) return 0
        
        local value_start = key_pos + key_str.len()
        while (value_start < json_str.len()) {
            local char = json_str.slice(value_start, value_start + 1)
            if (char != " " && char != "\t" && char != "\n") break
            value_start++
        }
        
        local value_end = value_start
        while (value_end < json_str.len()) {
            local char = json_str.slice(value_end, value_end + 1)
            if (char == "," || char == "}" || char == " ") break
            value_end++
        }
        
        if (value_end <= value_start) return 0
        
        local num_str = json_str.slice(value_start, value_end)
        try { 
            return num_str.tointeger() 
        } catch(e) { 
            return 0 
        }
    } catch(e) {
        return 0
    }
}

function GetLocalPlayer() {
    local player = null
    try { player = GetListenServerHost() } catch(e) {}
    if (player == null) { try { player = PlayerInstanceFromIndex(1) } catch(e) {} }
    if (player == null) { try { player = Entities.FindByClassname(null, "player") } catch(e) {} }
    return player
}

function SpawnModelAtCrosshair(model_path, distance) {
    local player = GetLocalPlayer()
    if (player == null) {
        SendResponse("error", "no player")
        return
    }
    
    local eye_pos = null
    local eye_angles = null
    
    try {
        eye_pos = player.EyePosition()
        eye_angles = player.EyeAngles()
    } catch(e) {
        SendResponse("error", "failed to get player view")
        return
    }
    
    if (eye_pos == null || eye_angles == null) {
        SendResponse("error", "invalid player view")
        return
    }
    
    local pitch = eye_angles.x * 0.0174533
    local yaw = eye_angles.y * 0.0174533
    
    local forward_x = cos(yaw) * cos(pitch)
    local forward_y = sin(yaw) * cos(pitch)
    local forward_z = -sin(pitch)
    
    local end_pos = Vector(
        eye_pos.x + (forward_x * distance),
        eye_pos.y + (forward_y * distance),
        eye_pos.z + (forward_z * distance)
    )
    
    local trace = {
        start = eye_pos
        end = end_pos
        ignore = player
    }
    
    try {
        TraceLineEx(trace)
    } catch(e) {}
    
    local spawn_pos = end_pos
    
    if (trace.hit && "pos" in trace) {
        spawn_pos = trace.pos
    }
    
    spawn_pos.z += 10
    
    if (model_path.find("models/") != 0) {
        model_path = "models/" + model_path
    }
    
    local prop = null
    
    try {
        prop = SpawnEntityFromTable("prop_physics", {
            origin = spawn_pos,
            angles = QAngle(0, 0, 0),
            model = model_path
        })
    } catch(e) {}
    
    if (prop == null) {
        try {
            prop = SpawnEntityFromTable("prop_dynamic", {
                origin = spawn_pos,
                angles = QAngle(0, 0, 0),
                model = model_path,
                solid = 6
            })
        } catch(e) {}
    }
    
    if (prop != null) {
        try { 
            prop.SetRenderColor(0, 230, 255) 
        } catch(e) {}
        SendResponse("spawned", model_path)
    } else {
        SendResponse("error", "spawn failed - invalid model or missing asset")
    }
}

function SendResponse(status, message) {
    local response = "{\"status\":\"" + status + "\",\"message\":\"" + message + "\"}"
    try { 
        StringToFile("python_response.txt", response) 
    } catch(e) {}
}

RegisterThinkFunction("python_bridge", CheckPythonCommand, 0.0)

if (!("g_master_think_active" in getroottable())) {
    ::g_master_think_active <- true
    try {
        local worldspawn = Entities.FindByClassname(null, "worldspawn")
        if (worldspawn != null) {
            AddThinkToEnt(worldspawn, "MasterThink")
        }
    } catch(e) {}
}
