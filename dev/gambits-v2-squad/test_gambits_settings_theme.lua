-- Gambits 0.3.4: the settings in use are the ones the settings library holds for the character that is logged in
-- (until 0.3.3 the add-on went on using the table from before the login), Crimson is the theme of a NEW installation
-- only, a saved theme is never changed, and a theme the player picks is the character's shared choice (xifo_ui).
-- SIMULATION: the real Gambits.lua, squad_editor.lua, transport.lua and xifo_ui.lua with a stand-in Ashita. The
-- settings library is either the REAL one of an Ashita installation (third argument: its addons/libs folder, read
-- only) or a stand-in written from it (same files, same order of saving and loading). Files are written only in a
-- temporary folder. Not a gameplay test.
--   luajit test_gambits_settings_theme.lua <kit>/addons-src/Gambits [<Ashita>/addons/libs]
--   (Lua 5.4: lua test_gambits_settings_theme.lua ... ; the real library needs LuaJIT)
local ADDON_DIR, LIBS = arg[1], arg[2]
assert(ADDON_DIR, 'usage: test_gambits_settings_theme.lua <addons-src/Gambits> [<Ashita addons/libs>]')
io.stdout:setvbuf('no')
local passed, failed = 0, 0
local function check(c, label) if c then passed = passed + 1 else failed = failed + 1 io.write('FAIL: ', label, '\n') end end
local function section(n) io.write('\n== ', n, '\n') end
local win = package.config:sub(1, 1) == '\\'
local function mkdir(p) if win then os.execute('mkdir "' .. p:gsub('/', '\\'):gsub('\\+$', '') .. '" 2>nul') else os.execute('mkdir -p "' .. p .. '"') end end
local function slurp(p) local f = io.open(p, 'rb') if not f then return nil end local s = f:read('*a') f:close() return (s:gsub('\r\n', '\n')) end
local function put(p, text) local f = assert(io.open(p, 'w')) f:write(text) f:close() end
local function exists(p) local f = io.open(p, 'r') if f then f:close() return true end return false end
local function themeIn(p) local t = slurp(p) return t and t:match('settings%["theme"%]%s*=%s*"(%w+)"') or nil end
local function numIn(p, key) local t = slurp(p) return t and tonumber(t:match('settings%["' .. key .. '"%]%s*=%s*(%d+)')) or nil end
local basePath, basePreload = package.path, {}
for k, v in pairs(package.preload) do basePreload[k] = v end
local realPrint = print

-- a settings file as the library writes it
local function settingsText(theme, scale)
    return "require('common');\n\nlocal settings = T{ };\n"
        .. 'settings["hide_echo"] = true;\nsettings["interval"] = 1;\nsettings["roles_open"] = false;\n'
        .. 'settings["scale"] = ' .. (scale or 100) .. ';\nsettings["show_all"] = false;\n'
        .. 'settings["theme"] = "' .. theme .. '";\nsettings["win_h"] = 0;\nsettings["win_w"] = 0;\nsettings["ws_open"] = false;\n'
        .. '\nreturn settings;\n'
end

