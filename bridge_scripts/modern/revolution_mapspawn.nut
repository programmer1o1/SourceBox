// Keep a nonsolid, invisible prop as proof the cube model loaded in this map.
if ("Entities" in getroottable()) {
    try {
        local model = "models/props/srcbox/srcbox.mdl";
        if (Entities.FindByName(null, "sourcebox_cube_maker") == null &&
            Entities.FindByName(null, "sourcebox_cube_precache") == null) {
            local prop = CreateEntityByName("prop_dynamic_override", {
                targetname = "sourcebox_cube_precache",
                model = model,
                solid = 0,
                rendermode = 10,
                disableshadows = 1,
                DisableBoneFollowers = 1
            });
            if (prop != null && prop.GetModelName() == model) {
                prop.__KeyValueFromString("targetname", "sourcebox_cube_precache");
                printl("[SourceBox] Revolution cube model loaded during map startup");
            } else {
                printl("[SourceBox] Revolution could not load the cube model during map startup");
            }
        }
    } catch (e) {
        printl("[SourceBox] Revolution cube precache failed: " + e);
    }
}
