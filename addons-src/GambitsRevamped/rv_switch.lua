--[[
rv_switch.lua: the saved Revamped switch, shared by the GambitsRevamped and SquadsRevamped shell addons, the full Revamped
packages that replace them, and the launcher (launcher_revamped.py reads and writes the same file).

The file: <Ashita>\config\addons\revamped\choice.txt, plain text, one key=value per line:
    asked=1            the first-load question was answered (missing = never asked)
    use_revamped=1     1 = Revamped on and the old Squads window and old Gambits addon off, 0 = nothing changes
Nothing here prints, draws or registers a command. The only thing that draws is RV.ask_draw(), and only when a Revamped
package (not just a shell) is installed and the question was not answered yet.

Used by an addon like this:
    local RV = require('rv_switch')
    -- in d3d_present:  RV.tick(imgui)          -- asks once, applies the saved choice; does nothing for shells alone
    -- anywhere:        RV.is_on()              -- true when the saved switch is Revamped
    -- a settings button:  RV.set(true|false)    -- the same choice the question writes; Yes also turns the old ones off now
]]

local RV = {}

RV.OLD_ADDONS = { 'squadpanel', 'Gambits' }   -- the dev team's Squads window and Gambits editor (kept on disk, only unloaded)
-- a file only the full package has: when it exists the package is installed, not just the shell
RV.PACKAGE_MARKERS = { 'GambitsRevamped\\gr_editor.lua', 'SquadsRevamped\\sr_window.lua' }

local state = { read_at = -100, value = nil, asked = false, applied = false, question_open = false, frames = 0 }

local function install_path()
    local ok, p = pcall(function() return AshitaCore:GetInstallPath() end)
    if ok and type(p) == 'string' then return p end
    return nil
end

function RV.path()
    local base = install_path()
    if not base then return nil end
    return base .. 'config\\addons\\revamped\\choice.txt'
end

local function read_file(path)
    local ok, f = pcall(io.open, path, 'rb')
    if not ok or not f then return nil end
    local text = f:read('*a')
    f:close()
    return text
end

-- parse(text) -> { asked = bool, use = true|false|nil }
function RV.parse(text)
    local out = { asked = false, use = nil }
    for line in tostring(text or ''):gmatch('[^\r\n]+') do
        local k, v = line:match('^%s*([%w_]+)%s*=%s*(%S+)')
        if k == 'asked' then out.asked = (v == '1') end
        if k == 'use_revamped' then
            if v == '1' then out.use = true elseif v == '0' then out.use = false end
        end
    end
    return out
end

function RV.read()
    local p = RV.path()
    local text = p and read_file(p) or nil
    local r = RV.parse(text)
    state.asked = r.asked
    state.value = r.use
    return r
end

function RV.is_on()
    local r = RV.read()
    return r.use == true
end

function RV.asked()
    return RV.read().asked
end

function RV.write(use)
    local p = RV.path()
    if not p then return false end
    pcall(function() ashita.fs.create_dir(p:match('^(.*)\\[^\\]*$')) end)
    local ok, f = pcall(io.open, p, 'wb')
    if not ok or not f then return false end
    f:write('asked=1\nuse_revamped=' .. (use and '1' or '0') .. '\n')
    f:close()
    state.asked, state.value = true, use and true or false
    return true
end

function RV.package_present()
    local base = install_path()
    if not base then return false end
    for _, rel in ipairs(RV.PACKAGE_MARKERS) do
        if ashita.fs.exists(base .. 'addons\\' .. rel) then return true end
    end
    return false
end

local function run(cmd)
    pcall(function() AshitaCore:GetChatManager():QueueCommand(1, cmd) end)
end

-- unload the old addons that are loaded; they stay on disk and can be switched on again from the launcher
function RV.old_off()
    for _, name in ipairs(RV.OLD_ADDONS) do run('/addon unload ' .. name) end
end

-- the choice, from a button or from the question. Yes (true) turns the old ones off now; No (false) changes nothing else.
function RV.set(use)
    local ok = RV.write(use and true or false)
    if ok and use then RV.old_off() end
    return ok
end

-- every frame: asks once when a package is installed and nothing was answered; applies a saved Yes once per load.
function RV.tick(imgui)
    state.frames = state.frames + 1
    if state.frames < 180 then return end            -- let the game and the addons finish loading first
    if state.frames % 20 == 0 or state.pkg == nil then
        RV.read()                                    -- the other Revamped addon may have answered a moment ago
        state.pkg = RV.package_present()
    end
    if not state.pkg then return end                 -- shells alone: silent
    if state.asked then
        if state.value and not state.applied then state.applied = true RV.old_off() end
        return
    end
    RV.ask_draw(imgui)
end

local function flag(name)
    return rawget(_G, name) or 0
end

function RV.ask_draw(g)
    if not g or not g.Begin then return end
    if g.SetNextWindowSize then g.SetNextWindowSize({ 460, 0 }, flag('ImGuiCond_FirstUseEver')) end
    if g.SetNextWindowPos then g.SetNextWindowPos({ 420, 260 }, flag('ImGuiCond_FirstUseEver')) end
    if g.Begin('Revamped##rv_question', { true }, flag('ImGuiWindowFlags_NoCollapse') + flag('ImGuiWindowFlags_AlwaysAutoResize')) then
        g.TextWrapped('Turn off the old Squads / old Gambits and use the Revamped versions?')
        g.Spacing()
        g.TextWrapped('Yes switches the old Squads window and the old Gambits addon off (they stay installed) and uses Revamped from now on. No changes nothing; you can switch later from the Revamped Settings button.')
        g.Spacing()
        if g.Button('Yes##rv_yes', { 120, 0 }) then RV.set(true) state.applied = true end
        if g.SameLine then g.SameLine() end
        if g.Button('No##rv_no', { 120, 0 }) then RV.set(false) end
    end
    g.End()
end

return RV
