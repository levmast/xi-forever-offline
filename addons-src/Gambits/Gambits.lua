--[[
Gambits - rule-based automation for XI: Forever Offline (Gambits v2; this addon was called GambitsV2 until 2026-11-19).
The addon the name Gambits used to belong to (your own character's rules) is now called autobox.
Commands: /gambits (and /gv2, as before). Settings stay in config/addons/GambitsV2/.
Milestone 2: the Squad Rule Set editor (Target -> Conditions -> Action) for your squad mates.

  /gv2                      show or hide the window
  /gv2 ping [n] [gap]       measure n round trips (default 10), optionally with another interval between lines
  /gv2 theme <classic|squad|crimson>
  /gv2 interval <seconds>   time between two chat lines (default 1.0; 0.6 - 5.0)
  /gv2 scale <70-200>       window size in percent
  /gv2 help

Independent of the old Gambits addon: its own window, settings (config/addons/GambitsV2/), draft file and command.
Run only one Squad Rule Set editor at a time: the old Gambits' SQUAD tab (if a development build has it) would also take
the server's GSQ answers.
Files: Gambits.lua (this shell), transport.lua (chat transport), squad_editor.lua (the editor).
]]

addon.name    = 'Gambits'
addon.author  = 'XI: Forever Offline'
addon.version = '0.2.0'
addon.desc    = 'Gambits: Rule Sets for your squad mates (Target -> Conditions -> Action).'
addon.link    = ''

pcall(require, 'common')

local G = { open = { false }, errors = {} }   -- this shell's state
_G.GambitsV2 = G

local function base_path()
    local p = (type(addon) == 'table' and type(addon.path) == 'string') and addon.path or ''
    if p ~= '' and not p:match('[/\\]$') then
        p = p .. '/'
    end

    return p
end

-- a file next to this one (require first, so Ashita's package path is used when it has the addon folder)
local function load_local(name)
    local ok, mod = pcall(require, name)
    if ok and type(mod) == 'table' then
        return mod
    end

    local ok2, mod2 = pcall(dofile, base_path() .. name .. '.lua')
    if ok2 and type(mod2) == 'table' then
        return mod2
    end

    error('GambitsV2: ' .. name .. '.lua could not be loaded: ' .. tostring(ok2 and 'not a module' or mod2))
end

local T  = load_local('transport')
local Ed = load_local('squad_editor')
G.T, G.Ed = T, Ed
do
    -- the Trust-summoning spells (generated list): left out of the editor's Specific Spell choices
    local okTr, trusts = pcall(load_local, 'trust_spells')
    G.trusts = okTr and trusts or {}
end

local imgui
do
    local ok, mod = pcall(require, 'imgui')
    if ok then
        imgui = mod
    end
end

local function now()
    if ashita and ashita.time and type(ashita.time.get_tick64) == 'function' then
        local ok, n = pcall(ashita.time.get_tick64)
        if ok and type(n) == 'number' then
            return n / 1000
        end
    end

    return os.clock()
end

local function log(text, err)
    if err then
        print('[Gambits] ' .. tostring(text))
    end
end

local function chat()
    local ok, c = pcall(function() return AshitaCore:GetChatManager() end)
    return ok and c or nil
end

-- ---------------------------------------------------------------- settings
local DEFAULTS = { theme = 'classic', scale = 100, interval = 1.0, hide_echo = true, win_w = 0, win_h = 0 }
local settingsLib
do
    local ok, mod = pcall(require, 'settings')
    if ok and type(mod) == 'table' and type(mod.load) == 'function' then
        settingsLib = mod
    end
end

local function clean_settings(s)
    s.theme = Ed.THEMES[s.theme or ''] and s.theme or 'classic'
    s.scale = math.max(70, math.min(200, math.floor(((tonumber(s.scale) or 100) + 5) / 10) * 10))
    s.interval = math.max(0.6, math.min(5.0, tonumber(s.interval) or 1.0))
    s.hide_echo = s.hide_echo ~= false
    s.win_w = math.max(0, math.floor(tonumber(s.win_w) or 0)) -- the window size the player left (pixels; 0 = not set yet)
    s.win_h = math.max(0, math.floor(tonumber(s.win_h) or 0))
    return s
end

local function load_settings()
    local s
    if settingsLib then
        local d = {}
        for k, v in pairs(DEFAULTS) do
            d[k] = v
        end

        local makeT = rawget(_G, 'T') -- Ashita's common.lua table helper (this file's own T is the transport)
        if type(makeT) == 'function' then
            d = makeT(d)
        end

        local ok, loaded = pcall(settingsLib.load, d)
        s = ok and loaded or nil
    end

    if type(s) ~= 'table' then
        s = {}
        for k, v in pairs(DEFAULTS) do
            s[k] = v
        end
    end

    G.settings = clean_settings(s)
end

local function save_settings()
    if settingsLib and type(settingsLib.save) == 'function' then
        pcall(settingsLib.save)
    end
end

local function scale()
    return (G.settings and G.settings.scale or 100) / 100
end

local function s(px)
    return math.max(1, math.floor((px or 0) * scale() + 0.5))
end

-- ---------------------------------------------------------------- files (config/addons/GambitsV2/)
local function root()
    local ok, base = pcall(function() return AshitaCore:GetInstallPath() end)
    if not ok or type(base) ~= 'string' or base == '' then
        return nil
    end

    if not base:match('[/\\]$') then
        base = base .. '/'
    end

    local dir = base .. 'config/addons/GambitsV2/'
    if not G.rootMade then
        G.rootMade = true
        if ashita and ashita.fs and type(ashita.fs.create_directory) == 'function' then
            pcall(ashita.fs.create_directory, dir)
        end
    end

    return dir
end

local function serialize(v, indent)
    indent = indent or ''
    local t = type(v)
    if t == 'string' then
        return string.format('%q', v)
    elseif t == 'number' or t == 'boolean' then
        return tostring(v)
    elseif t ~= 'table' then
        return 'nil'
    end

    local keys = {}
    for k in pairs(v) do
        if type(k) == 'string' or type(k) == 'number' then
            keys[#keys + 1] = k
        end
    end

    table.sort(keys, function(a, b)
        if type(a) == type(b) then return a < b end
        return type(a) == 'number'
    end)

    local inner, parts = indent .. '    ', {}
    for _, k in ipairs(keys) do
        local key = type(k) == 'number' and ('[' .. k .. ']') or (k:match('^[%a_][%w_]*$') and k or ('[' .. string.format('%q', k) .. ']'))
        parts[#parts + 1] = inner .. key .. ' = ' .. serialize(v[k], inner)
    end

    return '{\n' .. table.concat(parts, ',\n') .. '\n' .. indent .. '}'
end
G.serialize = serialize

-- writes "return <value>" safely: .tmp, then replace (the old file is kept as .bak)
local function writefile(path, value, comment)
    local ok, text = pcall(serialize, value)
    if not ok then
        return false, text
    end

    local data = '-- ' .. (comment or 'GambitsV2') .. '\nreturn ' .. text .. '\n'
    local tmp, bak = path .. '.tmp', path .. '.bak'
    local f, err = io.open(tmp, 'wb')
    if not f then
        return false, err
    end

    f:write(data)
    f:close()
    os.remove(bak)
    os.rename(path, bak)
    local moved, why = os.rename(tmp, path)
    if not moved then
        os.rename(bak, path)
        return false, why
    end

    return true
end
G.writefile = writefile

-- ---------------------------------------------------------------- errors: one line per problem, at most every 10 s
local function report(name, err)
    local t = now()
    local last = G.errors[name]
    if last == nil or t - last > 10 then
        G.errors[name] = t
        print('[Gambits] ' .. name .. ' error: ' .. tostring(err))
    end
end

local function guarded(name, fn)
    return function(...)
        local ok, err = pcall(fn, ...)
        if not ok then
            report(name, err)
        end
    end
end
G.guarded = guarded

-- ---------------------------------------------------------------- the window (whole-window theme, FFXIPort 1.2.0 pattern)
local function color_list(c)
    local times = Ed.times
    return {
        { 'ImGuiCol_WindowBg', c.window }, { 'ImGuiCol_ChildBg', c.panel }, { 'ImGuiCol_PopupBg', c.window },
        { 'ImGuiCol_Text', c.text }, { 'ImGuiCol_TextDisabled', c.muted }, { 'ImGuiCol_Border', c.border },
        { 'ImGuiCol_Separator', c.border }, { 'ImGuiCol_FrameBg', c.header },
        { 'ImGuiCol_FrameBgHovered', times(c.header, 1.25) }, { 'ImGuiCol_FrameBgActive', times(c.header, 1.40) },
        { 'ImGuiCol_Button', c.button }, { 'ImGuiCol_ButtonHovered', times(c.button, 1.25) },
        { 'ImGuiCol_ButtonActive', times(c.button, 1.40) }, { 'ImGuiCol_Header', c.header },
        { 'ImGuiCol_HeaderHovered', times(c.header, 1.25) }, { 'ImGuiCol_HeaderActive', times(c.header, 1.40) },
        { 'ImGuiCol_CheckMark', c.gold }, { 'ImGuiCol_SliderGrab', c.gold }, { 'ImGuiCol_ScrollbarGrab', c.button },
        { 'ImGuiCol_TitleBg', c.title or c.header }, { 'ImGuiCol_TitleBgActive', c.titleActive or c.header },
        { 'ImGuiCol_TitleBgCollapsed', c.title or c.header },
    }
end

local function style_list(c)
    local list = {
        { 'ImGuiStyleVar_WindowPadding', { s(8), s(8) } }, { 'ImGuiStyleVar_FramePadding', { s(4), s(3) } },
        { 'ImGuiStyleVar_ItemSpacing', { s(6), s(4) } }, { 'ImGuiStyleVar_ItemInnerSpacing', { s(4), s(4) } },
    }
    if c.rounding then
        list[#list + 1] = { 'ImGuiStyleVar_WindowRounding', s(c.rounding.window) }
        list[#list + 1] = { 'ImGuiStyleVar_ChildRounding', s(c.rounding.child) }
        list[#list + 1] = { 'ImGuiStyleVar_FrameRounding', s(c.rounding.frame) }
        list[#list + 1] = { 'ImGuiStyleVar_PopupRounding', s(c.rounding.frame) }
    end

    if c.frameBorder then
        list[#list + 1] = { 'ImGuiStyleVar_FrameBorderSize', c.frameBorder }
    end

    return list
end

-- pushes the theme; returns a token that pop() closes exactly (also after a failed push)
local function push_theme()
    local token = { colors = 0, vars = 0, font = false }
    local c = Ed.theme
    pcall(function()
        for _, item in ipairs(color_list(c)) do
            local id = rawget(_G, item[1])
            if id ~= nil and item[2] ~= nil then
                imgui.PushStyleColor(id, item[2])
                token.colors = token.colors + 1
            end
        end

        if imgui.PushStyleVar then
            for _, item in ipairs(style_list(c)) do
                local id = rawget(_G, item[1])
                if id ~= nil then
                    imgui.PushStyleVar(id, item[2])
                    token.vars = token.vars + 1
                end
            end
        end
    end)

    if imgui.PushFont and imgui.GetFont and imgui.GetFontSize and scale() ~= 1 then
        local ok = pcall(function() imgui.PushFont(imgui.GetFont(), imgui.GetFontSize() * scale()) end)
        token.font = ok
    end

    return token
end

local function pop_theme(token)
    if token.font then
        pcall(imgui.PopFont)
    end

    if token.vars > 0 and imgui.PopStyleVar then
        pcall(imgui.PopStyleVar, token.vars)
    end

    if token.colors > 0 then
        pcall(imgui.PopStyleColor, token.colors)
    end
end

G.MIN_W, G.MIN_H = 720, 420  -- unscaled minimum window size

-- Saves the window size once it has stopped changing for a second (not every frame while the player drags it)
function G.remember_size()
    if not imgui.GetWindowSize then
        return
    end

    local a, b = imgui.GetWindowSize()
    local w = type(a) == 'table' and (a[1] or a.x) or a
    local h = type(a) == 'table' and (a[2] or a.y) or b
    w, h = math.floor(tonumber(w) or 0), math.floor(tonumber(h) or 0)
    if w <= 0 or h <= 0 then
        return
    end

    local t = now()
    if math.abs(w - G.settings.win_w) <= 1 and math.abs(h - G.settings.win_h) <= 1 then
        G.pendingSize = nil
        return
    end

    if G.pendingSize == nil or G.pendingSize.w ~= w or G.pendingSize.h ~= h then
        G.pendingSize = { w = w, h = h, at = t }
    elseif t - G.pendingSize.at >= 1.0 then
        G.settings.win_w, G.settings.win_h = w, h
        G.pendingSize = nil
        save_settings()
    end
end

local function render()
    if not G.open[1] or imgui == nil then
        return
    end

    local token = push_theme()
    local began, shown = false, false
    local ok, err = pcall(function()
        -- resizable (FFXIPort 1.2.0's pattern): the minimum grows with the scale; the size the player left is used again
        if imgui.SetNextWindowSizeConstraints then
            local big = rawget(_G, 'FLT_MAX') or 3.0e38
            imgui.SetNextWindowSizeConstraints({ s(G.MIN_W), s(G.MIN_H) }, { big, big })
        end

        if not G.sizeApplied and imgui.SetNextWindowSize then
            local w, h = G.settings.win_w, G.settings.win_h
            imgui.SetNextWindowSize({ w > 0 and w or s(1080), h > 0 and h or s(600) }, rawget(_G, 'ImGuiCond_Always') or 1)
            G.sizeApplied = true
        end

        local flags = rawget(_G, 'ImGuiWindowFlags_NoCollapse') or 0
        shown = imgui.Begin('Gambits v2 - Squad Rule Sets##GambitsV2', G.open, flags)
        began = true
        if shown then
            if not token.font and scale() ~= 1 and imgui.SetWindowFontScale then
                imgui.SetWindowFontScale(scale())
            end

            G.remember_size()
            Ed.draw()
        end
    end)

    if began then
        pcall(imgui.End)
    end

    pop_theme(token)
    if not ok then
        report('window', err)
    end
end
G.render = render

-- ---------------------------------------------------------------- commands
local function help()
    for _, line in ipairs({
        '/gambits (or /gv2)  - show or hide the Squad Rule Set window',
        '/gv2 ping [n] [gap]  - n round trips to the server (and refusals by the game)',
        '/gv2 theme classic|squad|crimson',
        '/gv2 interval <seconds>  - time between two chat lines (now ' .. string.format('%.2f', T.get_interval()) .. ' s)',
        '/gv2 scale <70-200>  - window size in percent',
    }) do
        print('[Gambits] ' .. line)
    end
end

function G.command(words)
    local sub = string.lower(words[1] or '')
    if sub == '' or sub == 'show' or sub == 'toggle' then
        G.open[1] = (sub == 'show') or not G.open[1]
    elseif sub == 'hide' then
        G.open[1] = false
    elseif sub == 'ping' then
        G.open[1] = true
        Ed.ping(tonumber(words[2]) or 10, tonumber(words[3]))
    elseif sub == 'theme' then
        G.settings.theme = Ed.set_theme(string.lower(words[2] or ''))
        save_settings()
        print('[GambitsV2] Theme: ' .. Ed.THEME_NAMES[G.settings.theme])
    elseif sub == 'interval' then
        local v = tonumber(words[2])
        if v then
            G.settings.interval = math.max(0.6, math.min(5.0, v))
            T.set_interval(G.settings.interval)
            save_settings()
        end

        print(string.format('[GambitsV2] Interval between chat lines: %.2f s', T.get_interval()))
    elseif sub == 'scale' then
        local v = tonumber(words[2])
        if v then
            G.settings.scale = v
            clean_settings(G.settings)
            save_settings()
        end

        print('[GambitsV2] Window size: ' .. G.settings.scale .. ' %')
    else
        help()
    end
end

-- ---------------------------------------------------------------- start
function G.start()
    load_settings()
    Ed.set_theme(G.settings.theme)
    Ed.init({
        transport = T,
        transport_config = { interval = G.settings.interval, hideEcho = G.settings.hide_echo },
        now = now, imgui = imgui, log = log, s = s, root = root, writefile = writefile,
        available = function()
            if imgui and imgui.GetContentRegionAvail then
                local a = imgui.GetContentRegionAvail()
                if type(a) == 'table' then
                    return tonumber(a[1] or a.x)
                end

                return tonumber(a)
            end
        end,
        input_open = function()
            local c = chat()
            if not c then
                return false
            end

            local ok, open = pcall(function() return c:IsInputOpen() end)
            return ok and (open == true or (type(open) == 'number' and open ~= 0))
        end,
        queue_command = function(line)
            local c = chat()
            if c then
                pcall(function() c:QueueCommand(1, line) end)
            end
        end,
        on_theme = function(name)
            G.settings.theme = name
            save_settings()
        end,
        trust_spells = G.trusts,
        get_scale = function()
            return G.settings.scale
        end,
        set_scale = function(percent)
            G.settings.scale = percent
            clean_settings(G.settings)
            save_settings()
        end,
    })
end

ashita.events.register('load', 'gv2_load', guarded('load', G.start))

ashita.events.register('unload', 'gv2_unload', guarded('unload', function()
    Ed.on_unload()
    save_settings()
end))

ashita.events.register('command', 'gv2_command', guarded('command', function(e)
    if e.blocked or type(e.command) ~= 'string' then
        return
    end

    local words = {}
    for word in e.command:gmatch('%S+') do
        words[#words + 1] = word
    end

    local first = string.lower(words[1] or '')
    if first == '/gambits' or first == '/gv2' or first == '/gambitsv2' then
        e.blocked = true
        table.remove(words, 1)
        G.command(words)
        return
    end

    T.command_seen(e.command) -- any chat line counts for the interval between lines
end))

ashita.events.register('text_in', 'gv2_text_in', guarded('text_in', function(e)
    -- classified even when another addon already hid the line (it stays hidden; this never un-hides)
    if Ed.text_in(e.message_modified, e.message) then
        e.blocked = true
    end
end))

ashita.events.register('packet_in', 'gv2_packet_in', guarded('packet_in', function(e)
    if e.id == 0x00B then
        T.zone(true)
    elseif e.id == 0x00A then
        T.zone(false)
    end
end))

ashita.events.register('d3d_present', 'gv2_present', guarded('present', function()
    Ed.tick()
    render()
end))

return G
