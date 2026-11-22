// The saved VScript VM is restored after mapspawn. Use an entity output so
// the bridge starts in the final VM, including when reloading a checkpoint.
if (!("Entities" in getroottable())) {
    return;
}

try {
    // Replace the startup entity from builds that expected a caller binding.
    local oldStarter = Entities.FindByName(null, "sourcebox_portal2_start");
    if (oldStarter != null) {
        oldStarter.Destroy();
    }

    local name = "sourcebox_portal2_activate";
    local starter = Entities.FindByName(null, name);
    if (starter == null) {
        starter = Entities.CreateByClassname("logic_auto");
        if (starter == null) {
            throw "could not create the Portal 2 startup entity";
        }
        starter.__KeyValueFromString("targetname", name);
        starter.__KeyValueFromString("spawnflags", "0");
        // More than one startup entity can fire in the same frame on restore.
        // Portal 2 does not bind caller here, so guard with server time.
        local activate = "if (!(\"g_sourcebox_activate_at\" in getroottable()) || ::g_sourcebox_activate_at != Time()) { " +
            "::g_sourcebox_activate_at <- Time(); DoIncludeScript(\"sourcebox_bridge\", getroottable()); }";
        local sep = "\x1b";
        starter.__KeyValueFromString("OnMapSpawn",
            "worldspawn" + sep + "RunScriptCode" + sep + activate + sep + "0.0" + sep + "-1");
    }
} catch (e) {
    printl("[SourceBox] Portal 2 map-start hook failed: " + e);
}
