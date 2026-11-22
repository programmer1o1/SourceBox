// Experimental aim lock for a local legacy CS:GO practice match.

::g_sourcebox_picker <- { enabled = false, target = null, angles = null, updated = null,
    manual = false, nextScan = 0.0 };
::SOURCEBOX_CSGO_PICKER_RANGE <- 2500.0;

::SourceBoxCSGOPickerPlayer <- function() {
    if (::g_sourcebox_stopped) {
        return null;
    }
    // The classname lookup for "player" finds humans. Full iteration also
    // sees bots which can report "player" through GetClassname().
    local player = Entities.FindByClassname(null, "player");
    if (player == null || !player.IsValid() || player.GetHealth() <= 0 ||
        player.GetTeam() < 2 || Entities.FindByClassname(player, "player") != null) {
        return null;
    }
    return player;
}

::SourceBoxCSGOPickerIsPlayer <- function(classname) {
    return classname == "player" || classname == "cs_bot";
}

::SourceBoxCSGOPickerCandidate <- function(target, player, eye) {
    if (target == null || target == player || !target.IsValid()) {
        return null;
    }
    local classname = target.GetClassname();
    local actor = ::SourceBoxCSGOPickerIsPlayer(classname);
    local priority = 2;
    if (actor) {
        local team = target.GetTeam();
        if (target.GetHealth() <= 0 || (team != 2 && team != 3)) {
            return null;
        }
        priority = team == player.GetTeam() ? 1 : 0;
    } else if (classname != "prop_physics" && classname != "prop_physics_override" &&
        classname != "prop_physics_multiplayer") {
        return null;
    }
    local position = target.GetCenter();
    local distance = (position - eye).Length();
    if (distance < 1.0 || distance > ::SOURCEBOX_CSGO_PICKER_RANGE) {
        return null;
    }
    // CS:GO's world trace checks for cover without hitting the target hitbox.
    if (TraceLine(eye, position, player) < 1.0) {
        if (!actor) {
            return null;
        }
        position = target.EyePosition();
        if (TraceLine(eye, position, player) < 1.0) {
            return null;
        }
    }
    return { entity = target, position = position, priority = priority, distance = distance };
}

::SourceBoxCSGOPickerTargets <- function(player, eye) {
    local targets = [];
    for (local target = Entities.First(); target != null; target = Entities.Next(target)) {
        local candidate = ::SourceBoxCSGOPickerCandidate(target, player, eye);
        if (candidate != null) {
            candidate.order <- targets.len();
            targets.append(candidate);
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
    if (!picker.enabled && ::SourceBoxCSGOPickerPlayer() == null) {
        ::SourceBoxLog("CS:GO Picker requires a living player alone with bots in a local match");
        return;
    }
    picker.enabled = !picker.enabled;
    ::g_sourcebox_picker_hud_at = 0.0;
    picker.target = null;
    picker.angles = null;
    picker.updated = null;
    picker.manual = false;
    picker.nextScan = 0.0;
    ::SourceBoxLog(picker.enabled ? "CS:GO Picker on (requires sv_cheats 1)" : "CS:GO Picker off");
}

::PickerNext <- function() {
    local picker = ::g_sourcebox_picker;
    local player = ::SourceBoxCSGOPickerPlayer();
    if (!picker.enabled || player == null) {
        return;
    }
    local targets = ::SourceBoxCSGOPickerTargets(player, player.EyePosition());
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

::SourceBoxCSGOPickerThink <- function() {
    local picker = ::g_sourcebox_picker;
    if (!picker.enabled) {
        return;
    }
    try {
        local player = ::SourceBoxCSGOPickerPlayer();
        if (player == null) {
            ::PickerToggle();
            return;
        }
        ::SourceBoxPickerHud(player);
        local eye = player.EyePosition();
        local candidate = ::SourceBoxCSGOPickerCandidate(picker.target, player, eye);
        if (candidate == null) {
            picker.target = null;
            picker.manual = false;
        }
        if (!picker.manual && Time() >= picker.nextScan &&
            (candidate == null || candidate.priority > 0)) {
            picker.nextScan = Time() + 0.2;
            local targets = ::SourceBoxCSGOPickerTargets(player, eye);
            if (targets.len() && (candidate == null || targets[0].priority < candidate.priority)) {
                picker.target = targets[0].entity;
                candidate = targets[0];
            }
        }
        if (candidate != null) {
            ::SourceBoxSmoothPickerAim(picker, player, candidate.position - eye);
        }
    } catch (error) {
        picker.enabled = false;
        picker.target = null;
        ::SourceBoxLog("CS:GO Picker stopped: " + error);
    }
}
