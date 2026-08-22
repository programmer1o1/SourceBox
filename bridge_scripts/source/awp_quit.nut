
if (!("g_tracked_props" in getroottable())) {
    ::g_tracked_props <- [];
}

::awp_weapon_classes <- [
    "weapon_awp"
]

::QuitGame <- function() {
    SendToConsole("quit")
}

::TrackExistingProps <- function() {
    local prop = null
    while ((prop = Entities.FindByClassname(prop, "prop_physics")) != null) {
        local model = prop.GetModelName()
        if (model.find("srcbox") != null) {
            local already_tracked = false
            foreach (tracked in g_tracked_props) {
                if (tracked == prop) {
                    already_tracked = true
                    break
                }
            }

            if (!already_tracked) {
                g_tracked_props.append(prop)
            }
        }
    }

    prop = null
    while ((prop = Entities.FindByClassname(prop, "prop_dynamic")) != null) {
        local model = prop.GetModelName()
        if (model.find("srcbox") != null) {
            local already_tracked = false
            foreach (tracked in g_tracked_props) {
                if (tracked == prop) {
                    already_tracked = true
                    break
                }
            }

            if (!already_tracked) {
                g_tracked_props.append(prop)
            }
        }
    }
}

::CheckPropDamage <- function() {
    local prop = null
    while ((prop = Entities.FindByClassname(prop, "prop_physics")) != null) {
        local model = prop.GetModelName()
        if (model.find("srcbox") != null) {
            local already_tracked = false
            foreach (tracked in g_tracked_props) {
                if (tracked == prop) {
                    already_tracked = true
                    break
                }
            }

            if (!already_tracked) {
                g_tracked_props.append(prop)

                prop.ValidateScriptScope()
                local scope = prop.GetScriptScope()
                scope.last_health <- prop.GetHealth()
            }
        }
    }

    foreach (idx, prop in g_tracked_props) {
        if (prop == null || !prop.IsValid()) {
            g_tracked_props.remove(idx)
            continue
        }

        prop.ValidateScriptScope()
        local scope = prop.GetScriptScope()

        if (!("last_health" in scope)) {
            scope.last_health <- prop.GetHealth()
        }

        local current_health = prop.GetHealth()

        if (current_health < scope.last_health) {
            CheckAttackerWeapon(prop)
            scope.last_health <- current_health
        }
    }

    return 0.1
}

::CheckAttackerWeapon <- function(damaged_prop) {
    local host = null
    try { host = GetListenServerHost() } catch(e) {}
    if (host == null) {
        try { host = Entities.FindByClassname(null, "player") } catch(e) {}
    }

    if (host == null) return

    local player = null
    while ((player = Entities.FindByClassname(player, "player")) != null) {
        if (player != host) continue

        // use netprops to get active weapon
        local active_weapon = null
        try {
            active_weapon = NetProps.GetPropEntity(player, "m_hActiveWeapon")
        } catch(e) {
            continue
        }

        if (active_weapon == null || !active_weapon.IsValid()) {
            continue
        }

        // check if the active weapon classname matches awp
        local weapon_classname = null
        try {
            weapon_classname = active_weapon.GetClassname()
        } catch(e) {
            continue
        }

        if (weapon_classname == null) {
            continue
        }

        foreach (awp_class in awp_weapon_classes) {
            if (weapon_classname == awp_class) {
                EntFireByHandle(damaged_prop, "RunScriptCode", "QuitGame()", 0.1, null, null)
                return
            }
        }
    }
}

::SetupDamageOutput <- function() {
    local prop = null
    while ((prop = Entities.FindByClassname(prop, "prop_physics")) != null) {
        local model = prop.GetModelName()
        if (model.find("srcbox") != null) {
            EntFireByHandle(prop, "AddOutput", "OnTakeDamage !self:RunScriptCode:OnPropDamaged():0:-1", 0, null, null)
        }
    }
}

::OnPropDamaged <- function() {
    CheckAttackerWeapon(self)
}

TrackExistingProps()
SetupDamageOutput()

if ("RegisterThinkFunction" in getroottable()) {
    RegisterThinkFunction("awp_quit", CheckPropDamage, 0.0)
} else {
    ::DelayedRegisterAWP <- function() {
        if ("RegisterThinkFunction" in getroottable()) {
            RegisterThinkFunction("awp_quit", CheckPropDamage, 0.0)
        }
    }

    DoEntFire("worldspawn", "RunScriptCode", "DelayedRegisterAWP()", 1.5, null, null)
}
