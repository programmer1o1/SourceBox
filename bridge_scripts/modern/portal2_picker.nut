// Experimental single-player aim lock for stock Portal 2.

::g_sourcebox_picker <- { enabled = false, target = null, angles = null, updated = null,
    manual = false, nextScan = 0.0 };
::SOURCEBOX_PORTAL2_PICKER_CLASSES <- ["npc_portal_turret_floor", "prop_weighted_cube",
    "prop_physics", "prop_physics_override", "prop_physics_multiplayer"];
::SOURCEBOX_PORTAL2_PICKER_RANGE <- 2000.0;

// Portal 2 uses Squirrel 2.2, so use root slots for helpers shared between functions.
::SourceBoxPortal2PickerPlayer <- function() {
    if (::g_sourcebox_stopped || IsMultiplayer()) {
        return null;
    }
    local player = GetPlayer();
    return player != null && player.IsValid() && player.GetHealth() > 0 ? player : null;
}

::SourceBoxPortal2PickerTargetPosition <- function(target, player, eye) {
    if (target == null || !target.IsValid()) {
        return null;
    }
    local position = target.GetCenter();
    local delta = position - eye;
    local distance = delta.Length();
    if (distance < 1.0 || distance > ::SOURCEBOX_PORTAL2_PICKER_RANGE) {
        return null;
    }
    local hit = TraceLine(eye, position, player);
    // The trace can end on the target's surface. Check the rest with that target ignored.
    if (hit < 1.0 && TraceLine(eye + delta * hit, position, target) < 1.0) {
        return null;
    }
    return position;
}

::SourceBoxPortal2PickerTargets <- function(player, eye) {
    local targets = [];
    foreach (classname in ::SOURCEBOX_PORTAL2_PICKER_CLASSES) {
        local target = null;
        while ((target = Entities.FindByClassnameWithin(target, classname, eye, ::SOURCEBOX_PORTAL2_PICKER_RANGE)) != null) {
            local position = ::SourceBoxPortal2PickerTargetPosition(target, player, eye);
            if (position != null) {
                targets.append({ entity = target, position = position, priority = classname == "npc_portal_turret_floor" ? 0 : 1,
                    distance = (position - eye).Length(), order = targets.len() });
            }
        }
    }
    targets.sort(function(left, right) {
        if (left.priority != right.priority) return left.priority - right.priority;
        if (left.distance == right.distance) return left.order - right.order;
        return left.distance < right.distance ? -1 : 1;
    });
    return targets;
}

::PickerToggle <- function() {
    local picker = ::g_sourcebox_picker;
    if (!picker.enabled && ::SourceBoxPortal2PickerPlayer() == null) {
        ::SourceBoxLog("Portal 2 Picker requires a living player in a local single-player map with SourceBox connected");
        return;
    }
    picker.enabled = !picker.enabled;
    if (!picker.enabled) {
        ::SourceBoxClearPortal2PickerHud();
    }
    ::g_sourcebox_picker_hud_at = 0.0;
    picker.target = null;
    picker.angles = null;
    picker.updated = null;
    picker.manual = false;
    picker.nextScan = 0.0;
    ::SourceBoxLog(picker.enabled ? "Portal 2 Picker on (requires sv_cheats 1)" : "Portal 2 Picker off");
}

::PickerNext <- function() {
    local picker = ::g_sourcebox_picker;
    if (!picker.enabled) {
        return;
    }
    local player = ::SourceBoxPortal2PickerPlayer();
    if (player == null) {
        return;
    }
    local targets = ::SourceBoxPortal2PickerTargets(player, player.EyePosition());
    local next = 0;
    foreach (index, candidate in targets) {
        if (candidate.entity == picker.target) {
            next = (index + 1) % targets.len();
            break;
        }
    }
    picker.target = targets.len() ? targets[next].entity : null;
    picker.manual = picker.target != null;
}

::SourceBoxPortal2PickerThink <- function() {
    local picker = ::g_sourcebox_picker;
    if (!picker.enabled) {
        return;
    }
    try {
        local player = ::SourceBoxPortal2PickerPlayer();
        if (player == null) {
            picker.enabled = false;
            picker.target = null;
            ::SourceBoxClearPortal2PickerHud();
            return;
        }
        ::SourceBoxPickerHud(player);
        local eye = player.EyePosition();
        local position = ::SourceBoxPortal2PickerTargetPosition(picker.target, player, eye);
        if (position == null) {
            picker.target = null;
            picker.manual = false;
        }
        if (!picker.manual && Time() >= picker.nextScan &&
            (position == null || picker.target.GetClassname() != "npc_portal_turret_floor")) {
            picker.nextScan = Time() + 0.2;
            local targets = ::SourceBoxPortal2PickerTargets(player, eye);
            if (targets.len() && (position == null || targets[0].priority == 0)) {
                picker.target = targets[0].entity;
                position = targets[0].position;
            }
        }
        if (position != null) {
            ::SourceBoxSmoothPickerAim(picker, player, position - eye);
        }
    } catch (error) {
        picker.enabled = false;
        picker.target = null;
        ::SourceBoxClearPortal2PickerHud();
        ::SourceBoxLog("Portal 2 Picker stopped: " + error);
    }
}
