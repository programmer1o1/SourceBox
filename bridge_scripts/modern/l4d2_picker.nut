// Local survivor Picker. SourceBox includes this script in its L4D2 bridge.

::SOURCEBOX_PICKER_RANGE <- 2500.0;
::SOURCEBOX_PICKER_SHOT_MASK <- 1174421507;
::SOURCEBOX_PICKER_CLASSES <- ["player", "infected", "witch", "prop_physics",
    "prop_physics_multiplayer", "prop_physics_override"];
::g_sourcebox_picker <- { enabled = false, target = null, manual = false, nextScan = 0.0 };

::SourceBoxL4D2PickerPlayer <- function() {
    local player = GetListenServerHost();
    if (player != null && player.IsValid() && NetProps.GetPropInt(player, "m_iTeamNum") == 2 &&
        !player.IsDead() && !player.IsDying() && !player.IsIncapacitated() && !player.IsHangingFromLedge()) {
        return player;
    }
    return null;
}

::SourceBoxL4D2PickerVisible <- function(target, eye, position, player) {
    local trace = { start = eye, end = position, ignore = player, mask = ::SOURCEBOX_PICKER_SHOT_MASK };
    TraceLine(trace);
    if ("startsolid" in trace && trace.startsolid) {
        return false;
    }
    return ("hit" in trace && !trace.hit) || ("enthit" in trace && trace.enthit == target);
}

::SourceBoxL4D2PickerCandidate <- function(target, eye, player) {
    if (target == null || !target.IsValid() || target == player) {
        return null;
    }

    local classname = target.GetClassname();
    local priority = 2; // Physics prop.
    if (classname == "player") {
        local team = NetProps.GetPropInt(target, "m_iTeamNum");
        if ((team != 2 && team != 3) || target.IsDead() || target.IsDying() ||
            (team == 3 && target.IsGhost())) {
            return null;
        }
        priority = team == 3 ? 0 : 1;
    } else if (classname == "infected" || classname == "witch") {
        if (target.GetHealth() <= 0) {
            return null;
        }
        priority = 0;
    }
    local position = target.GetCenter();
    local distance = (position - eye).Length();
    if (distance < 1.0 || distance > ::SOURCEBOX_PICKER_RANGE) {
        return null;
    }
    if (!::SourceBoxL4D2PickerVisible(target, eye, position, player)) {
        if (classname != "player") {
            return null;
        }
        position = target.EyePosition();
        if (!::SourceBoxL4D2PickerVisible(target, eye, position, player)) {
            return null;
        }
    }
    return { entity = target, position = position, priority = priority, distance = distance };
}

::SourceBoxL4D2PickerTargets <- function(player, eye) {
    local targets = [];
    foreach (classname in ::SOURCEBOX_PICKER_CLASSES) {
        local target = null;
        while ((target = Entities.FindByClassnameWithin(target, classname, eye, ::SOURCEBOX_PICKER_RANGE)) != null) {
            local candidate = ::SourceBoxL4D2PickerCandidate(target, eye, player);
            if (candidate != null) {
                candidate.discoveryOrder <- targets.len();
                targets.append(candidate);
            }
        }
    }
    targets.sort(function(left, right) {
        if (left.priority != right.priority) {
            return left.priority <=> right.priority;
        }
        if (left.distance != right.distance) {
            return left.distance <=> right.distance;
        }
        return left.discoveryOrder <=> right.discoveryOrder;
    });
    return targets;
}

::SourceBoxL4D2PickerAim <- function(player, delta) {
    local horizontal = sqrt(delta.x * delta.x + delta.y * delta.y);
    local pitch = atan2(-delta.z, horizontal) * 57.2957795;
    local yaw = atan2(delta.y, delta.x) * 57.2957795;
    local current = player.EyeAngles();
    local yawDelta = yaw - current.y;
    while (yawDelta > 180.0) yawDelta -= 360.0;
    while (yawDelta < -180.0) yawDelta += 360.0;
    pitch = current.x + (pitch - current.x) * 0.35;
    if (pitch > 89.0) pitch = 89.0;
    if (pitch < -89.0) pitch = -89.0;
    player.SnapEyeAngles(QAngle(pitch, current.y + yawDelta * 0.35, 0));
}

::PickerToggle <- function() {
    local picker = ::g_sourcebox_picker;
    if (!picker.enabled && (::g_sourcebox_stopped || ::SourceBoxL4D2PickerPlayer() == null)) {
        ::SourceBoxLog("Picker requires a living survivor hosting a local game with SourceBox connected");
        return;
    }
    picker.enabled = !picker.enabled;
    picker.target = null;
    picker.manual = false;
    picker.nextScan = 0.0;
    ::SourceBoxLog(picker.enabled ? "Picker on" : "Picker off");
}

