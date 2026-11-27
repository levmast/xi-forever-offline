--[[
Gambits - rule-based automation for XI: Forever Offline (Gambits v2; this addon was called GambitsV2 until 2026-11-19).
The addon the name Gambits used to belong to (your own character's rules) is now called autobox.
Commands: /gambits (and /gv2, as before). Settings stay in config/addons/GambitsV2/.
Milestone 2: the Squad Rule Set editor (Target -> Conditions -> Action) for your squad mates.

  /gv2                      show or hide the window
  /gv2 show [slot]          show the window, on that squad mate (the Squads menu's Gambits button)
  /gv2 ping [n] [gap]       measure n round trips (default 10), optionally with another interval between lines
  /gv2 theme <classic|squad|crimson>
  /gv2 interval <seconds>   time between two chat lines (default 1.0; 0.6 - 5.0)
  /gv2 scale <70-200>       window size in percent
  /gv2 help

Independent of the old Gambits addon: its own window, settings (config/addons/GambitsV2/), draft file and command.
Run only one Squad Rule Set editor at a time: the old Gambits' SQUAD tab (if a development build has it) would also take
the server's GSQ answers.
Files: Gambits.lua (this shell), transport.lua (chat transport), squad_editor.lua (the editor), share_code.lua (Rule Set
share codes).
]]

addon.name    = 'Gambits'
addon.author  = 'XI: Forever Offline'
addon.version = '0.4.0'
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
local U  = Ed.UI   -- (0.3.4) xifo_ui.lua: the palettes, the window's colours and metrics, the character's shared theme
G.T, G.Ed, G.U = T, Ed, U
do
    -- the Trust-summoning spells (generated list): left out of the editor's Specific Spell choices
    local okTr, trusts = pcall(load_local, 'trust_spells')
    G.trusts = okTr and trusts or {}
    -- (0.3.1) spell families and status effects from the server's data (generated): only for the editor's lists; without
    -- it the lists are simply not filtered
    local okData, data = pcall(load_local, 'gambits_data')
    G.data = okData and data or nil
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
-- (0.3.1) show_all: the editor's Show all (every spell family / spell the server offers); ws_open: the Weapon Skills
-- section is open; (0.3.2) roles_open: the Party roles section is open
local DEFAULTS = { theme = 'classic', scale = 100, interval = 1.0, hide_echo = true, win_w = 0, win_h = 0, show_all = false,
                   ws_open = false, roles_open = false }
local PREFS = { show_all = true, ws_open = true, roles_open = true } -- (the editor may read and set only these)
local settingsLib
do
    local ok, mod = pcall(require, 'settings')
    if ok and type(mod) == 'table' and type(mod.load) == 'function' then
        settingsLib = mod
    end
end

local function install_path()
    local ok, base = pcall(function() return AshitaCore:GetInstallPath() end)
    if not ok or type(base) ~= 'string' or base == '' then
        return nil
    end

    if not base:match('[/\\]$') then
        base = base .. '/'
    end

    return base
end

-- (0.3.4) The theme a NEW settings file starts with. Crimson for a new installation. An installation that already
-- has Gambits settings keeps its own look: the settings library wrote the theme into every settings file it made
-- (Classic unless the player chose another), it never replaces a value that is in a file, and a file it makes later
-- (a character new to this installation) is made from the default given here. So that default is the theme found in
-- the installation's own defaults file. The file is only read, as text; nothing is written and nothing is changed.
local function saved_theme(path)
    local f = io.open(path, 'r')
    if not f then
        return nil, false
    end

    local text = f:read('*a') or ''
    f:close()
    local name = text:match('settings%["theme"%]%s*=%s*"(%w+)"')
    return (name ~= nil and Ed.THEMES[name] ~= nil) and name or nil, true
end

function G.seed_theme()
    local base = install_path()
    if base == nil then
        return U.DEFAULT
    end

    local dir = base .. 'config/addons/' .. tostring(addon.name) .. '/'
    local theme, existed = saved_theme(dir .. 'defaults/settings.lua')
    if existed then
        return theme or 'classic' -- (an existing installation; a file without a readable theme was written under Classic)
    end

    -- no defaults file: the add-on was only ever loaded while logged in. This character's file tells whether the
    -- installation is an existing one (its files were all made under Classic).
    local id = U.current_identity()
    if id ~= nil then
        local _, existedHere = saved_theme(dir .. id .. '/settings.lua')
        if existedHere then
            return 'classic'
        end
    end

    return U.DEFAULT
end

local function clean_settings(s)
    s.theme = Ed.THEMES[s.theme or ''] and s.theme or (Ed.THEMES[G.seedTheme or ''] and G.seedTheme or U.DEFAULT)
    s.scale = math.max(70, math.min(200, math.floor(((tonumber(s.scale) or 100) + 5) / 10) * 10))
    s.interval = math.max(0.6, math.min(5.0, tonumber(s.interval) or 1.0))
    s.hide_echo = s.hide_echo ~= false
    s.win_w = math.max(0, math.floor(tonumber(s.win_w) or 0)) -- the window size the player left (pixels; 0 = not set yet)
    s.win_h = math.max(0, math.floor(tonumber(s.win_h) or 0))
    s.show_all = s.show_all == true
    s.ws_open = s.ws_open == true
    s.roles_open = s.roles_open == true
    return s
end

local function load_settings()
    local s
    G.seedTheme = G.seed_theme()
    DEFAULTS.theme = G.seedTheme
    Ed.DEFAULT_THEME = G.seedTheme
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

    -- (0.3.4) The settings library reads another file when a character logs in or out and then holds a NEW table: the
    -- one it saves. Until 0.3.3 this add-on went on using the table from before the login (the "defaults" file when it
    -- was loaded at the title screen, as the launcher's start script does), so a character's own theme, size and
    -- window size were never used, and what the player changed was never written. Now the table the library holds is
    -- the one in use. A character whose own saved theme differs from the installation's default therefore shows its
    -- own theme from this version on.
    if settingsLib and type(settingsLib.register) == 'function' and not G.registered then
        G.registered = true
        pcall(settingsLib.register, 'settings', 'gv2_settings', function(new)
            if type(new) == 'table' then
                G.adopt_settings(new)
            end
        end)
    end
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
-- (0.3.4) the lists themselves are in xifo_ui.lua now (the same values), shared with the Squads menu
local function color_list(c)
    return U.window_colors(c)
end

local function style_list(c)
    return U.window_vars(c, s)
end

-- ---------------------------------------------------------------- (0.3.4) the settings in use, the shared theme
-- the settings table the library holds now (after a login or logout): this character's theme, size and window size
function G.adopt_settings(new)
    G.settings = clean_settings(new)
    G.sizeApplied, G.pendingSize = false, nil
    if T and type(T.set_interval) == 'function' then
        pcall(T.set_interval, G.settings.interval)
    end

    -- the settings library swapped its table: a login or a logout. With no character now it is a logout for sure
    -- (the follower would otherwise keep the character for a while, as it does through a zone change)
    if G.follow and U.current_identity() == nil then
        G.follow:reset()
    end

    G.sync_theme(now(), true)
end

local function make_dir(dir)
    if ashita and ashita.fs and type(ashita.fs.create_directory) == 'function' then
        pcall(ashita.fs.create_directory, dir)
    end
end

-- A small file while Gambits is loaded for this character (config/addons/xiforever/<Name>_<ServerId>/gambits.loaded):
-- the Squads menu shows its Gambits button only then, so it never sends a command nobody answers. It is not a
-- setting and holds nothing; it is removed when the add-on is unloaded or another character logs in.
function G.presence(id)
    if id == G.presenceId then
        return
    end

    local base = install_path()
    if G.presenceId and base then
        local old = U.pref_dir(base, G.presenceId)
        if old then
            os.remove(old .. 'gambits.loaded')
            os.remove(old .. 'gambits.open') -- (0.3.9)
        end
    end
    G.openSaid = nil -- (0.3.9) the new character's folder is told the window's state at the next frame

    G.presenceId = id
    local dir = base and U.pref_dir(base, id) or nil
    if dir then
        make_dir((dir:gsub('[^/\\]+[/\\]$', '')))
        make_dir(dir)
        local f = io.open(dir .. 'gambits.loaded', 'w')
        if f then
            f:write(U.presence_text(addon.version)) -- (with the game process's id: a mark left by a crash is not this one)
            f:close()
        end
    end
end

-- (0.3.9) The window's real state for the Squads menu's launcher: a small file gambits.open beside gambits.loaded while
-- the window is shown (made the same way: with the game process's id), and the line "/xifogambits" whenever it changes,
-- however it changed (the window's X, /gambits, a mate's Gambits button, the launcher). Looked at once a frame, after
-- the window was drawn; it only writes when the state changed. The line carries nothing: the file stays the one source.
G.OPEN_SIGNAL = '/xifogambits'
function G.announce_open()
    local shown = G.open[1] == true
    if shown == G.openSaid or G.presenceId == nil then
        return
    end

    G.openSaid = shown
    local base = install_path()
    local dir = base and U.pref_dir(base, G.presenceId) or nil
    if dir then
        if shown then
            local f = io.open(dir .. 'gambits.open', 'w')
            if f then
                f:write(U.presence_text(addon.version))
                f:close()
            end
        else
            os.remove(dir .. 'gambits.open')
        end
    end

    pcall(function()
        AshitaCore:GetChatManager():QueueCommand(1, G.OPEN_SIGNAL)
    end)
end

-- The theme in use: the character's shared choice when one was made (here or in the Squads menu), else this add-on's
-- own saved theme. Looked at once a second while the window is shown, every five seconds otherwise, and at once when
-- the settings change. It only reads: the shared choice is written only by G.pick_theme.
function G.sync_theme(t, force)
    if G.follow == nil or G.settings == nil then
        return
    end

    if not force and t - (G.themeAt or -1000) < (G.open[1] and 1 or 5) then
        return
    end

    G.themeAt = t
    local shared, id = G.follow:poll(t, true)
    local want = shared or G.settings.theme
    if want ~= Ed.themeName then
        Ed.set_theme(want)
    end

    G.presence(id)
end

-- the player picked a theme (the list in the window, /gv2 theme): saved as this add-on's own setting and as the
-- character's shared choice, which the Squads menu follows
function G.pick_theme(name)
    if not U.valid(name) then
        return nil
    end

    name = Ed.set_theme(name)
    G.settings.theme = name
    if settingsLib and type(settingsLib.save) == 'function' then
        pcall(settingsLib.save)
    end

    if G.follow and G.follow:pick(name, make_dir) then
        G.theme_signal() -- (0.3.7) the Squads menu reads the choice at its next frame, not at its next look
    end

    return name
end

-- (0.3.7) "/xifotheme": the character's theme was just chosen, look at it now. A line between the two add-ons, never
-- typed and never sent to the game: each of them answers it and stops it, so it is harmless when the other is not
-- loaded. It carries no theme: the saved choice stays the one source.
G.THEME_SIGNAL = '/xifotheme'
function G.theme_signal()
    pcall(function()
        AshitaCore:GetChatManager():QueueCommand(1, G.THEME_SIGNAL)
    end)
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

-- (0.3.6) the size of the game's screen in pixels (ImGui's display size), or nil when this binding does not say
function G.display()
    if not imgui.GetIO then
        return nil, nil
    end

    local ok, w, h = pcall(function()
        local size = imgui.GetIO().DisplaySize
        return tonumber(size.x or size[1]), tonumber(size.y or size[2])
    end)
    if ok and w and h and w > 0 and h > 0 then
        return w, h
    end

    return nil, nil
end

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
        -- (0.3.6) never taller or wider than the game's screen (a window taller than the screen has its Save buttons
        -- below the edge); at a large Size on a small screen the smallest size gives way to the screen's size
        if imgui.SetNextWindowSizeConstraints then
            local big = rawget(_G, 'FLT_MAX') or 3.0e38
            local sw, sh = G.display()
            local maxW, maxH = sw or big, sh or big
            imgui.SetNextWindowSizeConstraints({ math.min(s(G.MIN_W), maxW), math.min(s(G.MIN_H), maxH) }, { maxW, maxH })
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
        if G.open[1] then
            G.sync_theme(now(), true) -- (0.3.7) a window that opens has the character's theme in its first frame
        end
        -- (0.3.4) /gambits show <slot>: on that squad mate (the Squads menu's Gambits button sends this)
        if sub == 'show' and tonumber(words[2]) then
            Ed.want_mate(tonumber(words[2]))
        end
    elseif sub == 'hide' then
        G.open[1] = false
    elseif sub == 'ping' then
        G.open[1] = true
        Ed.ping(tonumber(words[2]) or 10, tonumber(words[3]))
    elseif sub == 'theme' then
        -- (0.3.4) an unknown name changes nothing (it used to set Classic); a known one is this character's choice,
        -- here and in the Squads menu
        local picked = G.pick_theme(string.lower(words[2] or ''))
        if picked then
            print('[GambitsV2] Theme: ' .. Ed.THEME_NAMES[picked])
        else
            print('[GambitsV2] /gv2 theme classic|squad|crimson   Now: ' .. tostring(Ed.THEME_NAMES[Ed.themeName]))
        end
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
    G.follow = U.follow.new(install_path())
    G.sync_theme(now(), true)
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
        display_h = function()
            local _, h = G.display()
            return h
        end,
        on_theme = function(name)
            G.pick_theme(name)
        end,
        trust_spells = G.trusts,
        addon_data = G.data,
        get_pref = function(key)
            return PREFS[key] and G.settings[key] or nil
        end,
        set_pref = function(key, value)
            if PREFS[key] then
                G.settings[key] = value == true
                save_settings()
            end
        end,
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
    G.presence(nil) -- (removes gambits.loaded and, 0.3.9, gambits.open)
end))

ashita.events.register('command', 'gv2_command', guarded('command', function(e)
    if type(e.command) ~= 'string' then
        return
    end

    -- (0.3.7) the theme was chosen a moment ago, here or in the Squads menu: read it once, now (also when the menu
    -- stopped the line first)
    if string.lower(e.command:match('^%s*(%S+)') or '') == G.THEME_SIGNAL then
        e.blocked = true
        G.sync_theme(now(), true)
        return
    end

    -- (0.3.9) this add-on's own line to the Squads menu: never sent to the game
    if string.lower(e.command:match('^%s*(%S+)') or '') == G.OPEN_SIGNAL then
        e.blocked = true
        return
    end

    if e.blocked then
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
    G.sync_theme(now())
    render()
    G.announce_open() -- (0.3.9) after the window was drawn: its X may have closed it in this frame
end))

return G
