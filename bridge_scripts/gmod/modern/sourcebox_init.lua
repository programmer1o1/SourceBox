if not SERVER then return end

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