::PickerNext <- function() {
    local picker = ::g_sourcebox_picker;
    if (::g_sourcebox_stopped || !picker.enabled) {
        return;
    }
    local player = ::SourceBoxL4D2PickerPlayer();
    if (player == null) {
        return;
    }
    local targets = ::SourceBoxL4D2PickerTargets(player, player.EyePosition());
    if (targets.len() == 0) {
        picker.target = null;
        picker.manual = false;
        return;
    }
    picker.manual = true;
    local next = 0;
    foreach (index, candidate in targets) {
        if (candidate.entity == picker.target) {
            next = (index + 1) % targets.len();
            break;
        }
    }
    picker.target = targets[next].entity;
}

::SourceBoxL4D2PickerThink <- function(now) {
    ::SourceBoxL4D2RefreshPickerChat(now);
    local picker = ::g_sourcebox_picker;
    if (!picker.enabled) {
        return false;
    }
    try {
        local player = ::SourceBoxL4D2PickerPlayer();
        if (player == null) {
            picker.target = null;
            return false;
        }
        local eye = player.EyePosition();
        local candidate = ::SourceBoxL4D2PickerCandidate(picker.target, eye, player);
        if (candidate == null) {
            picker.target = null;
            picker.manual = false;
        }
        // Give newly visible actors priority over an automatically selected fallback.
        if (!picker.manual && now >= picker.nextScan && (candidate == null || candidate.priority > 0)) {
            picker.nextScan = now + 0.25;
            local targets = ::SourceBoxL4D2PickerTargets(player, eye);
            if (targets.len() && (candidate == null || targets[0].priority < candidate.priority)) {
                candidate = targets[0];
                picker.target = candidate.entity;
            }
        }
        if (candidate != null) {
            ::SourceBoxL4D2PickerAim(player, candidate.position - eye);
        }
    } catch (error) {
        picker.enabled = false;
        picker.target = null;
        ::SourceBoxLog("Picker stopped: " + error);
    }
    return picker.enabled;
}

local pickerGeneration = ::g_sourcebox_gen;
local lastChat = null;
local nextChatCheck = 0.0;

local function HandlePickerChat(event, eventName) {
    if (pickerGeneration != ::g_sourcebox_gen || !("text" in event) || !("userid" in event)) {
        return;
    }
    local command = strip(event.text).tolower();
    if (command != "!picker" && command != "!pickernext") {
        return;
    }
    local host = GetListenServerHost();
    if (host == null || !host.IsValid() || GetPlayerFromUserID(event.userid) != host) {
        return;
    }

    // A message may arrive through both chat events. Process it once.
    local now = Time();
    if (lastChat != null && lastChat.command == command && lastChat.eventName != eventName &&
        now - lastChat.time < 0.15) {
        return;
    }
    lastChat = { command = command, eventName = eventName, time = now };

    if (::g_sourcebox_stopped) {
        ClientPrint(host, 3, "[SourceBox] Open SourceBox to use Picker.");
        return;
    }
    if (command == "!picker") {
        if (!::g_sourcebox_picker.enabled && ::SourceBoxL4D2PickerPlayer() == null) {
            ClientPrint(host, 3, "[SourceBox] Picker is available while playing a living survivor.");
            return;
        }
        ::PickerToggle();
        ClientPrint(host, 3, ::g_sourcebox_picker.enabled ? "[SourceBox] Picker on" : "[SourceBox] Picker off");
    } else if (::g_sourcebox_picker.enabled) {
        ::PickerNext();
    } else {
        ClientPrint(host, 3, "[SourceBox] Type !picker to turn Picker on.");
    }
}

::g_sourcebox_picker_events <- {
    OnGameEvent_player_say = function(event) { HandlePickerChat(event, "player_say"); },
    OnGameEvent_player_chat = function(event) { HandlePickerChat(event, "player_chat"); }
};

::SourceBoxL4D2RefreshPickerChat <- function(now) {
    if (now < nextChatCheck) {
        return;
    }
    nextChatCheck = now + 1.0;
    // L4D2 can clear callback tables when it initializes a round.
    __CollectEventCallbacks(::g_sourcebox_picker_events, "OnGameEvent_", "GameEventCallbacks", RegisterScriptGameEventListener);
};
::SourceBoxL4D2RefreshPickerChat(Time());