-- ---------------------------------------------------------------- one game session: Gambits loaded in an install folder
-- files: { ['defaults'] = { theme, scale }, ['Aldo_1'] = { ... } } written before the add-on loads (an existing installation)
local function session(dir, who)
    local W = { dir = dir, who = who, handlers = {}, clock = 100 }
    for k in pairs(package.loaded) do
        if k == 'settings' or k == 'squad_editor' or k == 'transport' or k == 'xifo_ui' or k == 'gambits_data' or k == 'trust_spells'
            or k == 'share_code' or k == 'chat' or k == 'imgui' or (k == 'common' and not LIBS) then package.loaded[k] = nil end   -- (the real library's own modules stay loaded: they define the global T once)
    end
    for k in pairs(package.preload) do if not basePreload[k] then package.preload[k] = nil end end
    package.path = ADDON_DIR .. '/?.lua;' .. basePath
    rawset(_G, 'GambitsV2', nil)
    addon = { name = 'Gambits', path = ADDON_DIR .. '/' }
    local im = setmetatable({}, { __index = function(t, k) local f = function() end rawset(t, k, f) return f end })
    im.Begin = function() return false end
    W.im = im
    package.preload['imgui'] = function() return im end
    local party = {}
    function party:GetMemberName() return W.who and W.who[1] or '' end
    function party:GetMemberServerId() return W.who and W.who[2] or 0 end
    ashita = { events = { register = function(event, id, fn) W.handlers[event] = W.handlers[event] or {}; W.handlers[event][id] = fn end },
               time = { get_tick64 = function() return W.clock * 1000 end },
               fs = { create_directory = mkdir, create_dir = mkdir,
                      exists = function(p) p = p:gsub('[\\/]+$', ''); local ok, _, code = os.rename(p, p); return ok ~= nil or code == 13 end } }
    AshitaCore = { GetInstallPath = function() return dir .. '/' end,
                   GetChatManager = function() return { QueueCommand = function(_, _, line) W.queued = W.queued or {}; W.queued[#W.queued + 1] = line end, IsInputOpen = function() return false end } end,
                   GetMemoryManager = function() return { GetParty = function() return party end,
                       GetPlayer = function() return { GetLoginStatus = function() return W.who and 2 or 0 end } end } end }
    GetPlayerEntity = function() return W.who and { ServerId = W.who[2], Name = W.who[1] } or nil end
    local login = { id = 0, name = '' }
    struct = { unpack = function(fmt) if fmt == 'L' then return login.id elseif fmt == 'c16' then return login.name else return 1 end end }

    if LIBS then
        -- the REAL library: its own require chain, with only the chat colours stood in
        package.path = ADDON_DIR .. '/?.lua;' .. LIBS .. '/?.lua;' .. LIBS .. '/?/init.lua;' .. LIBS .. '/sugar/?.lua;' .. basePath
        package.preload['chat'] = function() return setmetatable({}, { __index = function() return function() return setmetatable({}, { __index = function() return function(s) return s end end }) end end }) end
    else
        -- the stand-in: what libs/settings.lua does, step for step (read from it; see dev-step notes in the report)
        package.preload['common'] = function() return true end
        package.preload['settings'] = function()
            local lib = { cache = nil, logged = W.who ~= nil, name = W.who and W.who[1] or '', id = W.who and W.who[2] or 0, events = {} }
            local function path() return dir .. '/config/addons/Gambits/' .. ((lib.logged and lib.id > 0) and (lib.name .. '_' .. lib.id) or 'defaults') .. '/' end
            local function save(t)
                mkdir(path())
                local keys = {}
                for k in pairs(t) do keys[#keys + 1] = k end
                table.sort(keys)
                local out = { "require('common');\n\nlocal settings = T{ };\n" }
                for _, k in ipairs(keys) do
                    local v = t[k]
                    out[#out + 1] = string.format('settings["%s"] = %s;\n', k, type(v) == 'string' and string.format('%q', v) or tostring(v))
                end
                out[#out + 1] = '\nreturn settings;\n'
                put(path() .. 'settings.lua', table.concat(out))
            end
            local function read(defaults)
                local text = slurp(path() .. 'settings.lua')
                local t = {}
                if text == nil then
                    save(defaults)                       -- (no file: the defaults are written, a copy of them is used)
                    for k, v in pairs(defaults) do t[k] = v end
                    return t
                end
                for k, v in text:gmatch('settings%["([%w_]+)"%]%s*=%s*([^;]+);') do
                    if v == 'true' then t[k] = true elseif v == 'false' then t[k] = false
                    elseif tonumber(v) then t[k] = tonumber(v) else t[k] = v:match('^"(.*)"$') or v end
                end
                return t
            end
            local function merged(defaults)
                local t = read(defaults)
                for k, v in pairs(defaults) do if t[k] == nil then t[k] = v end end   -- (never replaces a value that is there)
                save(t)
                return t
            end
            function lib.load(defaults) lib.defaults = defaults; lib.cache = merged(defaults); return lib.cache end
            function lib.save() if lib.cache then save(lib.cache) return true end return false end
            function lib.register(_, id, fn) lib.events[id] = fn; return true end
            W.switch = function(id, name)
                if lib.cache then save(lib.cache) end        -- (saved under the OLD character first)
                lib.logged, lib.id, lib.name = id ~= 0, id, name
                if lib.defaults then
                    lib.cache = merged(lib.defaults)         -- (a NEW table)
                    for _, fn in pairs(lib.events) do fn(lib.cache) end
                end
            end
            return lib
        end
    end

    if LIBS then
        local okLib, errLib = pcall(require, 'settings')
        assert(okLib, 'the real settings library did not load: ' .. tostring(errLib))
    end
    print = function() end
    W.G = dofile(ADDON_DIR .. '/Gambits.lua')
    W.handlers.load.gv2_load()
    print = realPrint
    W.Ed = W.G.Ed
    function W.login(name, id)
        if W.who ~= nil then W.logout() end   -- (the game always logs the first character out before another logs in)
        W.who = { name, id }
        if LIBS then
            login.id, login.name = id, name
            W.handlers.packet_in['__settings_packet_in_cb']({ id = 0x000A, data = '' })
        else
            W.switch(id, name)
        end
    end
    function W.logout()
        W.who = nil
        if LIBS then W.handlers.packet_in['__settings_packet_in_cb']({ id = 0x000B, data = '' }) else W.switch(0, '') end
    end
    function W.frame(dt) W.clock = W.clock + (dt or 1.1); print = function() end; W.handlers.d3d_present.gv2_present(); print = realPrint end
    function W.command(text, blocked) local e = { command = text, blocked = blocked == true }; print = function() end; W.handlers.command.gv2_command(e); print = realPrint; return e.blocked end
    function W.unload() print = function() end; W.handlers.unload.gv2_unload(); print = realPrint end
    function W.file(who) return dir .. '/config/addons/Gambits/' .. who .. '/settings.lua' end
    function W.shared(who) return dir .. '/config/addons/xiforever/' .. who .. '/ui.cfg' end
    return W
end
local function install(files)
    local dir = os.tmpname(); os.remove(dir); mkdir(dir)
    for who, v in pairs(files or {}) do
        mkdir(dir .. '/config/addons/Gambits/' .. who)
        put(dir .. '/config/addons/Gambits/' .. who .. '/settings.lua', settingsText(v[1], v[2]))
    end
    return dir
end
local function remove(dir) if win then os.execute('rmdir /s /q "' .. dir:gsub('/', '\\') .. '" 2>nul') else os.execute('rm -rf "' .. dir .. '"') end end

io.write(LIBS and ('settings library: the REAL one, ' .. LIBS .. '\n') or 'settings library: the stand-in\n')

-- ================================================================= 1. a new installation
section('1. a new installation: Crimson, and what the player picks is kept')
do
    local dir = install()
    local W = session(dir, nil)
    check(W.Ed.themeName == 'crimson' and themeIn(W.file('defaults')) == 'crimson', 'no settings at all: Crimson at the title screen, written as the default')
    W.login('Aldo', 1); W.frame()
    check(W.Ed.themeName == 'crimson' and themeIn(W.file('Aldo_1')) == 'crimson', 'the first character: Crimson')
    check(not exists(W.shared('Aldo_1')), 'loading and logging in makes no shared choice')
    W.command('/gv2 theme squad'); W.frame()
    check(W.Ed.themeName == 'squad' and themeIn(W.file('Aldo_1')) == 'squad' and slurp(W.shared('Aldo_1')) == 'theme=squad\n',
          '/gv2 theme squad: in use, saved in the character\'s own settings, and the character\'s shared choice')
    W.G.settings.scale = 120; W.G.settings.win_w, W.G.settings.win_h = 900, 520
    W.unload()
    check(numIn(W.file('Aldo_1'), 'scale') == 120 and numIn(W.file('Aldo_1'), 'win_w') == 900, 'size and window size reach the character\'s file (0.3.3 wrote them to a table that was never saved)')
    -- the next start of the game
    W = session(dir, nil)
    check(W.Ed.themeName == 'crimson', 'restart, title screen: the installation\'s default')
    W.login('Aldo', 1); W.frame()
    check(W.Ed.themeName == 'squad' and W.G.settings.scale == 120 and W.G.settings.win_w == 900 and W.G.sizeApplied == false,
          'restart, the character logs in: its Squad theme, its 120 %, its 900 px window')
    W.unload(); remove(dir)
end

-- ================================================================= 2. an existing installation is not changed
section('2. an existing installation keeps what it saved (Classic stays Classic)')
do
    local dir = install({ defaults = { 'classic' }, Aldo_1 = { 'classic' } })
    local before = { slurp(dir .. '/config/addons/Gambits/defaults/settings.lua'), slurp(dir .. '/config/addons/Gambits/Aldo_1/settings.lua') }
    local W = session(dir, nil)
    check(W.G.seedTheme == 'classic' and W.Ed.themeName == 'classic', 'the installation\'s defaults file says classic: that is this installation\'s default, not Crimson')
    W.login('Aldo', 1); W.frame()
    check(W.Ed.themeName == 'classic' and themeIn(W.file('Aldo_1')) == 'classic' and themeIn(W.file('defaults')) == 'classic', 'Classic before and after the login; both files still say classic')
    if LIBS then
        -- the real library writes a file again whenever it loads it (it always did), in its own layout and in the
        -- order its table happens to have: what counts is that no value in it changed
        local function values(path)
            local out = {}
            for k, v in (slurp(path) or ''):gmatch('settings%["([%w_]+)"%]%s*=%s*([^;]+);') do out[#out + 1] = k .. '=' .. v end
            table.sort(out)
            return table.concat(out, ' ')
        end
        local v1, d1 = values(W.file('Aldo_1')), values(W.file('defaults'))
        W.logout(); W.login('Aldo', 1); W.frame()
        check(themeIn(W.file('Aldo_1')) == 'classic' and numIn(W.file('Aldo_1'), 'scale') == 100 and numIn(W.file('Aldo_1'), 'win_w') == 0
            and values(W.file('Aldo_1')) == v1 and values(W.file('defaults')) == d1 and v1:find('theme="classic"', 1, true) ~= nil,
              'no value in the settings files changed, also after loading them a second time')
    else
        check(slurp(W.file('defaults')) == before[1] and slurp(W.file('Aldo_1')) == before[2], 'both settings files are the same text as before, byte for byte')
    end
    W.login('Bea', 2); W.frame()
    check(W.Ed.themeName == 'classic' and themeIn(W.file('Bea_2')) == 'classic', 'a character new to this installation gets the installation\'s theme (Classic), not Crimson')
    check(not exists(dir .. '/config/addons/xiforever/Aldo_1/ui.cfg') and not exists(dir .. '/config/addons/xiforever/Bea_2/ui.cfg'), 'and no shared choice was made for anyone')
    W.unload(); remove(dir)
    for _, name in ipairs({ 'squad', 'crimson' }) do
        dir = install({ defaults = { 'classic' }, Aldo_1 = { name } })
        W = session(dir, nil)
        local atTitle = W.Ed.themeName
        W.login('Aldo', 1); W.frame()
        check(atTitle == 'classic' and W.Ed.themeName == name and themeIn(W.file('Aldo_1')) == name,
              'a character that saved ' .. name .. ' shows ' .. name .. ' after its login (0.3.3 went on showing the installation default, classic)')
        W.unload(); remove(dir)
    end
    -- the add-on was only ever loaded while logged in: there is no defaults file
    dir = install({ Aldo_1 = { 'classic' } })
    W = session(dir, { 'Aldo', 1 })
    W.frame()
    check(W.G.seedTheme == 'classic' and W.Ed.themeName == 'classic', 'no defaults file, but this character has settings: an existing installation, Classic')
    W.login('Bea', 2); W.frame()
    check(themeIn(W.file('Bea_2')) == 'classic', 'and a second character there starts with Classic too')
    W.unload(); remove(dir)
    -- a defaults file without a readable theme
    dir = install({ defaults = { 'classic' } })
    put(dir .. '/config/addons/Gambits/defaults/settings.lua', "require('common');\n\nlocal settings = T{ };\nsettings[\"scale\"] = 100;\n\nreturn settings;\n")
    W = session(dir, nil)
    check(W.Ed.themeName == 'classic', 'an existing defaults file without a theme: still an existing installation (Classic)')
    W.unload(); remove(dir)
end

-- ================================================================= 3. the shared choice of a character
section('3. the shared choice: followed while loaded, per character, and it wins over the older setting')
do
    local dir = install({ defaults = { 'classic' }, Aldo_1 = { 'classic' }, Bea_2 = { 'squad' } })
    local W = session(dir, nil)
    W.login('Aldo', 1); W.frame()
    mkdir(dir .. '/config/addons/xiforever/Aldo_1')   -- (the Squads menu is about to write the character's choice there)
    W.G.open[1] = true
    W.frame()                                                                                       -- (the window is open: looked at once a second)
    put(W.shared('Aldo_1'), 'theme=crimson\n')
    W.frame(0.3)
    local early = W.Ed.themeName
    W.frame(1.0)
    check(early == 'classic' and W.Ed.themeName == 'crimson', 'a theme picked in the Squads menu is followed within a second, without a restart')
    check(themeIn(W.file('Aldo_1')) == 'classic' and W.G.settings.theme == 'classic', 'the add-on\'s own saved theme is not rewritten by following')
    W.login('Bea', 2); W.frame()
    check(W.Ed.themeName == 'squad' and not exists(W.shared('Bea_2')), 'another character: its own saved theme (Squad), never the first one\'s choice, and no file is made for it')
    W.Ed.set_theme('classic'); W.G.pick_theme('classic'); W.frame()
    check(slurp(W.shared('Bea_2')) == 'theme=classic\n' and themeIn(W.file('Bea_2')) == 'classic' and slurp(W.shared('Aldo_1')) == 'theme=crimson\n'
        and themeIn(W.file('Aldo_1')) == 'classic', 'the second character picks Classic: its two files; the first character\'s files are untouched')
    W.logout(); W.frame()
    check(W.Ed.themeName == 'classic', 'logged out: the installation default')
    W.login('Aldo', 1); W.frame()
    check(W.Ed.themeName == 'crimson', 'the first character again: its shared choice (it wins over its older "classic")')
    W.command('/gv2 theme purple'); W.frame()
    check(W.Ed.themeName == 'crimson' and slurp(W.shared('Aldo_1')) == 'theme=crimson\n', 'an unknown name changes nothing (0.3.3 set Classic)')
    -- the file the Squads menu looks for while Gambits is loaded
    check(exists(dir .. '/config/addons/xiforever/Aldo_1/gambits.loaded') and not exists(dir .. '/config/addons/xiforever/Bea_2/gambits.loaded'),
          'gambits.loaded is there for the character that is logged in, not for the other')
    -- a moment without a character that is NOT a logout (a zone loads; the settings library says nothing)
    do
        local mark = dir .. '/config/addons/xiforever/Aldo_1/gambits.loaded'
        local text = slurp(mark)
        W.who = nil
        local held = true
        for _ = 1, 10 do W.frame(2.0); held = held and W.Ed.themeName == 'crimson' and exists(mark) end
        check(held, 'no character for 20 seconds without a logout: the theme stays the character\'s and gambits.loaded stays, in every frame')
        W.who = { 'Aldo', 1 }; W.frame(5.1)
        check(W.Ed.themeName == 'crimson' and slurp(mark) == text, 'the character is back: nothing changed, the mark was not written again')
        W.who = nil; W.frame(5.1); W.frame(31)
        check(not exists(mark) and W.Ed.themeName == 'classic', 'no character for more than 30 seconds: the mark is removed and the add-on\'s own theme is used (nothing is held for ever)')
        W.who = { 'Aldo', 1 }; W.frame(5.1)
        check(exists(mark) and W.Ed.themeName == 'crimson', 'back: the mark and the shared choice again')
        W.logout(); W.frame(0.1)
        check(not exists(mark) and W.Ed.themeName == 'classic', 'a real logout (the settings library says so): at once, without the wait')
        W.login('Aldo', 1); W.frame()
        check(exists(mark) and W.Ed.themeName == 'crimson', 'logged in again: as before')
    end
    W.unload()
    check(not exists(dir .. '/config/addons/xiforever/Aldo_1/gambits.loaded'), 'and it is removed when the add-on is unloaded')
    -- the other load order: the shared choice exists before the add-on loads
    W = session(dir, { 'Aldo', 1 }); W.frame()
    check(W.Ed.themeName == 'crimson', 'loaded while logged in, with a shared choice already there: in use from the start')
    W.unload(); remove(dir)
end

-- (0.3.7) a theme picked in either add-on is in the other at its next frame: the "/xifotheme" line
section('4. (0.3.7) the theme line between the two add-ons')
do
    local dir = install({ defaults = { 'classic' }, Aldo_1 = { 'classic' } })
    local W = session(dir, nil)
    W.login('Aldo', 1); W.frame()
    mkdir(dir .. '/config/addons/xiforever/Aldo_1')
    local function lines() local n = 0 for _, l in ipairs(W.queued or {}) do if l == '/xifotheme' then n = n + 1 end end return n end
    -- picked here: the Squads menu is told, once
    W.G.open[1] = true; W.frame()
    local n0 = lines()
    W.command('/gv2 theme squad'); W.frame(0.016)
    check(lines() == n0 + 1 and W.Ed.themeName == 'squad' and slurp(W.shared('Aldo_1')) == 'theme=squad\n',
          'picked in Gambits: saved for the character, in use at once, and one /xifotheme line tells the Squads menu')
    -- picked in the Squads menu: its line arrives, the very next frame has the theme
    put(W.shared('Aldo_1'), 'theme=crimson\n')
    W.frame(0.016)
    local before = W.Ed.themeName
    local stopped = W.command('/xifotheme')
    local atOnce = W.Ed.themeName
    W.frame(0.016)
    check(before == 'squad' and stopped == true and atOnce == 'crimson' and W.Ed.themeName == 'crimson',
          'the Squads menu picked Crimson and said so: the line is stopped (never sent to the game) and the open window is Crimson at its next frame')
    check(themeIn(W.file('Aldo_1')) == 'squad' and lines() == n0 + 1, 'following writes nothing and sends no line back')
    -- the line was stopped by the menu first: still answered
    put(W.shared('Aldo_1'), 'theme=classic\n')
    check(W.command('/xifotheme', true) == true and W.Ed.themeName == 'classic', 'the line already stopped by the other add-on is answered all the same')
    -- any other stopped line is left alone, as before
    put(W.shared('Aldo_1'), 'theme=crimson\n')
    W.command('/gv2 hide', true)
    check(W.G.open[1] == true and W.Ed.themeName == 'classic', 'another line that was stopped is still not acted on')
    -- without the line nothing is read in every frame
    W.frame(0.016); W.frame(0.016)
    local held = W.Ed.themeName
    W.frame(1.1)
    check(held == 'classic' and W.Ed.themeName == 'crimson', 'without the line: no reading in every frame; the look once a second still follows')
    -- a window opened after a change nobody announced: its first frame has the theme
    W.command('/gv2 hide'); W.frame(0.016)
    put(W.shared('Aldo_1'), 'theme=squad\n')
    W.frame(0.016)
    local closed = W.Ed.themeName
    W.command('/gv2 show')
    check(closed == 'crimson' and W.G.open[1] == true and W.Ed.themeName == 'squad', 'a window opened after the change has the new theme before its first frame')
    -- an unknown theme name: nothing saved, no line
    local n1 = lines()
    W.command('/gv2 theme purple')
    check(lines() == n1 and W.Ed.themeName == 'squad', 'an unknown name: no change, no line')
    W.unload(); remove(dir)
end

-- (0.3.9) the Squads launcher's Gambits half: the window's real state in gambits.open, and "/xifogambits" when it changes
section('4b. (0.3.9) the window\'s state for the Squads launcher')
do
    local dir = install({})
    local W = session(dir, nil)
    W.login('Aldo', 1); W.frame()
    local open = dir .. '/config/addons/xiforever/Aldo_1/gambits.open'
    local function lines() local n = 0 for _, l in ipairs(W.queued or {}) do if l == '/xifogambits' then n = n + 1 end end return n end
    W.frame(); W.frame()
    check(not exists(open) and lines() <= 1, 'closed: no gambits.open')
    local n0 = lines()
    W.command('/gambits'); W.frame()
    check(exists(open) and lines() == n0 + 1, '/gambits opens it: gambits.open is written and one /xifogambits line says so')
    W.frame(); W.frame()
    check(lines() == n0 + 1, 'nothing more while it stays open (written only on a change)')
    W.G.open[1] = false; W.frame()   -- (the window's own X: ImGui sets the open flag to false while drawing)
    check(not exists(open) and lines() == n0 + 2, 'closed with its X: the file goes and one line says so')
    W.command('/gambits show 2'); W.frame()
    check(exists(open) and lines() == n0 + 3, 'opened on a mate ("/gambits show 2", a card\'s button): the same')
    W.command('/gambits hide'); W.frame()
    check(not exists(open) and lines() == n0 + 4, '/gambits hide: the same')
    check(W.command('/xifogambits') == true, 'its own line is stopped here too, when the Squads menu is not loaded')
    W.command('/gambits'); W.frame()
    W.unload()
    check(not exists(open), 'unloaded while open: the file is removed with gambits.loaded')
    remove(dir)
end

-- (0.3.6) the window is never taller or wider than the game's screen, also at a large Size
do
    local dir = install({})
    local W = session(dir, { 'Aldo', 1 })
    local limits = {}
    W.im.SetNextWindowSizeConstraints = function(lo, hi) limits[#limits + 1] = { lo[1], lo[2], hi[1], hi[2] } end
    W.command('/gv2'); W.frame()
    local a = limits[#limits]
    check(a ~= nil and a[1] == 720 and a[2] == 420 and a[3] > 100000, 'an ImGui that does not say the screen\'s size: 720 x 420 at least, no upper limit, as before')
    W.im.GetIO = function() return { DisplaySize = { x = 1280, y = 720 } } end
    W.frame()
    a = limits[#limits]
    check(a[1] == 720 and a[2] == 420 and a[3] == 1280 and a[4] == 720, 'a 1280 x 720 screen: at most 1280 x 720')
    W.command('/gv2 scale 200'); W.frame()
    a = limits[#limits]
    check(a[1] == 1280 and a[2] == 720 and a[3] == 1280 and a[4] == 720, 'at 200 % the smallest size (1440 x 840) gives way to the screen: exactly 1280 x 720')
    W.unload()
end

io.write(string.format('\npassed %d, failed %d\n', passed, failed))
os.exit(failed == 0 and 0 or 1)
