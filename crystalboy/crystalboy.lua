addon.name    = 'crystalboy'
addon.author  = 'XI: Forever Offline'
addon.version = '1.8c'
addon.desc    = 'Crystal Boy: play your Game Boy cartridges inside FFXI.'
addon.link    = ''

-- Let require() find our cb/*.lua files.
local here = debug.getinfo(1, 'S').source:sub(2):gsub('[^\\/]*$', '')
package.path = here .. '?.lua;' .. package.path

local imgui   = require('imgui')
local retro   = require('cb.retro')
local screen  = require('cb.screen')
local games   = require('cb.games')
local rewards = require('cb.rewards')
local util    = require('cb.util')
local carts   = require('cb.carts')
local input   = require('cb.input')
local trace   = require('cb.trace')
local audio   = require('cb.audio')
local okchat, chat = pcall(require, 'chat')

------------------------------------------------------------------------------
-- Settings and paths
------------------------------------------------------------------------------
local DEFAULTS = {
    scale = 3,            -- picture size: 160x144 times this
    ff_speed = 4,         -- fast forward speed
    slot = 1,             -- savestate slot (1-3)
    pause_unfocused = true,
    core = '',            -- core file in addons\crystalboy\cores ('' = first one found)
    palette = 'auto',     -- gambatte colorization: auto, GBC, SGB, internal, disabled
    sound = true,         -- (1.5) the game's sound
    volume = 60,          -- 0-100
    jit = true,           -- (1.8c) false = the add-on's own Lua runs without LuaJIT's compiler (/cb jit off)
}

local P = {}       -- paths
local S = {}       -- settings
local G = {        -- runtime state
    open = { false }, roms = {}, game = nil, char = nil, last_sav = nil, sav_backed_up = false,
    acc = 0, last_tick = nil, ff_hold = false, ff_toggle = false, paused = false, focused = false,
    owned = { crystal_boy = false, carts = {} }, cart = nil, next_own = 0,
    next_flush = 0, next_ram_check = 0, held = {}, capture = nil, show_controls = false, rules = {}, claims = {}, msg = '', msg_until = 0, core_error = nil,
}

local function say(msg)
    if okchat and chat and chat.header then
        print(chat.header(addon.name):append(chat.message(msg)))
    else
        print('[crystalboy] ' .. msg)
    end
end

local function now_ms() return tonumber(ashita.time.get_tick64()) end
local function now_s() return now_ms() / 1000 end

local function note(msg)
    G.msg, G.msg_until = msg, now_s() + 4
end

--- Create a folder and any missing parents.
local function mkdir(path)
    local sofar = ''
    for part in path:gmatch('[^\\/]+') do
        sofar = (sofar == '' and part) or (sofar .. '\\' .. part)
        if path:sub(1, 1) == '/' and not sofar:match('^/') then sofar = '/' .. sofar end
        if not sofar:match('^%a:$') and not ashita.fs.exists(sofar) then ashita.fs.create_directory(sofar) end
    end
end

local function list_dir(path)
    local t = ashita.fs.get_directory(path, '.*', false)
    if type(t) ~= 'table' then return {} end
    local out = {}
    for _, v in ipairs(t) do
        local name = tostring(v):gsub('^.*[\\/]', '')
        out[#out + 1] = name
    end
    return out
end


local function char_name()
    local ok, name = pcall(function()
        return AshitaCore:GetMemoryManager():GetParty():GetMemberName(0)
    end)
    if ok and type(name) == 'string' and name ~= '' then return name end
    return nil
end

local function char_dir(kind)
    local d = P.cfg .. kind .. '\\' .. util.clean(G.char)
    mkdir(P.cfg .. kind)
    mkdir(d)
    return d .. '\\'
end

local function save_settings() util.save_table(P.cfg .. 'settings.lua', S) end

local function load_settings()
    local t = util.load_table(P.cfg .. 'settings.lua') or {}
    for k, v in pairs(DEFAULTS) do
        if type(v) == 'table' then
            S[k] = {}
            for kk, vv in pairs(v) do S[k][kk] = (type(t[k]) == 'table' and t[k][kk]) or vv end
        elseif t[k] == nil then S[k] = v else S[k] = t[k] end
    end
    S.scale = math.max(1, math.min(6, tonumber(S.scale) or 3))
    S.ff_speed = math.max(2, math.min(10, tonumber(S.ff_speed) or 4))
    S.slot = math.max(1, math.min(3, tonumber(S.slot) or 1))
    S.volume = math.max(0, math.min(100, tonumber(S.volume) or 60))
    S.sound = S.sound ~= false
    S.jit = S.jit ~= false
    S.binds = input.load(t.binds) -- (older versions kept window key codes in S.keys: replaced by the defaults)
end

-- (1.8c) Test switch for a hard fault that lands on a different step every time (Ricc): /cb jit off runs the add-on's
-- own Lua without LuaJIT's compiler. The emulator core is native code either way, so games run the same.
local function apply_jit()
    if type(jit) ~= 'table' or not jit.off or not jit.on then return false end
    if S.jit == false then
        jit.off()
        if jit.flush then jit.flush() end
    else
        jit.on()
    end
    return true
end

local function load_rules()
    local t, err = util.load_table(P.cfg .. 'rewards.lua')
    if not t then
        if err ~= 'missing' then say('rewards.lua has a problem: ' .. tostring(err)) end
        t = {}
    end
    -- games added in a later version (the addon's rewards_default.lua) count too; your own rewards.lua wins
    local defaults = util.load_table(P.addon .. 'rewards_default.lua')
    for title, rule in pairs(type(defaults) == 'table' and defaults or {}) do
        if t[title] == nil then t[title] = rule end
    end
    G.rules = t
end

local function load_claims()
    G.claims = util.load_table(char_dir('claims') .. 'claims.lua') or {}
    G.play = util.load_table(char_dir('claims') .. 'playtime.lua') or {}
end

-- Play time per character and game (seconds). Only time spent actually playing counts: the window has focus,
-- the game is not paused, and a key or button was pressed in the last two minutes. Fast forward counts as normal time.
local IDLE = 120
local function save_play()
    if G.char and G.play then util.save_table(char_dir('claims') .. 'playtime.lua', G.play) end
end

local function hm(sec)
    sec = math.floor(sec or 0)
    return string.format('%dh %02dm', math.floor(sec / 3600), math.floor(sec % 3600 / 60))
end

local function inventory()
    local ok, inv = pcall(function() return AshitaCore:GetMemoryManager():GetInventory() end)
    if ok then return inv end
    return nil
end

--- What the character owns right now (the bags as the server sent them).
local function refresh_owned()
    G.owned = carts.owned(inventory())
    return G.owned
end

local function load_cart_config()
    local t = util.load_table(P.cfg .. 'cartridges.lua')
    if type(t) == 'table' then carts.merge(t) end
end

------------------------------------------------------------------------------
-- Core and games
------------------------------------------------------------------------------
local function find_core()
    local dir = P.addon .. 'cores\\'
    if S.core ~= '' and ashita.fs.exists(dir .. S.core) then return dir .. S.core end
    for _, name in ipairs(list_dir(dir)) do
        if name:lower():match('_libretro%.dll$') then return dir .. name end
    end
    return nil
end

local function ensure_core()
    if retro.is_open() then return true end
    local path = find_core()
    if not path then
        G.core_error = 'No emulator core found. Run install_crystalboy.py again.'
        return false
    end
    local vars = { gambatte_gb_colorization = S.palette, gambatte_gb_hwmode = 'Auto' }
    local ok, err = retro.open(path, P.cfg .. 'system', vars)
    if not ok then G.core_error = err; return false end
    G.core_error = nil
    return true
end

local function rescan()
    G.roms = games.scan(P.cfg .. 'roms', list_dir, util.read)
end

local function sav_path() return char_dir('saves') .. util.clean(G.game.stem) .. '.sav' end
local function state_path(slot) return char_dir('states') .. util.clean(G.game.stem) .. '.state' .. slot end

local function check_done(why)
    if not G.game or not G.game.header then return end
    local title = G.game.header.title
    local rule = G.rules[title]
    if not rule or G.claims[title] then return end
    local mem = { save = retro.memory(retro.MEM_SAVE), ram = retro.memory(retro.MEM_SYSTEM) }
    local hours = tonumber(rule.playtime_hours)
    local by_time = hours and hours > 0 and ((G.play or {})[title] or 0) >= hours * 3600
    if by_time or rewards.check_rule(rule, mem) then
        G.claims[title] = { name = rule.name or title, rom = G.game.file, finished = os.date('%Y-%m-%d %H:%M'),
                            delivered = false }
        util.save_table(char_dir('claims') .. 'claims.lua', G.claims)
        say(string.format('*** %s COMPLETE! *** Recorded for %s.', rule.name or title, G.char))
        note((rule.name or title) .. ' complete!')
    end
end

--- Write the battery save if it changed since the last write.
local function flush_save()
    if not (G.game and retro.loaded()) then return end
    local cur = retro.memory(retro.MEM_SAVE)
    if not cur or cur == G.last_sav then return end
    local path = sav_path()
    if not G.sav_backed_up then
        local old = util.read(path)
        if old then util.write(path .. '.bak', old) end
        G.sav_backed_up = true
    end
    local ok, err = util.write(path, cur)
    if ok then G.last_sav = cur else say('Could not write the save file: ' .. tostring(err)) end
    check_done('save')
end

local function stop_game()
    if G.game then flush_save(); save_play() end
    pcall(audio.flush)
    retro.unload_game()
    G.game = nil
    G.cart = nil
    G.last_sav = nil
    for k in pairs(retro.pressed) do retro.pressed[k] = nil end
end

local function start_game(entry)
    if not char_name() then say('Log in to a character first: saves are kept per character.'); return end
    if entry.problem then say(entry.file .. ': ' .. entry.problem); return end
    trace.again()
    trace.log('start_game ' .. entry.file)
    if not ensure_core() then say(G.core_error); return end
    trace.log('core ready ' .. tostring(retro.core_name()))
    stop_game()
    G.char = char_name()
    load_claims()
    load_rules()
    local rom = util.read(entry.path)
    if not rom then say('Could not read ' .. entry.path); return end
    trace.log('load_game ' .. entry.file .. ' ' .. #rom)
    local ok, err = retro.load_game(rom, entry.path)
    trace.log('load_game -> ' .. tostring(ok) .. ' ' .. tostring(err))
    if not ok then say(entry.file .. ': ' .. tostring(err)); return end
    G.game = entry
    G.sav_backed_up = false
    local sav = util.read(sav_path())
    if sav then
        trace.log('set_memory ' .. #sav .. ' bytes into ' .. tostring(#(retro.memory(retro.MEM_SAVE) or '')))
        if not retro.set_memory(retro.MEM_SAVE, sav) then say('Note: the save file is bigger than this game expects.') end
    end
    G.last_sav = retro.memory(retro.MEM_SAVE)
    G.acc, G.last_tick, G.paused = 0, nil, false
    say(string.format('Playing %s (%s) as %s.', entry.file, entry.header.title, G.char))
    check_done('load')
end

local function cart_name(id) return (carts.list[id] and carts.list[id].name) or ('Cartridge ' .. tostring(id)) end

--- Open the window. Only with a Crystal Boy in one of your bags.
local function open_window()
    if not char_name() then say('Log in to a character first.'); return false end
    if not refresh_owned().crystal_boy then
        say('You need a Crystal Boy in your inventory to play.')
        G.open[1] = false
        return false
    end
    G.open[1] = true
    return true
end

--- Start the game on one of your cartridges.
local function play_cart(id)
    if not open_window() then return end
    if not G.owned.carts[id] then say('That cartridge must be in your inventory.'); return end
    if G.cart == id and G.game then return end
    rescan()
    local rom = carts.rom_for(id, G.roms)
    if not rom then
        say(string.format('No ROM for %s yet. Put your own copy of the game in %sroms (any file name; it is matched by the title inside the ROM).',
            cart_name(id), P.cfg))
        return
    end
    start_game(rom)
    if G.game then G.cart = id end
end

local function save_state(slot)
    if not G.game then say('No game is running.'); return end
    local data, err = retro.save_state()
    if not data then say(err); return end
    local ok, werr = util.write(state_path(slot), data)
    if ok then note('Saved state ' .. slot) else say('Could not write the state: ' .. tostring(werr)) end
end

local function load_state(slot)
    if not G.game then say('No game is running.'); return end
    local data = util.read(state_path(slot))
    if not data then note('State ' .. slot .. ' is empty'); return end
    local ok, err = retro.load_state(data)
    if ok then note('Loaded state ' .. slot) else say(err) end
end

------------------------------------------------------------------------------
-- Snapshots (to find which bytes mean "game finished")
------------------------------------------------------------------------------
local function snap_path(name, kind)
    mkdir(P.cfg .. 'snaps')
    return P.cfg .. 'snaps\\' .. util.clean(G.game.stem) .. '__' .. util.clean(name) .. '.' .. kind .. '.bin'
end

local function snap(name)
    if not G.game then say('Start the game first.'); return end
    name = name or 'snap'
    local n = 0
    for _, kind in ipairs({ 'save', 'ram' }) do
        local bytes = retro.memory(kind == 'save' and retro.MEM_SAVE or retro.MEM_SYSTEM)
        if bytes then util.write(snap_path(name, kind), bytes); n = n + 1 end
    end
    say(string.format('Snapshot "%s" taken (%d memory areas).', name, n))
end

local function diff(a, b, kind)
    if not G.game then say('Start the game first.'); return end
    kind = (kind == 'ram') and 'ram' or 'save'
    local x, y = util.read(snap_path(a, kind)), util.read(snap_path(b, kind))
    if not x or not y then say('Snapshot not found. Take them with /cb snap <name>.'); return end
    local d = rewards.diff(x, y)
    local lines = { string.format('%s: %s -> %s, %d bytes changed', kind, a, b, #d) }
    for _, e in ipairs(d) do
        lines[#lines + 1] = string.format('at=0x%04X  %3d -> %3d   (0x%02X -> 0x%02X)', e[1], e[2], e[3], e[2] % 256, e[3] % 256)
    end
    local out = P.cfg .. 'snaps\\' .. util.clean(G.game.stem) .. '__diff_' .. util.clean(a) .. '_' .. util.clean(b) .. '_' .. kind .. '.txt'
    util.write(out, table.concat(lines, '\n') .. '\n')
    for i = 1, math.min(#lines, 16) do say(lines[i]) end
    if #lines > 16 then say('... full list in ' .. out) end
end

------------------------------------------------------------------------------
-- Emulation timing
------------------------------------------------------------------------------
------------------------------------------------------------------------------
-- Input: keyboard and controllers go to the Crystal Boy only while its window has focus
------------------------------------------------------------------------------
local PAD = { up = 'UP', down = 'DOWN', left = 'LEFT', right = 'RIGHT', a = 'A', b = 'B', start = 'START', select = 'SELECT' }

local function release_all()
    input.clear()
    for k in pairs(retro.pressed) do retro.pressed[k] = nil end
    G.ff_hold = false
    G.held = {}
end

local function set_of(list)
    local t = {}
    for _, e in ipairs(list) do t[e[1] .. ':' .. tostring(e[2])] = e end
    return t
end

--- Waiting for "press a key / button" in the Controls panel.
local function do_capture()
    local c = G.capture
    local now = set_of(input.pressed_now())
    for k in pairs(c.baseline) do if not now[k] then c.baseline[k] = nil end end -- released keys may be pressed again
    for k, e in pairs(now) do
        if not c.baseline[k] then
            local kind, code = e[1], e[2]
            if kind == 'kb' and code == input.DIK.ESCAPE then
                G.capture = nil; note('Cancelled'); return
            end
            if (c.kind == 'kb' and kind == 'kb') or (c.kind == 'pad' and kind ~= 'kb') then
                S.binds[kind][c.action] = code
                save_settings()
                note(c.label .. ' = ' .. input.name(kind, code))
                G.capture = nil
                c.baseline = now
                return
            end
        end
    end
end

local function apply_input()
    if not (G.open[1] and G.focused) then release_all(); return end
    if G.capture then
        for k in pairs(retro.pressed) do retro.pressed[k] = nil end
        do_capture()
        return
    end
    if #input.pressed_now() > 0 then G.last_input = now_s() end
    for action, button in pairs(PAD) do
        retro.pressed[retro[button]] = input.held(action, S.binds) or nil
    end
    G.ff_hold = input.held('fast', S.binds)
    for _, action in ipairs({ 'save', 'load' }) do
        local down = input.held(action, S.binds)
        if down and not G.held[action] and G.game then
            trace.log('key: ' .. action .. ' state'); trace.step('key ' .. action .. ' state')
            if action == 'save' then save_state(S.slot) else load_state(S.slot) end
        end
        G.held[action] = down or nil
    end
end

local function tick()
    local t = now_ms()
    if not G.last_tick then G.last_tick = t; return end
    local dt = (t - G.last_tick) / 1000
    G.last_tick = t
    if dt > 0.25 then dt = 0.25 end -- after a stall, do not race to catch up
    local running = G.game and retro.loaded() and G.open[1] and not G.paused
                    and not (S.pause_unfocused and not G.focused)
    if not running then G.acc = 0; return end
    if G.game.header and G.play and now_s() - (G.last_input or -1e9) <= IDLE then
        local title = G.game.header.title
        G.play[title] = (G.play[title] or 0) + dt
        if now_s() >= (G.next_play_save or 0) then G.next_play_save = now_s() + 30; save_play() end
    end
    local fast = G.ff_hold or G.ff_toggle
    local speed = fast and S.ff_speed or 1
    G.acc = G.acc + dt * retro.fps() * speed
    local cap = 3 * speed
    local n = math.floor(G.acc)
    if n > cap then n = cap; G.acc = 0 else G.acc = G.acc - n end
    trace.log('run ' .. n .. ' frames', 'run', 40); trace.step('run ' .. n .. ' frames')
    retro.run(n)
    trace.log('run done', 'rundone', 40); trace.step('run done')
    -- (1.5) sound: what the core produced in these frames goes to the sound device. Not while fast forwarding (it would
    -- only be noise), and never allowed to break the game: any failure switches the sound off for this session.
    local samples, frames = retro.audio_take()
    if S.sound and not G.audio_failed and not fast and frames > 0 then
        trace.step('audio')
        local ok, err = pcall(function()
            if not audio.is_open() or audio.rate() ~= retro.sample_rate() then
                local opened, why = audio.open(retro.sample_rate())
                trace.log('audio open ' .. tostring(retro.sample_rate()) .. ' -> ' .. tostring(opened) .. ' ' .. tostring(why))
                if not opened then error(why or 'no sound device') end
            end
            audio.write(samples, frames, S.volume)
        end)
        if not ok then
            G.audio_failed = true
            trace.log('audio off: ' .. tostring(err))
            say('Crystal Boy: no sound this session (' .. tostring(err) .. ').')
        end
        trace.step('audio done')
    end
    if now_s() >= G.next_flush then
        G.next_flush = now_s() + 3
        trace.step('save flush'); flush_save(); trace.step('save flush done')   -- (1.8b, Ricc's crash after 'audio done')
    end
    if G.rec and now_s() >= G.rec.next then
        -- recorder: the game's working memory once a second, so the "finished" bytes can be found afterwards
        G.rec.next = now_s() + 1
        local ram = retro.memory(retro.MEM_SYSTEM)
        if ram then
            G.rec.n = G.rec.n + 1
            util.write(G.rec.dir .. string.format('%05d.bin', G.rec.n), ram)
            if G.rec.n >= 3600 then G.rec = nil; say('Recorder stopped (one hour recorded).') end
        end
    end
    if now_s() >= G.next_ram_check then
        G.next_ram_check = now_s() + 2
        local rule = G.game and G.game.header and G.rules[G.game.header.title]
        if rule then trace.step('ram check'); check_done('check'); trace.step('ram check done') end
    end
end

------------------------------------------------------------------------------
-- Window
------------------------------------------------------------------------------
local function draw()
    if not G.open[1] then G.focused = false; return end
    imgui.SetNextWindowSize({ 160 * S.scale + 20, 144 * S.scale + 120 }, ImGuiCond_FirstUseEver)
    -- (1.6) no keyboard / controller navigation inside this window: the keys you play with (Enter = Start, Space = fast)
    -- are also ImGui's "press the highlighted button" keys, so playing could press Save state, Load state or Reset
    if imgui.Begin('Crystal Boy', G.open, bit.bor(ImGuiWindowFlags_AlwaysAutoResize, ImGuiWindowFlags_NoNavInputs or 0)) then
        G.focused = imgui.IsWindowFocused()

        local preview = G.cart and cart_name(G.cart) or 'Choose a cartridge...'
        imgui.PushItemWidth(160 * S.scale - 150)
        if imgui.BeginCombo('##cart', preview) then
            local ids = carts.sorted(G.owned.carts)
            if #ids == 0 then imgui.Text('You have no cartridges yet.') end
            for _, id in ipairs(ids) do
                local label = cart_name(id) .. (carts.rom_for(id, G.roms) and '' or '  (ROM missing)')
                if imgui.Selectable(label .. '##' .. id, G.cart == id) then play_cart(id) end
            end
            imgui.EndCombo()
        end
        imgui.PopItemWidth()
        imgui.SameLine()
        if imgui.Button('Rescan') then rescan() end
        imgui.SameLine()
        if imgui.Button(G.paused and 'Resume' or 'Pause') then G.paused = not G.paused end

        local w, h = 160 * S.scale, 144 * S.scale
        if G.game then
            trace.log('screen.update', 'su', 40); trace.step('screen.update')
            screen.update(retro.frame())
            trace.log('screen.update done', 'sud', 40); trace.step('screen.update done')
            local id, u, v = screen.image()
            trace.log('image ' .. tostring(id), 'img', 40); trace.step('image ' .. tostring(id))
            if id then imgui.Image(id, { w, h }, { 0, 0 }, { u, v }) else imgui.Dummy({ w, h }) end
            trace.step('image drawn')
        else
            imgui.Dummy({ w, h / 2 })
            if G.core_error then imgui.TextColored({ 1, 0.45, 0.45, 1 }, G.core_error) end
            imgui.TextWrapped('Choose one of your cartridges above. Your own ROM files go in config\\addons\\crystalboy\\roms (matched by the title inside the ROM).')
            imgui.Dummy({ w, h / 2 - 40 })
        end

        if imgui.Button((G.ff_toggle and '>> Fast: ON' or '>> Fast: off')) then G.ff_toggle = not G.ff_toggle end
        imgui.SameLine()
        for i = 1, 3 do
            if imgui.RadioButton(tostring(i), S.slot == i) then S.slot = i; save_settings() end
            imgui.SameLine()
        end
        if imgui.Button('Save state') then trace.log('button: save state'); trace.step('button save state'); save_state(S.slot); trace.step('button save state done') end
        imgui.SameLine()
        if imgui.Button('Load state') then trace.log('button: load state'); trace.step('button load state'); load_state(S.slot); trace.step('button load state done') end
        imgui.SameLine()
        if imgui.Button('Reset') and G.game then trace.log('button: reset'); trace.step('button reset'); retro.reset(); trace.step('button reset done') end
        imgui.SameLine()
        if imgui.Button(S.sound and 'Sound: on' or 'Sound: off') then
            S.sound = not S.sound; G.audio_failed = nil
            if not S.sound then pcall(audio.flush) end
            save_settings()
        end

        imgui.SameLine()
        if imgui.Button(G.show_controls and 'Controls ^' or 'Controls') then G.show_controls = not G.show_controls; G.capture = nil end
        if G.show_controls then
            imgui.Separator()
            imgui.Text('Click a box, then press the key or controller button (Esc cancels).')
            for _, a in ipairs(input.ACTIONS) do
                local id = a.id
                imgui.Text(a.label)
                imgui.SameLine(150)
                local waiting = G.capture and G.capture.action == id
                local kbl = (waiting and G.capture.kind == 'kb') and 'press a key...' or input.name('kb', S.binds.kb[id])
                if imgui.Button(kbl .. '##kb_' .. id, { 140, 0 }) then
                    G.capture = { action = id, kind = 'kb', label = a.label, baseline = set_of(input.pressed_now()) }
                end
                imgui.SameLine()
                local padl = (waiting and G.capture.kind == 'pad') and 'press a button...'
                    or (input.name('xi', S.binds.xi[id]) .. ' | ' .. input.name('di', S.binds.di[id]))
                if imgui.Button(padl .. '##pad_' .. id, { 260, 0 }) then
                    G.capture = { action = id, kind = 'pad', label = a.label, baseline = set_of(input.pressed_now()) }
                end
            end
            if imgui.Button('Reset controls') then S.binds = input.defaults(); save_settings(); note('Controls reset') end
            imgui.SameLine()
            imgui.TextWrapped('Controller: Xbox-style | PlayStation-style. The left stick also moves.')
            imgui.Separator()
        end

        local status
        if G.capture then status = 'Waiting for ' .. G.capture.label .. ' ... (Esc cancels)'
        elseif G.msg ~= '' and now_s() < G.msg_until then status = G.msg
        elseif not G.game then status = 'No cartridge in'
        elseif G.paused then status = 'Paused'
        elseif S.pause_unfocused and not G.focused then status = 'Paused (click here to play)'
        else status = (G.ff_hold or G.ff_toggle) and ('Fast forward x' .. S.ff_speed) or 'Playing' end
        local title = G.game and G.game.header and G.game.header.title
        local done = title and G.claims[title]
        local rule = title and G.rules[title]
        local extra = ''
        if done then extra = '   |   Completed'
        elseif rule and tonumber(rule.playtime_hours) then
            extra = string.format('   |   %s / %gh', hm((G.play or {})[title]), tonumber(rule.playtime_hours))
        end
        imgui.Text(status .. extra)
        trace.step('window drawn')
    end
    imgui.End()
end

------------------------------------------------------------------------------
-- Ashita events
------------------------------------------------------------------------------
local function split(s)
    local t = {}
    for w in s:gmatch('%S+') do t[#t + 1] = w end
    return t
end

local HELP = {
    '/cb                 open or close the Crystal Boy window (needs a Crystal Boy in your inventory)',
    'Use the Crystal Boy or a cartridge from your items to play.',
    '/cb list            your cartridges and the ROM files found',
    '/cb stop            stop the game (the save is written first)',
    '/cb ff              fast forward on/off (or hold Space while playing)',
    '/cb save [1-3]      save state            /cb load [1-3]   load state',
    '/cb scale <1-6>     picture size          /cb speed <2-10> fast forward speed',
    '/cb sound [on|off]  the game\'s sound       /cb volume <0-100>',
    '/cb snap <name>     memory snapshot       /cb diff <a> <b> [ram]  what changed',
    '/cb record          record the game memory once a second (start / stop)',
    '/cb done            which games this character has completed',
    '/cb jit [on|off]    test mode for crashes: off runs the add-on without the Lua compiler',
    'Click the window to play (keys and controller then go to the Crystal Boy only); click the game to give them back.',
    'Default keys: arrows, X = A, Z = B, Enter = Start, Backspace = Select, Space = fast, F5/F7 = save/load state.',
    'Change keys and controller buttons with the Controls button in the window.',
}

ashita.events.register('load', 'cb_load', function()
    local install = AshitaCore:GetInstallPath()
    if not install:match('[\\/]$') then install = install .. '\\' end
    P.addon = install .. 'addons\\crystalboy\\'
    P.cfg = install .. 'config\\addons\\crystalboy\\'
    mkdir(install .. 'config\\addons')
    mkdir(P.cfg)
    mkdir(P.cfg .. 'roms')
    mkdir(P.cfg .. 'system')
    trace.start(P.cfg .. 'trace.txt')
    retro.trace = trace.log
    trace.log('addon ' .. addon.version .. ' loaded')
    load_settings()
    if S.jit == false then apply_jit() end
    trace.log('compiler ' .. (S.jit and 'on' or 'off'))
    load_rules()
    load_cart_config()
    screen.init(require('d3d8'))
    rescan()
end)

ashita.events.register('unload', 'cb_unload', function()
    stop_game()
    pcall(audio.close)
    retro.close()
    screen.release()
    save_settings()
end)

ashita.events.register('command', 'cb_command', function(e)
    local a = split(e.command)
    local c = (a[1] or ''):lower()
    if c ~= '/cb' and c ~= '/crystalboy' then return end
    e.blocked = true
    local sub = (a[2] or ''):lower()
    if sub == '' or sub == 'show' or sub == 'open' then
        if sub == '' and G.open[1] then G.open[1] = false else open_window() end
    elseif sub == 'help' then
        for _, l in ipairs(HELP) do say(l) end
    elseif sub == 'list' then
        rescan()
        refresh_owned()
        say('Crystal Boy: ' .. (G.owned.crystal_boy and 'yes' or 'no'))
        local ids = carts.sorted(G.owned.carts)
        if #ids == 0 then say('Cartridges: none yet.') end
        for _, id in ipairs(ids) do
            local r = carts.rom_for(id, G.roms)
            say(string.format('Cartridge: %s  ->  %s', cart_name(id), r and r.file or 'ROM missing'))
        end
        if #G.roms == 0 then say('No ROM files in ' .. P.cfg .. 'roms') end
        for i, r in ipairs(G.roms) do
            local h = r.header
            say(string.format('ROM %d. %s  %s', i, r.file,
                h and string.format('[%s, %s%s]', h.title, h.cart, h.color and ', color' or '') or ('(' .. tostring(r.problem) .. ')')))
        end
    elseif sub == 'stop' then
        stop_game(); say('Stopped.')
    elseif sub == 'ff' then
        G.ff_toggle = not G.ff_toggle; say('Fast forward ' .. (G.ff_toggle and 'on' or 'off'))
    elseif sub == 'save' then
        save_state(tonumber(a[3]) or S.slot)
    elseif sub == 'load' then
        load_state(tonumber(a[3]) or S.slot)
    elseif sub == 'scale' then
        S.scale = math.max(1, math.min(6, tonumber(a[3]) or S.scale)); save_settings(); say('Scale ' .. S.scale)
    elseif sub == 'sound' then
        if a[3] == 'on' or a[3] == 'off' then S.sound = a[3] == 'on' else S.sound = not S.sound end
        G.audio_failed = nil
        if not S.sound then pcall(audio.flush) end
        save_settings(); say('Sound ' .. (S.sound and 'on' or 'off'))
    elseif sub == 'jit' then
        if a[3] == 'on' or a[3] == 'off' then
            S.jit = a[3] == 'on'
            save_settings()
            trace.log('compiler ' .. (S.jit and 'on' or 'off') .. ' (command)')
            if apply_jit() then say('Compiler ' .. (S.jit and 'on' or 'off') .. ' (remembered for next time).')
            else say('This game build has no compiler switch.') end
        else
            say('Compiler is ' .. (S.jit and 'on' or 'off') .. '. /cb jit off = test mode for crashes, /cb jit on = normal.')
        end
    elseif sub == 'volume' then
        S.volume = math.max(0, math.min(100, tonumber(a[3]) or S.volume)); save_settings(); say('Volume ' .. S.volume)
    elseif sub == 'speed' then
        S.ff_speed = math.max(2, math.min(10, tonumber(a[3]) or S.ff_speed)); save_settings(); say('Fast forward x' .. S.ff_speed)
    elseif sub == 'record' then
        if G.rec then
            say(string.format('Recorder stopped: %d snapshots in %s', G.rec.n, G.rec.dir)); G.rec = nil
        elseif not G.game then
            say('Start the game first.')
        else
            local dir = P.cfg .. 'snaps\\rec_' .. os.date('%Y%m%d_%H%M%S') .. '\\'
            mkdir(dir)
            G.rec = { dir = dir, n = 0, next = 0 }
            say('Recording the game memory once a second. Beat the boss, watch the ending, then /cb record again to stop.')
        end
    elseif sub == 'snap' then
        snap(a[3])
    elseif sub == 'diff' then
        diff(a[3] or 'before', a[4] or 'after', a[5])
    elseif sub == 'check' then
        load_rules(); check_done('command'); say('Checked.')
    elseif sub == 'done' then
        if not G.char then G.char = char_name() end
        if not G.char then say('Log in first.'); return end
        load_claims()
        local n = 0
        for _, c2 in pairs(G.claims) do n = n + 1; say('Completed: ' .. tostring(c2.name) .. ' on ' .. tostring(c2.finished)) end
        if n == 0 then say(G.char .. ' has not completed any games yet.') end
        for title, sec in pairs(G.play or {}) do
            local r = G.rules[title]
            local need = r and tonumber(r.playtime_hours)
            say(string.format('Played %s: %s%s', (r and r.name) or title, hm(sec), need and (' of ' .. need .. 'h') or ''))
        end
    else
        say('Unknown command. /cb help')
    end
end)

-- Using the Crystal Boy or a cartridge from the item menu: the game sends "use item" (0x37) with the bag and slot.
-- The addon answers it here and the packet never reaches the server, so the item is not used up.
-- (Without the addon the server has no script for these items and replies "Unable to use item".)
ashita.events.register('packet_out', 'cb_packet_out', function(e)
    if e.id ~= 0x37 then return end
    local data = e.data_modified or e.data
    if type(data) ~= 'string' or #data < 0x11 then return end
    local slot, bag = data:byte(0x0E + 1), data:byte(0x10 + 1)
    local id = carts.item_at(inventory(), bag, slot)
    if id == carts.CRYSTAL_BOY then
        e.blocked = true
        open_window()
    elseif id and carts.is_cart(id) then
        e.blocked = true
        play_cart(id)
    end
end)

-- While the Crystal Boy window has focus, every key and controller button belongs to it: FFXI gets an
-- empty keyboard and controller (so your character does not walk off while you play). Click the game to give them back.
local function captured() return G.open[1] and G.focused end

-- (1.5) Every input and frame handler runs guarded: a Lua error in one of them is written to the trace with the line
-- it happened on (once per handler) and the add-on carries on, instead of Ashita reporting "exception in event" and the
-- error being lost. A crash inside the emulator itself is not a Lua error and still ends in the trace's last step.
local guard_seen = {}
local function guarded(name, f)
    return function(e)
        local ok, err = xpcall(function() return f(e) end, debug.traceback)
        if not ok and not guard_seen[name] then
            guard_seen[name] = true
            trace.log('ERROR in ' .. name .. ': ' .. tostring(err))
            pcall(say, 'Crystal Boy hit an error in "' .. name .. '" and carried on. Please send Ashita/config/addons/crystalboy/trace.txt in a bug report.')
        end
    end
end
local function register(event, alias, f) ashita.events.register(event, alias, guarded(event, f)) end

register('key', 'cb_key', function(e)
    if not captured() then return end
    -- (1.8, Ricc: Enter still did nothing) some keys, Enter among them, only ever arrive as window messages on some
    -- setups. The message carries the key's scan code (lParam bits 16-23, bit 24 = extended), which is the same
    -- number the keyboard table uses, so the key counts as pressed from here too. Bit 31 set = released.
    local lp = tonumber(e.lparam)
    if lp then
        local scan = bit.band(bit.rshift(lp, 16), 0xFF)
        if bit.band(lp, 0x01000000) ~= 0 then scan = bit.bor(scan, 0x80) end
        local down = bit.band(lp, 0x80000000) == 0
        if scan > 0 then
            trace.log('key msg ' .. scan .. ' ' .. tostring(down), 'km', 20)
            input.key_data(scan, down)
        end
    end
    e.blocked = true -- window messages (chat, menus)
end)

-- (1.7) Ricc: arrows moved the character too and Enter never reached the Crystal Boy. FFXI also reads the keyboard's
-- buffered events (key_data); they were neither read nor blocked. Now they are both while the window has focus.
register('key_data', 'cb_key_data', function(e)
    if not captured() then return end
    trace.log('key_data ' .. tostring(e.key) .. ' ' .. tostring(e.down), 'kd', 20)
    input.key_data(e.key, e.down)
    e.blocked = true
end)

register('key_state', 'cb_key_state', function(e)
    if not captured() then return end
    -- (1.4) the pointer to the game's own key table when there is one; a string (a copy) is only read
    local ptr = e.data_raw
    if ptr == nil or type(ptr) == 'string' then ptr = e.data end
    if ptr == nil or (e.size and e.size < 256) then return end
    trace.log('key_state ' .. type(ptr) .. ' raw ' .. type(e.data_raw) .. ' data ' .. type(e.data) .. ' size ' .. tostring(e.size), 'ks', 10)
    trace.step('key_state ' .. type(ptr))
    pcall(input.take_keyboard, ptr, true)
    trace.log('key_state done', 'ksd', 10)
end)

register('xinput_state', 'cb_xinput_state', function(e)
    if not captured() or e.state == nil then return end
    trace.log('xinput_state ' .. type(e.state), 'xs', 10)
    trace.step('xinput_state')
    pcall(input.take_xinput, e.state, e.state_modified)
end)

register('xinput_button', 'cb_xinput_button', function(e)
    if captured() then e.blocked = true end
end)

register('dinput_button', 'cb_dinput_button', function(e)
    if not captured() then return end
    trace.log('dinput ' .. tostring(e.button) .. ' ' .. tostring(e.state), 'di', 20)
    trace.step('dinput_button')
    input.dinput(e.button, e.state)
    e.blocked = true
end)

register('d3d_present', 'cb_present', function()
    local c = char_name()
    if G.game and c ~= G.char then
        stop_game() -- logged out or switched character: keep saves apart
        say('Character changed: the game was stopped and saved.')
    end
    if (G.open[1] or G.game) and now_s() >= G.next_own then
        G.next_own = now_s() + 5
        refresh_owned()
        if not G.owned.crystal_boy then
            if G.game then stop_game(); say('The Crystal Boy is no longer in your inventory: the game was stopped and saved.') end
            G.open[1] = false
        elseif G.cart and not G.owned.carts[G.cart] then
            stop_game(); say('That cartridge is no longer in your inventory: the game was stopped and saved.')
        end
    end
    trace.log('present: input', 'p1', 40); trace.step('present: input')
    apply_input()
    trace.log('present: tick', 'p2', 40); trace.step('present: tick')
    tick()
    trace.log('present: draw', 'p3', 40); trace.step('present: draw')
    draw()
    trace.log('present: end', 'p4', 40); trace.step('present: end')
end)
