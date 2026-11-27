-- GambitsV2 (standalone addon): stand-in tests for the shell, transport.lua and the editor's flows, end to end against
-- the REAL server modules (gambits_squad.lua, squad_rulesets.lua, squad_rulesets_store.lua) through a fake game client.
--   luajit test_gambitsv2_addon.lua <server>/modules/custom/lua <server>/scripts/globals/gambits.lua
--                                    <server>/scripts/enum/job_ability.lua <kit>/addons-src/GambitsV2 <empty work folder>
-- The fake client behaves as the real one did in game (2026-11-19): it shows "Name : <text>" for a /say it sent, and
-- ">> <line>" + "...A command error occurred." for one it refused because it came less than 0.6 s after the last one.
-- Lines reach the addon as the timestamp addon leaves them (e.message_modified with "[hh:mm:ss] " in front).
-- Files are written only inside the work folder.
local LUA_DIR, GAMBITS, JA_ENUM, ADDON_DIR, WORK = arg[1], arg[2], arg[3], arg[4], arg[5]
assert(LUA_DIR and GAMBITS and JA_ENUM and ADDON_DIR and WORK, 'usage: test_gambitsv2_addon.lua lua-dir gambits.lua job_ability.lua addon-dir work-dir')
package.path = ADDON_DIR .. '/?.lua;' .. package.path
local passed, failed = 0, 0
local function check(c, l) if c then passed = passed + 1 else failed = failed + 1; io.write('FAIL: ', l, '\n') end end
local function section(n) io.write('\n== ', n, '\n') end
local function deq(a, b)
    if type(a) ~= type(b) then return false end
    if type(a) ~= 'table' then return a == b end
    for k, v in pairs(a) do if not deq(v, b[k]) then return false end end
    for k in pairs(b) do if a[k] == nil then return false end end
    return true
end
local sep = package.config:sub(1, 1)

-- ---------------------------------------------------------------- 1. transport.lua alone, with a fake clock
section('transport: interval, other chat, refusals (also with timestamps), echoes, safe resends, zoning')
local T = dofile(ADDON_DIR .. '/transport.lua')
local clock, sent, inputOpen = 100, {}, false
local function tinit(cfg)
    T.init({ now = function() return clock end, queue_command = function(l) sent[#sent + 1] = { l, clock } end,
             input_open = function() return inputOpen end, config = cfg })
    sent = {}
end
local function stamp(line) return '\30\81[22:41:16]\30\1 ' .. line end

tinit()
check(T.get_interval() == 1.0 and T.config.timeout == 3.0, 'defaults: 1.0 s between lines, 3.0 s answer timeout')
local log = {}
local function job(id, lines, extra)
    local j = { id = id, lines = lines,
                on_line = function(f) if f[3] == 'ack' then return 'next' elseif f[3] == 'ok' then return 'done' end end,
                on_done = function() log[#log + 1] = 'done ' .. id end,
                on_fail = function(why, kind) log[#log + 1] = 'fail ' .. id .. ' ' .. kind end }
    for k, v in pairs(extra or {}) do j[k] = v end
    return j
end
T.command_seen('/p on my way')
T.enqueue(job('1', { '/say !gsq ping 1 1' }))
T.tick()
check(#sent == 0, 'a party line of the player just now: the editor waits')
clock = clock + 1.0; T.tick()
check(#sent == 1 and sent[1][2] - 100 >= 1.0, 'and sends 1.0 s after the other chat line')
T.command_seen('/say !gsq ping 1 1')
check(T.stats().foreign == 1, 'its own line (seen by the command event) is not counted as other chat')
T.command_seen('/gambits squad')
T.command_seen('/ma "Cure" <me>')
check(T.stats().foreign == 1, 'commands that are not chat (/gambits, /ma) do not delay anything')
-- refusal, as the game shows it, through the timestamp addon's modified text and through the original text
check(T.text_in(nil, stamp('>> /say !gsq ping 1 1')) == true, 'the refusal echo of our line (timestamped) is recognised and hidden')
check(T.text_in(nil, stamp('...A command error occurred.')) == true, 'the error line right after it is hidden')
check(T.stats().rejected == 1 and T._S.current.state == 'ready', 'the line counts as refused and is ready to go again (it never left the game)')
check(math.abs(T.get_interval() - 1.25) < 1e-9, 'a refusal makes the interval 1.25 x longer (1.25 s)')
clock = clock + 1.0; T.tick()
check(#sent == 1, 'not resent before the (longer) interval')
clock = clock + 0.3; T.tick()
check(#sent == 2 and sent[2][1] == '/say !gsq ping 1 1', 'resent after 1.25 s, unchanged (same request id)')
check(T.text_in('Testcharone : !gsq ping 1 1', stamp('Testcharone : !gsq ping 1 1')) == true and T._S.current.state == 'accepted',
      'the echo of the accepted line marks it sent and is hidden')
check(T.text_in('GSQ|1|ok', stamp('GSQ|1|ok')) == true and log[#log] == 'done 1', 'the answer finishes the job and is hidden')
-- what must stay visible
clock = clock + 5
check(T.text_in('...A command error occurred.') == false, 'a command error with no refusal of ours stays visible')
check(T.text_in('>> /ma "Cure" <p9>') == false, 'the refusal echo of a line that is not ours stays visible')
check(T.text_in('Bob : hello') == false and T.text_in('Testcharone : !squad') == false, 'other chat and own chat stay visible')
T.text_in('>> /say !gsq ping 1 1')
clock = clock + 1.5
check(T.text_in('...A command error occurred.') == false, 'an error line long after a refusal stays visible')
-- too many refusals, and the cap
tinit()
log = {}
T.enqueue(job('2', { '/say !gsq hello 2' }))
for i = 1, 5 do
    clock = clock + 3; T.tick()
    T.text_in('>> /say !gsq hello 2'); T.text_in('...A command error occurred.')
end
check(log[1] == 'fail 2 rejected' and #sent == 4, 'after 3 resends of a refused line the job fails as "rejected" (4 attempts)')
check(T.get_interval() == 2.0, 'the interval stops at 2.0 s')
T.set_interval(1.0)
-- a sent line without an answer: idempotent jobs are resent, others are not
tinit()
log = {}
T.enqueue(job('3', { '/say !gsq list 3 WHM' }))
clock = clock + 1; T.tick()
T.text_in('Testcharone : !gsq list 3 WHM')
clock = clock + 3.1; T.tick()
check(#sent == 2 and T.stats().timeouts == 1, 'no answer within 3 s: an idempotent request is sent again')
clock = clock + 3.1; T.tick(); clock = clock + 3.1; T.tick()
check(log[1] == 'fail 3 unknown' and #sent == 3, 'after 2 resends it fails as "unknown" (never as a plain failure)')
-- noreply jobs (Assign, Apply)
tinit()
log = {}
T.enqueue(job('apply', { '/say !squad reapply' }, { noreply = true, idempotent = false }))
clock = clock + 1; T.tick()
T.text_in(nil, stamp('>> /say !squad reapply')); T.text_in(nil, stamp('...A command error occurred.'))
clock = clock + 1.3; T.tick()
check(#sent == 2, 'Apply refused by the game: sent again (the server never saw it)')
T.text_in(nil, stamp('Testcharone : !squad reapply'))
T.tick()
check(log[1] == 'done apply', 'Apply echoed as sent: done (the editor then reads the squad back)')
T.enqueue(job('apply2', { '/say !squad reapply' }, { noreply = true, idempotent = false }))
clock = clock + 1.3; T.tick()
clock = clock + 1.6; T.tick(); clock = clock + 5; T.tick()
check(#sent == 3 and log[2] == 'fail apply2 unknown', 'Apply with no echo at all: never sent again, reported as unknown')
T.enqueue(job('assign', { '/say !squad ruleset 1 2' }, { noreply = true }))
clock = clock + 1.3; T.tick(); clock = clock + 1.6; T.tick()
clock = clock + 1.3; T.tick()
check(#sent == 5, 'Assign with no echo: sent again (setting a value twice is harmless)')
-- the chat input, zoning
tinit()
log = {}
inputOpen = true
T.enqueue(job('4', { '/say !gsq w 4 1 2 a', '/say !gsq w 4 2 2 b' }))
clock = clock + 2; T.tick()
check(#sent == 0, 'nothing is sent while the player types in the chat input')
inputOpen = false; T.tick()
check(#sent == 1, 'sent once the input is closed')
T.zone(true)
check(T._S.current.state == 'ready' and T.paused(), 'zoning out while waiting: the part is to be sent again (same token), the queue pauses')
clock = clock + 10; T.tick()
check(#sent == 1, 'nothing is sent while zoning')
T.zone(false); clock = clock + 1.0; T.tick()
check(#sent == 1, 'after zoning in it waits a little (2 s)')
clock = clock + 1.1; T.tick()
check(#sent == 2 and sent[2][1] == sent[1][1], 'then sends the same part again')
T.on_reply({ 'GSQ', '4', 'ack', '1', '2' }); clock = clock + 1.0; T.tick()
T.on_reply({ 'GSQ', '4', 'ok' })
check(log[1] == 'done 4', 'and the save finishes normally')

-- ---------------------------------------------------------------- 2. the server modules (real), as in test_gambits_squad.lua
dofile(GAMBITS)
xi = rawget(_G, 'xi') or {}
xi.magic = { spellFamily = setmetatable({ NONE = 0, CURE = 1, CURAGA = 2, PROTECT = 10, SHELL = 11, REGEN = 40 }, { __index = function() return nil end }),
             spell = setmetatable({}, { __index = function(_, k) return type(k) == 'string' and 1 or nil end }) }
xi.effect = setmetatable({}, { __index = function(_, k) return type(k) == 'string' and string.match(k, '^[A-Z_]+$') and 1 or nil end })
xi.objType = { PC = 1, TRUST = 2 }
dofile(JA_ENUM)
SquadOwnerMerit = function(owner, meritId) return (SQUAD_TEST_MERITS or {})[meritId] or 0 end
-- the REAL levelsFor (and jobLevel) out of squad.lua, as squad.lua exports it (xi.squad.levelsFor): the exact code, not a copy
local function realLevelsFor(path)
    local src = assert(io.open(path, 'rb')):read('*a')
    local a = assert(src:find('local function jobLevel%('), 'jobLevel not found in squad.lua')
    local b = assert(src:find('\nxi%.squad%.levelsFor = levelsFor', a), 'squad.lua does not export xi.squad.levelsFor')
    local chunk = 'local SUB_UNLOCK_LEVEL = ' .. assert(src:match('local SUB_UNLOCK_LEVEL = (%d+)')) .. '\n' .. src:sub(a, b) .. '\nreturn levelsFor'
    return assert((loadstring or load)(chunk, '=squad.lua levelsFor'))()
end
xi.squad = xi.squad or {}
xi.squad.levelsFor = realLevelsFor(LUA_DIR .. '/squad.lua')
SQUAD_TEST_SCROLLS, SQUAD_TEST_UNLOCKS = false, {}
squadScrollsOn = function() return SQUAD_TEST_SCROLLS end          -- (squad.lua's global: the launcher's scroll option)
GetSquadUnlocks = function() return SQUAD_TEST_UNLOCKS end          -- (squad.cpp: squad_unlock rows; 60000 + spell id = learned)
local DATA = 'modules/custom/lua/squad_rulesets_data'
local P = WORK .. sep .. 'squad_rulesets_data.lua'
package.preload['modules/custom/lua/squad_rulesets'] = function() return dofile(LUA_DIR .. '/squad_rulesets.lua') end
package.preload['modules/custom/lua/squad_ability_rules'] = function() return dofile(LUA_DIR .. '/squad_ability_rules.lua') end
package.preload['modules/custom/lua/squad_ja_jobs_data'] = function() return dofile(LUA_DIR .. '/squad_ja_jobs_data.lua') end
package.preload['modules/custom/lua/squad_rulesets_store'] = function() return dofile(LUA_DIR .. '/squad_rulesets_store.lua') end
package.preload['modules/custom/lua/squad_spell_jobs_data'] = function() return dofile(LUA_DIR .. '/squad_spell_jobs_data.lua') end
local R = require('modules/custom/lua/squad_rulesets')
local St = require('modules/custom/lua/squad_rulesets_store')
package.preload[DATA] = function() return St.readRaw(P) end
local MANUAL = { format = 'xifo-ruleset-store', version = 1, sets = {
    { format = 'xifo-ruleset', version = 1, num = 1, id = 'custom.whm.cure-basics', name = 'WHM - Cure basics', job = 'WHM', readonly = false,
      rules = { { id = 'r1', on = true, target = 'PARTY', cond = { 'HPP_LT', 40 }, action = { 'family', 'CURE' } },
                { id = 'r2', on = true, target = 'PARTY', cond = { 'HPP_LT', 75 }, action = { 'spell', 'CURE_II' } } } },
    -- (a rule form the wire cannot carry: a { main, sub } argument)
    { format = 'xifo-ruleset', version = 1, num = 2, id = 'custom.whm.main-sub', name = 'WHM - Main and sub', job = 'WHM', readonly = false,
      rules = { { id = 'r1', on = true, target = 'PARTY', cond = { 'HPP_LT', 50 }, action = { 'family', 'CURE' } },
                { id = 'r2', on = true, target = 'SELF', cond = { 'HPP_LT', { main = 50, sub = 30 } }, action = { 'family', 'CURE' } } } } } }
for _, s in ipairs({ '', '.tmp', '.bak', '.old' }) do os.remove(P .. s) end
local f = assert(io.open(P, 'wb')); f:write('return ' .. St.valueText(MANUAL) .. '\n'); f:close()
St.PATH = P
local Gs = dofile(LUA_DIR .. '/gambits_squad.lua')
Gs.now = function() return math.floor(clock) end

-- ---------------------------------------------------------------- 3. a fake game client, Ashita and ImGui
local game = { pending = {}, visible = {}, charvars = {}, party = {}, lastSay = -100, policy = nil, sends = {}, writes = 0, served = {},
               squadSays = 0, dropTo = nil }
local events = {}
local function deliver(text, delay)
    game.pending[#game.pending + 1] = { at = clock + (delay or 0), text = text }
end
local player = {
    getID = function() return 1 end,
    -- the game's chat packet carries at most 150 bytes (GP_SERV_COMMAND_CHAT_STD Mes[150]) and cuts the rest
    printToPlayer = function(_, line) game.served[#game.served + 1] = line; deliver(string.sub(line, 1, 150), game.latency or 0.2) end,
    getPartyWithTrusts = function() return game.party end,
    getCharVar = function(_, k) return game.charvars[k] or 0 end,
    setCharVar = function(_, k, v) game.charvars[k] = v end,
}
local MIRA = { slot = 1, id = 11, name = 'Mira', mjob = 3, sjob = 0, jobs = { [3] = { level = 25 } } }
GetSquad = function() return { MIRA } end
local function trust(id) return { getObjType = function() return xi.objType.TRUST end,
                                  getLocalVar = function(_, k) return k == 'SQUAD_ID' and id or 0 end } end
local realSave = Gs.save
Gs.save = function(edit, charId) game.writes = game.writes + 1; return realSave(edit, charId) end

local function squad_command(text)
    local w = {}
    for word in text:gmatch('%S+') do w[#w + 1] = word end
    if game.ignoreSquad then return end
    if w[1] == 'ruleset' then
        R.command(player, { MIRA }, w[2], w[3], { say = function(p, t) p:printToPlayer(t) end,
            findMate = function(sq, slot) for _, m in ipairs(sq) do if m.slot == slot then return m end end end,
            jobNames = { [3] = 'WHM' } })
    elseif w[1] == 'reapply' then
        game.squadSays = game.squadSays + 1
        if #game.party == 0 then player:printToPlayer('None of your squad mates are out.') return end
        game.party = {}
        if not game.noReturn then game.timers = { at = clock + 4.0, fn = function() game.party = { trust(11) } end } end
    end
end

-- QueueCommand of the game: the command event, then the client's own rules
local function client(line)
    for _, fn in pairs(events.command or {}) do fn({ command = line, blocked = false }) end
    local said = line:match('^/say (.*)$')
    if not said then return end
    local decision = game.policy and game.policy(line) or 'auto'
    if decision == 'auto' then decision = (clock - game.lastSay < 0.6) and 'reject' or 'accept' end
    game.sends[#game.sends + 1] = { line = line, at = clock, decision = decision }
    if decision == 'reject' then
        deliver('>> ' .. line); deliver('...A command error occurred.')
        return
    elseif decision == 'silent' then
        return -- (left the game without the client showing anything; the server gets it)
    elseif decision == 'lost' then
        return -- (never left the game, no message: e.g. a disconnect)
    end

    game.lastSay = clock
    deliver('Testcharone : ' .. said)
    if said:match('^!gsq ') then
        Gs.handle(player, said:sub(6))
    elseif said:match('^!squad ') then
        squad_command(said:sub(8))
    end
end

-- (hotfix 2026-11-21) Ashita's Lua bindings, as addons.dll implements them: SetTooltip, TextWrapped, BulletText and
-- LabelText hand the Lua string to ImGui as a printf FORMAT (no "%s"); Text, TextColored and TextUnformatted draw it
-- unformatted. A format text is accepted only if every '%' is part of '%%' - anything else either prints garbage
-- ("40% and" -> %a) or is rejected by the C runtime, which ends the game (0xC0000409; e.g. "lowest HP % that").
local function format_problem(fmt)
    fmt = tostring(fmt)
    if fmt:gsub('%%%%', ''):find('%', 1, true) then
        return 'a format text with a bare %: ' .. fmt
    end
    return nil
end
local function fakeImgui()
    local g = { colors = 0, vars = 0, ids = 0, children = 0, windows = 0, fonts = 0, disabled = 0, tooltips = 0, wraps = 0,
                errors = {}, clicks = {}, texts = {}, tips = {}, wrapped = {}, formats = 0 }
    local function err(e) g.errors[#g.errors + 1] = e end
    local function shown(t)
        g.texts[#g.texts + 1] = t
        if g.tooltips > 0 then g.tips[#g.tips + 1] = t end
        if g.wraps > 0 then g.wrapped[#g.wrapped + 1] = t end
    end
    local function formatted(fmt)
        g.formats = g.formats + 1
        local why = format_problem(fmt)
        if why then err(why) end
        return (tostring(fmt):gsub('%%%%', '%%'))
    end
    g.Text = function(t) shown(t) end
    g.TextUnformatted = function(t) shown(t) end
    g.TextColored = function(_, t) shown(t) end
    g.TextWrapped = function(fmt) local t = formatted(fmt); g.wraps = g.wraps + 1; shown(t); g.wraps = g.wraps - 1 end
    g.BulletText = function(fmt) shown(formatted(fmt)) end
    g.LabelText = function(_, fmt) shown(formatted(fmt)) end
    g.SetTooltip = function(fmt) local t = formatted(fmt); g.tips[#g.tips + 1] = t end
    g.BeginTooltip = function() g.tooltips = g.tooltips + 1; return true end
    g.EndTooltip = function() g.tooltips = g.tooltips - 1; if g.tooltips < 0 then err('tooltip') end end
    g.PushTextWrapPos = function() g.wraps = g.wraps + 1 end
    g.PopTextWrapPos = function() g.wraps = g.wraps - 1; if g.wraps < 0 then err('wrap') end end
    g.SameLine, g.SetNextItemWidth, g.Separator = function() end, function() end, function() end
    g.IsItemHovered = function() return false end
    g.GetContentRegionAvail = function() return { 1000, 500 } end
    g.Button = function(label) if g.clicks[label] then g.clicks[label] = nil; return true end return false end
    g.Selectable = function(label) if g.clicks[label] then g.clicks[label] = nil; return true end return false end
    g.Checkbox = function(label, t) if g.clicks[label] then g.clicks[label] = nil; t[1] = not t[1]; return true end return false end
    g.InputText, g.InputInt = function() return false end, function() return false end
    g.BeginCombo = function() return false end
    g.EndCombo = function() end
    g.PushStyleColor = function() g.colors = g.colors + 1 end
    g.PopStyleColor = function(n) g.colors = g.colors - (n or 1); if g.colors < 0 then err('colors') end end
    g.PushStyleVar = function() g.vars = g.vars + 1 end
    g.PopStyleVar = function(n) g.vars = g.vars - (n or 1); if g.vars < 0 then err('vars') end end
    g.GetFont, g.GetFontSize = function() return 'font' end, function() return 14 end
    g.PushFont = function() g.fonts = g.fonts + 1 end
    g.PopFont = function() g.fonts = g.fonts - 1 end
    g.PushID = function() g.ids = g.ids + 1 end
    g.PopID = function() g.ids = g.ids - 1 end
    g.BeginChild = function() g.children = g.children + 1; return true end
    g.EndChild = function() g.children = g.children - 1 end
    g.BeginDisabled = function() g.disabled = g.disabled + 1 end
    g.EndDisabled = function() g.disabled = g.disabled - 1 end
    g.SetNextWindowSize = function() end
    g.SetWindowFontScale = function() end
    g.Begin = function(title, open) g.windows = g.windows + 1; g.title = title; return true end
    g.End = function() g.windows = g.windows - 1 end
    return g
end
local function balanced(g)
    return g.colors == 0 and g.vars == 0 and g.ids == 0 and g.children == 0 and g.windows == 0 and g.fonts == 0
        and g.disabled == 0 and g.tooltips == 0 and g.wraps == 0 and #g.errors == 0
end
for _, name in ipairs({ 'ImGuiCol_WindowBg', 'ImGuiCol_ChildBg', 'ImGuiCol_PopupBg', 'ImGuiCol_Text', 'ImGuiCol_TextDisabled',
    'ImGuiCol_Border', 'ImGuiCol_Separator', 'ImGuiCol_FrameBg', 'ImGuiCol_FrameBgHovered', 'ImGuiCol_FrameBgActive',
    'ImGuiCol_Button', 'ImGuiCol_ButtonHovered', 'ImGuiCol_ButtonActive', 'ImGuiCol_Header', 'ImGuiCol_HeaderHovered',
    'ImGuiCol_HeaderActive', 'ImGuiCol_CheckMark', 'ImGuiCol_SliderGrab', 'ImGuiCol_ScrollbarGrab', 'ImGuiCol_TitleBg',
    'ImGuiCol_TitleBgActive', 'ImGuiCol_TitleBgCollapsed', 'ImGuiStyleVar_WindowPadding', 'ImGuiStyleVar_FramePadding',
    'ImGuiStyleVar_ItemSpacing', 'ImGuiStyleVar_ItemInnerSpacing', 'ImGuiStyleVar_WindowRounding', 'ImGuiStyleVar_ChildRounding',
    'ImGuiStyleVar_FrameRounding', 'ImGuiStyleVar_PopupRounding', 'ImGuiStyleVar_FrameBorderSize', 'ImGuiChildFlags_Borders' }) do
    rawset(_G, name, 1)
end

local gui = fakeImgui()
local settingsSaved = 0
package.preload['imgui'] = function() return gui end
package.preload['settings'] = function() return { load = function(d) return d end, save = function() settingsSaved = settingsSaved + 1 end } end
package.loaded['transport'] = nil
local cfgDir = WORK .. sep .. 'config' .. sep .. 'addons' .. sep .. 'GambitsV2'
if sep == '\\' then os.execute('mkdir "' .. cfgDir .. '" >nul 2>nul') else os.execute('mkdir -p "' .. cfgDir .. '"') end
os.remove(cfgDir .. sep .. 'squad_draft.lua')
local chatMgr = { QueueCommand = function(_, mode, line) game.mode = mode; client(line) end, IsInputOpen = function() return false end }
addon = { path = ADDON_DIR .. '/' }
ashita = { events = { register = function(ev, name, fn) events[ev] = events[ev] or {}; events[ev][name] = fn end },
           time = { get_tick64 = function() return clock * 1000 end } }
AshitaCore = { GetChatManager = function() return chatMgr end, GetInstallPath = function() return WORK .. sep end }

local globalsBefore = {}
for k in pairs(_G) do globalsBefore[k] = true end
local GV = dofile(ADDON_DIR .. '/Gambits.lua')  -- (the addon was renamed Gambits on 2026-11-19; its global and settings folder kept their names)
local Ed, Tr = GV.Ed, GV.T

-- the game loop: deliveries (through the text_in event, timestamped), squad timers, then d3d_present
local function step(dt)
    clock = clock + (dt or 0.05)
    local now, keep = {}, {}
    for _, p in ipairs(game.pending) do if p.at <= clock then now[#now + 1] = p else keep[#keep + 1] = p end end
    game.pending = keep
    for _, p in ipairs(now) do
        if not (game.dropTo and p.text:find('GSQ|' .. game.dropTo .. '|', 1, true)) then
            local e = { message = p.text, message_modified = stamp(p.text), blocked = p.blocked or false }
            for _, fn in pairs(events.text_in or {}) do fn(e) end
            if not e.blocked then game.visible[#game.visible + 1] = p.text end
        end
    end

    if game.timers and clock >= game.timers.at then local t = game.timers; game.timers = nil; t.fn() end
    for _, fn in pairs(events.d3d_present or {}) do fn() end
end
local function run_until(cond, limit)
    local start = clock
    while not cond() and clock - start < (limit or 120) do step(0.05) end
    return cond(), clock - start
end
local function idle() return not Ed.busy() and Ed._S.progress == nil and Ed._S.apply == nil end
local function visible_has(pattern)
    for _, l in ipairs(game.visible) do if l:find(pattern) then return true end end
    return false
end
local function cmd(text)
    local e = { command = text, blocked = false }
    for _, fn in pairs(events.command or {}) do fn(e) end
    return e.blocked
end

-- ---------------------------------------------------------------- 4. the shell
section('shell: loading, events, commands, window, themes, no globals')
local evNames = {}
for ev, list in pairs(events) do for name in pairs(list) do evNames[#evNames + 1] = ev .. ':' .. name end end
table.sort(evNames)
check(table.concat(evNames, ' ') == 'command:gv2_command d3d_present:gv2_present load:gv2_load packet_in:gv2_packet_in text_in:gv2_text_in unload:gv2_unload',
      'registers exactly its six events, all named gv2_*: ' .. table.concat(evNames, ' '))
local newGlobals = {}
for k in pairs(_G) do if not globalsBefore[k] then newGlobals[#newGlobals + 1] = tostring(k) end end
check(#newGlobals == 1 and newGlobals[1] == 'GambitsV2', 'defines one global, GambitsV2: ' .. table.concat(newGlobals, ', '))
events.load.gv2_load()
-- (0.3.4) no settings exist here: a NEW installation, which starts with Crimson (an existing one keeps its saved theme:
-- dev/squad-tests/test_theme_default.lua)
check(GV.settings.theme == 'crimson' and Ed.themeName == 'crimson' and Tr.get_interval() == 1.0, 'a new installation starts with Crimson and a 1.0 s interval')
Ed._S.showOptions = true -- (0.3.4: Ping, Theme and Size are behind the Options button; the checks below use them)
step(); step()
check(#game.sends == 0 and gui.windows == 0, 'nothing is sent and no window is drawn while it is closed')
check(cmd('/gv2') == true and GV.open[1] == true, '/gv2 is handled (blocked) and opens the window')
-- (D9, 2026-11-20) since v0.1.50 /gambits is this addon's own command (the old engine is autobox, /autobox)
check(cmd('/gambits help') == true and cmd('/autobox') == false, '/gambits is this addon\'s command; /autobox (the old engine) is not touched')
check(cmd('/GV2 help') == true, 'the command is not case sensitive')
local ok1, t1 = run_until(function() return Ed._S.server and Ed._S.cat ~= nil and #Ed._S.sets > 0 end, 30)
check(ok1 and Ed._S.server.version == 12 and Ed._S.mates[1].name == 'Mira', string.format('opening asks the server: hello (version %s), Mira, sets, choices (%.1f s)',
      tostring(Ed._S.server and Ed._S.server.version), t1))
check(balanced(gui) and gui.title:find('Gambits v2', 1, true), 'the window draws balanced (colours, style, IDs, children, window)')
check(not visible_has('GSQ|') and not visible_has('command error') and not visible_has('^>>'), 'no GSQ answer, refusal or error line is visible')
check(not visible_has('!gsq'), 'the client\'s echo of our own lines is hidden')
for _, name in ipairs({ 'squad', 'crimson', 'classic' }) do
    cmd('/gv2 theme ' .. name)
    step()
    check(Ed.themeName == name and GV.settings.theme == name and balanced(gui), 'theme ' .. name .. ': whole window, balanced, saved')
end
cmd('/gv2 interval 0.2')
check(Tr.get_interval() == 0.6, 'the interval setting cannot go below 0.6 s (the smallest value the kit uses)')
cmd('/gv2 interval 1.0')
cmd('/gv2 scale 130'); step()
check(GV.settings.scale == 130 and balanced(gui), 'a larger window size draws balanced (font pushed and popped)')
cmd('/gv2 scale 100')

-- ---------------------------------------------------------------- 5. ping
section('ping: at 1.0 s, and a measurement below the game\'s limit')
game.visible = {}
Ed.ping(10)
local okp, tp = run_until(idle, 60)
check(okp and #Ed._S.pings == 10 and Ed._S.message:find('refused by the game 0', 1, true), 'Ping at 1.0 s: 10/10 answered, nothing refused: ' .. tostring(Ed._S.message))
io.write(string.format('   10 pings at 1.0 s: %.1f s\n', tp))
Ed.ping(10, 0.3)
local okq = run_until(idle, 90)
local refusedN = tonumber(Ed._S.message:match('refused by the game (%d+)'))
check(okq and #Ed._S.pings == 10 and refusedN and refusedN > 0, 'Ping at 0.3 s: all answered, the game refused some lines (' .. tostring(refusedN) .. ')')
check(Tr.get_interval() == 1.0, 'after the measurement the 1.0 s interval is back')
check(not visible_has('command error') and not visible_has('^>>') and not visible_has('GSQ|'), 'the refusals are not visible in the chat log')

-- ---------------------------------------------------------------- 6. saving, with the real server
section('Save: 5, 15 and 32 rules (the longest valid kind), confirmed by the server; lost answers; never twice')
local cat = Ed._S.cat
local longJa = 'DIVINE_SEAL'
for _, ja in ipairs(cat.jas) do if #ja.name > #longJa then longJa = ja.name end end
local function longRule()
    return { on = true, target = 'MASTER', cond = 'NOT_STATUS', arg = 'TRUST_AURA_MAGIC_ATTACK', cond2 = 'NOT_STATUS',
             arg2 = 'GEO_MAGIC_EVASION_BOOST', kind = 'ja', name = longJa, retry = '3600' }
end
local function typical(i)
    local list = {
        { on = true, target = 'PARTY', cond = 'HPP_LT', arg = '50', kind = 'family', name = 'CURE' },
        { on = true, target = 'SELF', cond = 'MPP_GTE', arg = '30', cond2 = 'NOT_STATUS', arg2 = 'PROTECT', kind = 'family', name = 'PROTECT', retry = '30' },
        { on = true, target = 'MASTER', cond = 'HPP_LT', arg = '40', cond2 = 'MPP_GTE', arg2 = '10', kind = 'family', name = 'CURAGA', retry = '30' },
        { on = true, target = 'SELF', cond = 'HPP_LT', arg = '25', kind = 'ja', name = 'DIVINE_SEAL' } }
    return list[(i - 1) % #list + 1]
end
local function draft(name, n, maker)
    local d = { num = 0, job = 'WHM', name = name, flags = 'o', dirty = true, rules = {} }
    for i = 1, n do d.rules[i] = maker(i) end
    return d
end
local function data() return St.readRaw(P) end
local function count_named(name)
    local c = 0
    for _, s in ipairs(data().sets) do if s.name == name then c = c + 1 end end
    return c
end
for _, case in ipairs({ { 5, typical, 'typical' }, { 15, typical, 'typical' }, { 32, typical, 'typical' }, { 5, longRule, 'longest' },
                        { 15, longRule, 'longest' }, { 32, longRule, 'longest' } }) do
    local n, maker, kind = case[1], case[2], case[3]
    local name = string.format('Size %d %s', n, kind)
    Ed._S.draft = draft(name, n, maker)
    local before = #game.sends
    local writes = game.writes
    Ed.save()
    local ok, took = run_until(idle, 180)
    local lines = #game.sends - before
    io.write(string.format('   %2d %-8s rules: %2d chat lines (incl. the list refresh), %.1f s at 1.0 s and 0.2 s latency\n', n, kind, lines, took))
    check(ok and Ed._S.message:find('server confirmed', 1, true) and count_named(name) == 1 and game.writes == writes + 1
          and not Ed._S.draft.dirty, string.format('%2d %s rules: saved once, server confirmed (%d lines, %.1f s)', n, kind, lines, took))
end
check(not visible_has('command error') and not visible_has('GSQ|'), 'no refusals or answers visible during the saves')

-- the answer to the last part is lost: the same token is sent again and the stored answer comes back
Ed._S.draft = draft('Lost answer', 15, typical)
game.dropOnce = true
local lostToken
game.policy = function(line)
    local tok, seq, tot = line:match('^/say !gsq x (%d+) (%d+) (%d+) ')
    if tok and seq == tot and game.dropOnce then game.dropOnce = false; lostToken = tok; game.dropTo = tok end
    return 'auto'
end
local writes0 = game.writes
Ed.save()
run_until(function() return game.dropTo ~= nil end, 60)
step(0.5); game.dropTo = nil -- (only that one answer was lost)
local okL = run_until(idle, 60)
check(okL and Ed._S.message:find('server confirmed', 1, true) and count_named('Lost answer') == 1 and game.writes == writes0 + 1,
      'a lost answer to the last part: resent with the same token, the stored answer comes back, written once')
game.policy = nil

-- every answer after the write is lost (and the server forgot its stored answer): the editor reads the list back
Ed._S.draft = draft('Read back', 5, typical)
local wr = game.writes
game.policy = function(line)
    local tok, seq, tot = line:match('^/say !gsq x (%d+) (%d+) (%d+) ')
    if tok and seq == tot then game.dropTo = tok; Gs._results[1] = nil end
    return 'auto'
end
local realHandle = Gs.handle
Gs.handle = function(p, line) realHandle(p, line); if game.dropTo then Gs._results[1] = nil end end
Ed.save()
local okR = run_until(idle, 90)
game.policy, game.dropTo, Gs.handle = nil, nil, realHandle
check(okR and Ed._S.message:find('confirmed by reading it back', 1, true) and count_named('Read back') == 1,
      'no answer at all and no stored answer: the list is read back and the save confirmed - never written twice (' .. tostring(Ed._S.message) .. ')')
check(game.writes - wr >= 1 and count_named('Read back') == 1, 'the resent last part could not create a second set (the server lost the parts: only acknowledged)')

-- the server lost the unfinished save (a restart between parts): nothing written, the editor says so after checking
Ed._S.draft = draft('Server restart', 15, typical)
game.policy = function(line)
    local tok, seq = line:match('^/say !gsq x (%d+) (%d+) ')
    if seq == '2' then Gs._drafts[1] = nil end
    return 'auto'
end
local wr2 = game.writes
Ed.save()
local okS = run_until(idle, 90)
game.policy = nil
check(okS and Ed._S.message:find('Not saved (checked on the server', 1, true) and count_named('Server restart') == 0 and game.writes == wr2,
      'a save the server lost halfway: checked on the server, reported as not saved, nothing written')
check(Ed._S.draft and #Ed._S.draft.rules == 15 and Ed._S.draft.dirty and io.open(cfgDir .. sep .. 'squad_draft.lua') ~= nil,
      'the rows are kept, in the window and in the draft file')

-- an edit (one part) whose answer was lost after the write, and the server forgot its stored answer: the resend is
-- refused as "stale" (the revision moved on) -> the editor reads the set back -> it has these rows -> saved
Ed._S.draft = draft('Tiny', 1, typical)
Ed.save(); run_until(idle, 20)
local mine
for _, s in ipairs(data().sets) do if s.name == 'Tiny' then mine = s end end
Ed.open_set(mine.num, false); run_until(idle, 20)
check(Ed._S.draft and Ed._S.draft.num == mine.num and #Ed._S.draft.rules == 1 and not Ed._S.draft.readonly,
      'Open loads your own set into the editor (header and rules counted right)')
Ed._S.draft.rules[1].arg = '61'; Ed._S.draft.dirty = true
game.policy = function(line)
    if line:match('^/say !gsq x ') then game.dropTo = line:match('^/say !gsq x (%d+)') end
    return 'auto'
end
Gs.handle = function(p, line) realHandle(p, line); Gs._results[1] = nil end
Ed.save()
step(1.5); game.dropTo = nil
local okE = run_until(idle, 60)
game.policy, Gs.handle = nil, realHandle
local edited
for _, s in ipairs(data().sets) do if s.num == mine.num then edited = s end end
check(okE and edited.rules[1].cond[2] == 61 and Ed._S.message:find('Saved as Rule Set ' .. mine.num, 1, true),
      'an edit refused as stale after a lost answer is checked: the server has these rows, so it is reported saved (' .. tostring(Ed._S.message) .. ')')

-- zoning in the middle of a save
Ed._S.draft = draft('Zoned', 32, longRule)
local wz = game.writes
Ed.save()
run_until(function() return #game.sends > 0 and Ed._S.progress and Ed._S.progress:find('Saving%.%.%. 5/') end, 60)
events.packet_in.gv2_packet_in({ id = 0x00B })
local sendsAtZone = #game.sends
for i = 1, 60 do step(0.05) end
check(#game.sends == sendsAtZone, 'zoning out: nothing is sent while zoning')
events.packet_in.gv2_packet_in({ id = 0x00A })
local okZ = run_until(idle, 120)
check(okZ and count_named('Zoned') == 1 and game.writes == wz + 1 and Ed._S.message:find('server confirmed', 1, true),
      'after zoning in the save continues and is written once')

-- ---------------------------------------------------------------- 7. delete
section('Delete: server confirmed, and confirmed by reading back after a lost answer')
Ed.load_sets('WHM'); run_until(idle, 20)
local victim
for _, s in ipairs(Ed._S.sets) do if s.name == 'Zoned' then victim = s end end
game.policy = function(line) if line:match('^/say !gsq del ') then game.dropTo = line:match('^/say !gsq del (%d+)') end return 'auto' end
Gs.handle = function(p, line) realHandle(p, line); Gs._results[1] = nil end
Ed.delete_set(victim.num, victim.rev)
local okD = run_until(idle, 60)
game.policy, game.dropTo, Gs.handle = nil, nil, realHandle
check(okD and count_named('Zoned') == 0 and Ed._S.message:find('deleted (server confirmed)', 1, true), 'a delete without an answer: the list is read back, the set is gone: confirmed')

-- ---------------------------------------------------------------- 8. assign and apply
section('Assign and Apply: confirmed by reading the server back; Apply never sent twice')
local function chosen() return R.selectedNum(player, 11, 3) end
game.party = { trust(11) }
Ed.assign(1, 1)
local okA = run_until(idle, 30)
-- (beta polish) the message names the Rule Set (its saved name, or "Rule Set #1" when the list has not loaded it)
check(okA and chosen() == 1 and Ed._S.message:find('Mira now uses ', 1, true) and Ed._S.message:find('(server confirmed)', 1, true)
      and Ed._S.message:find(Ed.set_label(1), 1, true), 'Assign set 1: confirmed by reading Mira\'s choice back - ' .. tostring(Ed._S.message))
local first = true
game.policy = function(line) if line:match('!squad ruleset') and first then first = false; return 'reject' end return 'auto' end
Ed.assign(1, 2)
okA = run_until(idle, 30)
game.policy = nil
check(okA and chosen() == 2 and Ed._S.message:find('server confirmed', 1, true), 'Assign refused once by the game: sent again, then confirmed')
first = true
game.policy = function(line) if line:match('!squad ruleset') and first then first = false; return 'lost' end return 'auto' end
Ed.assign(1, nil)
okA = run_until(idle, 30)
game.policy = nil
check(okA and chosen() == 0 and Ed._S.message:find('job rules (server confirmed)', 1, true), 'Assign lost once (no echo): sent again (harmless), then confirmed')
game.ignoreSquad = true
Ed.assign(1, 1)
okA = run_until(idle, 40)
game.ignoreSquad = false
check(okA and chosen() == 0 and Ed._S.messageOk == false and Ed._S.message:find('Not assigned', 1, true), 'Assign the server did not take: after two rounds "Not assigned", never "assigned"')

local function reapplies() local c = 0 for _, s in ipairs(game.sends) do if s.line == '/say !squad reapply' then c = c + 1 end end return c end
game.party = {}
local r0 = reapplies()
Ed.apply()
run_until(idle, 20)
check(reapplies() == r0 and Ed._S.message:find('No squad mate is out', 1, true), 'Apply with nobody out: nothing sent, the player is told')
game.party = { trust(11) }
r0 = reapplies()
local s0 = game.squadSays
Ed.apply()
local okP, tP = run_until(idle, 40)
check(okP and Ed._S.message:find('Applied: Mira called again', 1, true) and game.squadSays == s0 + 1 and reapplies() == r0 + 1,
      string.format('Apply: sent once, Mira left and came back: confirmed (%.1f s)', tP))
first = true
game.policy = function(line) if line == '/say !squad reapply' and first then first = false; return 'reject' end return 'auto' end
s0 = game.squadSays
Ed.apply()
okP = run_until(idle, 40)
game.policy = nil
check(okP and game.squadSays == s0 + 1 and Ed._S.message:find('Applied', 1, true), 'Apply refused once by the game: sent again, runs once on the server')
game.policy = function(line) if line == '/say !squad reapply' then return 'silent' end return 'auto' end
s0, r0 = game.squadSays, reapplies()
Ed.apply()
okP = run_until(idle, 40)
game.policy = nil
check(okP and reapplies() == r0 + 1 and Ed._S.messageWarn and Ed._S.message:find('NOT confirmed', 1, true),
      'Apply without the client\'s echo: never sent again, shown as NOT confirmed (' .. tostring(Ed._S.message) .. ')')
game.party = { trust(11) }
game.noReturn = true
Ed.apply()
okP = run_until(idle, 60)
game.noReturn = false
check(okP and Ed._S.messageWarn and Ed._S.message:find('not back yet', 1, true), 'Apply where the mate does not come back: NOT confirmed, never "applied"')
game.party = { trust(11) }

-- ---------------------------------------------------------------- 9. UI after failures, other chat, blocked lines, unload
section('UI after failures, other addons\' chat and hidden lines, unload')
game.visible = {}
deliver('...A command error occurred.')
step()
check(visible_has('command error'), 'a command error that is not about our line stays visible in the chat log')
Ed._S.draft = draft('Busy test', 3, typical)
Ed.ping(3)
check(Ed.save() == false and Ed._S.messageWarn, 'Save while the editor is busy: refused with "wait", nothing queued twice')
run_until(idle, 30)
cmd('/say hello all')
local lastBefore = #game.sends
Ed.ping(1)
step(0.05)
check(#game.sends == lastBefore, 'right after the player\'s own /say the editor waits for the interval')
run_until(idle, 10)
-- a refusal echo another addon already hid is still classified (and stays hidden)
Ed._S.pings = {}
game.policy = function(line) if line:match('!gsq ping') then return 'reject' end return 'auto' end
Ed.ping(1)
run_until(function() return #game.pending > 0 end, 5)
for _, p in ipairs(game.pending) do p.blocked = true end
local rej0 = Tr.stats().rejected
step(0.05)
game.policy = nil
run_until(idle, 20)
check(Tr.stats().rejected == rej0 + 1 and #Ed._S.pings == 1, 'a refusal another addon already hid is still seen, and the ping still completes')
-- after the failed save the window still draws in every state
check(balanced(gui), 'the window is balanced after all the failures')
-- unload keeps unsaved rows
Ed._S.draft = draft('Unsaved at unload', 2, typical)
events.unload.gv2_unload()
local df = io.open(cfgDir .. sep .. 'squad_draft.lua', 'rb')
local dtext = df and df:read('*a') or ''
if df then df:close() end
check(dtext:find('Unsaved at unload', 1, true) and settingsSaved > 0, 'unload writes the unsaved rows to the draft file and saves the settings')
Ed._S.restorable = nil
Ed.load_draft()
check(Ed._S.restorable and Ed._S.restorable.name == 'Unsaved at unload' and #Ed._S.restorable.rules == 2, 'the next start offers them again (Restore unsaved draft)')
check(game.mode == 1, 'lines go through QueueCommand mode 1, like the other kit addons')

-- ---------------------------------------------------------------- 10. version 3: catalog transport, lossless rules, the WHM editor
section('catalog: 150-byte game cut, every job reconstructed exactly, damaged lists refused')
local function served_lines(req)
    game.served = {}
    Gs.handle(player, req)
    local out = {}
    for _, l in ipairs(game.served) do out[#out + 1] = l end
    return out
end
local function as_items(lines)
    local items, endF = {}, nil
    for _, l in ipairs(lines) do
        local fl = Tr.split(string.sub(l, 1, 150), '|')
        if fl[3] == 'end' then endF = fl else items[#items + 1] = fl end
    end
    return items, endF
end
local allOk, longestCat = true, 0
local jobNames = {}
for name in pairs(Gs.JOBS) do jobNames[#jobNames + 1] = name end
table.sort(jobNames)
for _, job in ipairs(jobNames) do
    for _, sub in ipairs({ '', 'WHM', 'NIN', 'BLU' }) do
        local lines = served_lines('cat 123 ' .. job .. (sub ~= '' and (' ' .. sub) or ''))
        for _, l in ipairs(lines) do longestCat = math.max(longestCat, #l) end
        local c, why = Ed.parse_catalog(as_items(lines))
        -- compare with the server's own lists (the uncut lines)
        local want = { t = 0, c = 0, f = 0, j = 0, s = 0 }
        for _, l in ipairs(lines) do
            local fl = Tr.split(l, '|')
            if fl[3] == 'cat' then want[fl[5]] = want[fl[5]] + #Ed.split(fl[6], ',') end
        end
        local condCount = 0
        for _ in pairs(c and c.conds or {}) do condCount = condCount + 1 end
        if not (c and #c.targets == want.t and condCount == want.c and #c.families == want.f and #c.jas == want.j and #c.spells == want.s) then
            allOk = false
            io.write('   ', job, ' ', sub, ': ', tostring(why), '\n')
        end
    end
end
check(allOk and longestCat <= 140, string.format('18 jobs x 4 sub job choices: every catalog survives the 150-byte cut and is rebuilt exactly (longest line %d)', longestCat))
local whm = served_lines('cat 124 WHM')
local good = Ed.parse_catalog(as_items(whm))
check(good and good.conds.HPP_LT and good.conds.HPP_LT.lo == 0 and good.conds.HPP_LT.hi == 100 and good.conds.STATUS
      and good.conds.READYING_WS and #good.spells > 50, 'WHM: HP below/at least, Status, Readying a weapon skill, and the spells are all there')
local function damaged(fn)
    local items, endF = as_items(whm)
    fn(items, endF)
    return Ed.parse_catalog(items, endF)
end
local cases = {
    { 'a missing line', function(items) table.remove(items, 3) end },
    { 'a line twice', function(items) items[#items + 1] = items[2] end },
    { 'lines of two kinds swapped', function(items) local a, b = items[1], items[#items]; a[4], b[4] = b[4], a[4] end },
    { 'an entry cut', function(items) items[2][6] = string.sub(items[2][6], 1, #items[2][6] - 3) end },
    { 'an entry changed (still well formed)', function(items)
        local changed = false
        for _, it in ipairs(items) do
            if not changed and it[6]:find('HPP_LT:r:0:100', 1, true) then it[6] = it[6]:gsub('HPP_LT:r:0:100', 'HPP_LT:r:0:99'); changed = true end
        end
        assert(changed)
    end },
    { 'an entry repeated', function(items) items[2][6] = items[2][6] .. ',' .. Ed.split(items[2][6], ',')[1] end },
    { 'wrong counts', function(_, endF) endF[5] = endF[5]:gsub('^%d+', '1') end },
    { 'no end line', function(_, endF) for k in pairs(endF) do endF[k] = nil end end },
}
for _, case in ipairs(cases) do
    local c, why = damaged(case[2])
    check(c == nil and why, 'refused: ' .. case[1] .. ' (' .. tostring(why) .. ')')
end
-- the old server's 200-byte lines, cut by the game: refused, nothing guessed
local cutOld = {}
for _, l in ipairs(whm) do cutOld[#cutOld + 1] = l end
cutOld[2] = cutOld[2] .. ',' .. string.rep('X', 60) -- (a line that would be longer than 150)
local cOld = Ed.parse_catalog(as_items(cutOld))
check(cOld == nil, 'a line cut at 150 bytes makes the whole list refused')
-- end to end: a lost catalog line keeps the old catalog and says so
local before = Ed._S.cat
game.policy = function() return 'auto' end
local realHandle2 = Gs.handle
Gs.handle = function(p, line)
    if line:match('^cat ') then
        game.served = {}
        local realPrint = p.printToPlayer
        local n = 0
        p.printToPlayer = function(self, l) n = n + 1; if n ~= 2 then realPrint(self, l) end end
        realHandle2(p, line)
        p.printToPlayer = realPrint
    else
        realHandle2(p, line)
    end
end
Ed.load_catalog('WHM')
run_until(idle, 20)
Gs.handle, game.policy = realHandle2, nil
check(Ed._S.cat == before and Ed._S.catError and Ed._S.messageOk == false, 'a catalog with a lost line is refused, the old choices stay: ' .. tostring(Ed._S.catError))
Ed.load_catalog('WHM'); run_until(idle, 20)
check(Ed._S.cat ~= before and Ed._S.catError == nil, 'Refresh loads it again')

section('lossless rules: Rule Set 1 (Cure II) round-trips; kept rows; exact values')
local function stored(num) for _, s in ipairs(data().sets) do if s.num == num then return s end end end
local function encs(rules) local out = {} for i, r in ipairs(rules) do out[i] = Ed.encode_rule(r) end return out end
Ed.load_sets('WHM'); run_until(idle, 20)
Ed.open_set(1, false); run_until(idle, 20)
local d1 = Ed._S.draft
check(d1 and d1.readonly and #d1.rules == 2 and d1.rules[1].arg == '40' and d1.rules[2].kind == 'spell' and d1.rules[2].name == 'CURE_II'
      and d1.rules[2].arg == '75' and not d1.uneditable, 'Open set 1 (hand-written): both rules, HP below 40 / 75, the specific spell Cure II; read-only')
check(Ed.rule_summary(d1.rules[2], Ed._S.cat) == 'Party member: HP below 75% -> Cure II', 'its summary: ' .. Ed.rule_summary(d1.rules[2], Ed._S.cat))
-- draw it many frames: nothing changes (no value is replaced by a default)
for _ = 1, 5 do step() end
check(d1.rules[1].arg == '40' and d1.rules[2].arg == '75', 'drawing the read-only set keeps HP below 40 and 75 exactly')
Ed.open_set(1, true); run_until(idle, 20)
local dc = Ed._S.draft
check(dc and not dc.readonly and #dc.rules == 2 and dc.rules[1].arg == '40' and dc.rules[2].name == 'CURE_II' and not dc.uneditable,
      'Copy: both rules, editable, values exact (problems 1 and 3 fixed)')
Ed._S.sel = 1
for _ = 1, 5 do step() end
check(dc.rules[1].arg == '40' and dc.rules[1].cond == 'HPP_LT', 'drawing the copied rule keeps its threshold (no "?%")')
dc.name = 'Copy of Cure basics'
Ed.save(); run_until(idle, 30)
local savedNum = tonumber(Ed._S.message:match('Saved as Rule Set (%d+)'))
local copySet = stored(savedNum or -1)
check(copySet and deq(copySet.rules, MANUAL.sets[1].rules), 'Copy -> Save: the stored rules equal Rule Set 1\'s exactly (Cure II included)')
Ed.open_set(savedNum, false); run_until(idle, 20)
check(deq(encs(Ed._S.draft.rules), encs(d1.rules)) and not Ed._S.draft.readonly, 'Open the copy again: the same rules, now your own (editable)')
-- the set with a { main, sub } argument: visible, kept, read-only; Copy refused; Save impossible
Ed.open_set(2, false); run_until(idle, 20)
local d2 = Ed._S.draft
check(d2 and d2.readonly and d2.uneditable and d2.rules[2].opaque and #d2.rules == 2, 'set 2: its uncarriable rule is a visible [kept] row, the set read-only')
check(Ed.rule_summary(d2.rules[2]):find('kept unchanged', 1, true), 'the kept row says so in the list')
local msgBefore = Ed._S.draft
Ed.open_set(2, true); run_until(idle, 20)
check(Ed._S.draft == msgBefore and Ed._S.messageOk == false and Ed._S.message:find('Not copied', 1, true), 'Copy of set 2 is refused (it would lose that rule)')
local sends0 = #game.sends
d2.readonly = false
check(Ed.check_draft(d2, Ed._S.cat):find('cannot show', 1, true), 'a draft with a kept row never passes the save check')
d2.readonly = true
check(#game.sends == sends0, 'nothing was sent for it')
check(deq(stored(2).rules, MANUAL.sets[2].rules), 'set 2 on the server is untouched')

-- exact values through the condition builder
local cat3 = Ed._S.cat
local r = Ed.new_rule()
Ed.set_condition(r, 1, 'HPP_LT', cat3); r.arg = '37'
Ed.set_condition(r, 1, 'HPP_GTE', cat3)
check(r.cond == 'HPP_GTE' and r.arg == '37', 'HP below 37 -> at least: the value stays 37 (only the comparison changes)')
Ed.set_condition(r, 1, 'MPP_LT', cat3)
check(r.arg == '50', 'another subject (MP) starts from its default, 50')
r.arg = '150'
local dv = { num = 0, job = 'WHM', name = 'Value test', rules = { r } }
check(Ed.check_draft(dv, cat3):find('0%-100'), 'MP below 150 is refused before sending (nothing is clamped)')
r.arg = '100'
check(Ed.check_draft(dv, cat3) == nil, 'MP below 100 is accepted (the exact upper bound)')
Ed.set_condition(r, 1, 'TP_GTE', cat3); r.arg = '2999'
Ed.set_condition(r, 2, 'HP_MISSING', cat3); r.arg2 = '1234'
Ed._S.draft = dv; Ed._S.sel = 1
for _ = 1, 5 do step() end
check(r.arg == '2999' and r.arg2 == '1234', 'TP 2999 and missing HP 1234 survive drawing')
Ed.save(); run_until(idle, 30)
local vNum = tonumber(Ed._S.message:match('Saved as Rule Set (%d+)'))
local vs = stored(vNum or -1)
check(vs and vs.rules[1].cond[1] == 'TP_GTE' and vs.rules[1].cond[2] == 2999 and vs.rules[1].cond2[1] == 'HP_MISSING' and vs.rules[1].cond2[2] == 1234,
      'saved and stored exactly: TP at least 2999, missing HP at least 1234')
Ed.open_set(vNum, false); run_until(idle, 20)
check(Ed._S.draft.rules[1].arg == '2999' and Ed._S.draft.rules[1].arg2 == '1234', 'and opened again exactly')
-- enemy conditions need the Enemy target
local re = Ed.new_rule()
Ed.set_condition(re, 1, 'CASTING_MA', cat3)
check(Ed.check_draft({ num = 0, job = 'WHM', name = 'Enemy test', rules = { re } }, cat3):find('needs the target Enemy'),
      '"Enemy is casting" with the target Party member is refused')
check(#Ed.subjects_for(1, 'PARTY', cat3) < #Ed.subjects_for(1, 'TARGET', cat3), 'the Enemy subject is offered only with the target Enemy')
re.target = 'TARGET'; Ed.set_action(re, 'ja', 'DIVINE_SEAL')
check(Ed.check_draft({ num = 0, job = 'WHM', name = 'Enemy test', rules = { re } }, cat3) == nil, 'with the target Enemy it is accepted')

section('a complete WHM Rule Set built with the editor\'s own edits, saved and stored exactly')
local function rule(target, c1, a1, c2, a2, kind, name, retry)
    local x = Ed.new_rule()
    x.target = target
    Ed.set_condition(x, 1, c1, cat3); x.arg = a1
    if c2 then Ed.set_condition(x, 2, c2, cat3); x.arg2 = a2 end
    Ed.set_action(x, kind, name)
    x.retry = retry
    return x
end
local function has_spell(name) for _, s in ipairs(cat3.spells) do if s.name == name then return true end end return false end
check(has_spell('CURE_II') and has_spell('POISONA') and has_spell('PARALYNA') and has_spell('BLINDNA') and has_spell('SILENA')
      and has_spell('PROTECT') and has_spell('SHELL'), 'the WHM spell list has Cure II, Protect, Shell and the -na spells')
local whmRules = {
    rule('SELF', 'HAS_TOP_ENMITY', nil, 'HPP_LT', '50', 'ja', 'DIVINE_SEAL'),
    rule('PARTY', 'HPP_LT', '30', 'MPP_GTE', '10', 'family', 'CURAGA', '20'),
    rule('PARTY', 'HPP_LT', '50', nil, nil, 'family', 'CURE'),
    rule('TANK', 'HPP_LT', '70', nil, nil, 'spell', 'CURE_II'),
    rule('PARTY', 'STATUS', 'PARALYSIS', nil, nil, 'spell', 'PARALYNA'),
    rule('PARTY', 'STATUS', 'SILENCE', nil, nil, 'spell', 'SILENA'),
    rule('PARTY', 'STATUS', 'POISON', nil, nil, 'spell', 'POISONA'),
    rule('PARTY', 'STATUS', 'BLINDNESS', nil, nil, 'spell', 'BLINDNA'),
    rule('PARTY', 'NOT_STATUS', 'PROTECT', nil, nil, 'family', 'PROTECT', '60'),
    rule('PARTY', 'NOT_STATUS', 'SHELL', nil, nil, 'family', 'SHELL', '60'),
    rule('SELF', 'MPP_LT', '25', 'NOT_STATUS', 'REFRESH', 'family', 'CURE'),
}
local whmDraft = { num = 0, job = 'WHM', name = 'Mira WHM', flags = 'o', dirty = true, rules = whmRules }
check(Ed.check_draft(whmDraft, cat3) == nil, 'the WHM set passes the editor\'s checks: ' .. tostring(Ed.check_draft(whmDraft, cat3)))
Ed._S.draft, Ed._S.sel = whmDraft, 2
for _ = 1, 3 do step() end
check(balanced(gui), 'the editor draws the WHM set balanced')
local wantEnc = encs(whmRules)
Ed.save(); run_until(idle, 40)
local wNum = tonumber(Ed._S.message:match('Saved as Rule Set (%d+)'))
Ed.open_set(wNum or -1, false); run_until(idle, 20)
check(wNum and deq(encs(Ed._S.draft.rules), wantEnc), 'saved as Rule Set ' .. tostring(wNum) .. ' and opened again: all 11 rules exactly')
local ws = stored(wNum or -1)
check(ws and ws.rules[1].action[2] == 'DIVINE_SEAL' and ws.rules[4].action[1] == 'spell' and ws.rules[4].target == 'TANK'
      and ws.rules[5].cond[2] == 'PARALYSIS' and ws.rules[2].cond2[2] == 10 and ws.rules[9].retry == 60,
      'stored with the server\'s own forms (job ability, specific spell, Tank, status, two conditions, wait)')

section('32 complex rules through the editor (boundary)')
local bigRules = {}
for i = 1, 32 do
    bigRules[i] = rule('TOP_ENMITY', 'NOT_STATUS', 'TRUST_AURA_MAGIC_ATTACK', 'NOT_STATUS', 'GEO_MAGIC_EVASION_BOOST', 'spell', 'CURE_II', '3600')
    bigRules[i].level = '75'
end
local bigD = { num = 0, job = 'WHM', name = 'Thirty two complex', flags = 'o', dirty = true, rules = bigRules }
Ed._S.draft = bigD
local s0b = #game.sends
Ed.save()
local okB, tB = run_until(idle, 120)
local bNum = tonumber((Ed._S.message or ''):match('Saved as Rule Set (%d+)'))
check(okB and bNum and #stored(bNum).rules == 32, string.format('32 complex rules saved through the editor (%d lines, %.0f s)', #game.sends - s0b, tB))
Ed.open_set(bNum or -1, false); run_until(idle, 30)
check(#Ed._S.draft.rules == 32 and Ed._S.draft.rules[32].level == '75' and Ed._S.draft.rules[32].arg2 == 'GEO_MAGIC_EVASION_BOOST',
      'and opened again whole (every get line under 150 bytes, rules in segments)')
local tooMany = { num = 0, job = 'WHM', name = 'Too many', rules = {} }
for i = 1, 33 do tooMany.rules[i] = bigRules[1] end
check(Ed.check_draft(tooMany, cat3):find('at most 32'), '33 rules are refused (the limit is a number of rules)')
-- ---------------------------------------------------------------- 11. UI polish: spells, Check, window, scale, layout
section('Specific Spell choices: no Trust spells, the mate\'s levels, one alphabetical list, saved spells kept')
Ed.load_catalog('WHM'); run_until(idle, 20)
local whmCat = Ed._S.cat
local mira = { slot = 1, name = 'Mira', job = 'WHM', level = 25, sub = nil, out = true }
check(Ed.TRUSTS and Ed.TRUSTS.SHANTOTTO and Ed.TRUSTS.KUPIPI, 'the generated Trust list is loaded (' .. tostring(Ed.TRUSTS and Ed.TRUSTS.SHANTOTTO) .. ')')
local rawTrusts = 0
for _, sp in ipairs(whmCat.spells) do if Ed.TRUSTS[sp.name] then rawTrusts = rawTrusts + 1 end end
local choices = Ed.spell_choices(whmCat, mira)
local names, labels, seenN, dup, trustIn, overLevel = {}, {}, {}, false, false, false
for i, e in ipairs(choices) do
    names[e.name] = i
    labels[i] = Ed.pretty(e.name)
    if seenN[e.name] then dup = true end
    seenN[e.name] = true
    if Ed.TRUSTS[e.name] then trustIn = true end
    if e.level > 25 then overLevel = true end
end
check(rawTrusts > 100 and not trustIn, string.format('the server\'s WHM list has %d Trust spells; none of them is offered', rawTrusts))
check(not overLevel and names.CURE_II and names.CURE_III and not names.CURE_IV, 'only spells up to Mira\'s level 25 (Cure III yes, Cure IV no)')
check(names.CURE and names.CURE_II == names.CURE + 1 and names.CURE_III == names.CURE + 2, 'Cure, Cure II and Cure III are next to each other')
local sorted = true
for i = 2, #labels do sorted = sorted and labels[i - 1] <= labels[i] end
check(sorted and not dup, 'one alphabetical list (' .. #choices .. ' spells), no duplicates')
check(choices[names.CURE_II].label == 'Cure II' and choices[names.CURE_II].level == 11, 'clean names (Cure II), the level kept for the tooltip: ' .. choices[names.CURE_II].label)
local subCat = { spells = { { name = 'CURE', level = 1 }, { name = 'CURE', level = 1, sub = true }, { name = 'UTSUSEMI_ICHI', level = 12, sub = true },
                            { name = 'UTSUSEMI_NI', level = 37, sub = true }, { name = 'SHANTOTTO', level = 1 } } }
local sc = Ed.spell_choices(subCat, mira)
local subNames = {}
for _, e in ipairs(sc) do subNames[e.name] = e end
check(#sc == 2 and subNames.CURE and not subNames.CURE.sub and subNames.UTSUSEMI_ICHI and subNames.UTSUSEMI_ICHI.sub
      and subNames.UTSUSEMI_ICHI.label == 'Utsusemi Ichi' and not subNames.UTSUSEMI_NI,
      'sub-job spells: marked as sub job, kept up to the main level (the sub level is not known to the editor), a spell of both jobs listed once as main')
check(#Ed.spell_choices(whmCat, nil) > #choices, 'without a mate (no level known) the whole job list is offered')
-- a saved spell above the level: kept unchanged, explained
local keepRule = { on = true, target = 'PARTY', cond = 'HPP_LT', arg = '40', kind = 'spell', name = 'CURE_IV' }
local note = Ed.spell_note(keepRule, whmCat, mira)
-- (0.3.1) with the job's own list (an older server's catalog) the note says when it starts working
check(note and note:find('Mira learns Cure IV at level 41', 1, true) and note:find('kept as saved', 1, true), 'a saved Cure IV (above level 25): ' .. tostring(note))
check(Ed.spell_note({ kind = 'spell', name = 'CURE_II' }, whmCat, mira) == nil, 'no note for a spell Mira has')
check(Ed.spell_note({ kind = 'spell', name = 'SHANTOTTO' }, whmCat, mira):find('Trust spell', 1, true), 'a saved Trust spell is explained, not removed')
Ed._S.mates = { { slot = 1, id = 11, name = 'Mira', job = 'WHM', level = 25, chosen = 0, out = true } }
Ed._S.mateSlot = 1
Ed._S.draft = { num = 0, job = 'WHM', name = 'Keep test', flags = 'o', rules = { keepRule } }
Ed._S.sel = 1
for _ = 1, 3 do step() end
check(keepRule.name == 'CURE_IV' and keepRule.kind == 'spell' and Ed.encode_rule(keepRule) == '1,PARTY,HPP_LT,40,,,s,CURE_IV,',
      'drawing the editor keeps the saved Cure IV exactly')

section('Check: a mate that is not out is explained, not reported as a bad Rule Set')
game.party = {}
Ed.load_mates(); run_until(idle, 20)
Ed.check_set(1, 1); run_until(idle, 20)
check(Ed._S.messageWarn and Ed._S.message:find('Summon Mira before checking this Rule Set.', 1, true) and Ed._S.message:find('not a problem in the set', 1, true),
      'not out: ' .. tostring(Ed._S.message))
check(next(Ed._S.checks) == nil, 'no rule is marked as left out')

section('window: resizable, minimum size, saved size and UI scale, layout at any size')
rawset(_G, 'ImGuiWindowFlags_NoResize', 2); rawset(_G, 'ImGuiWindowFlags_NoCollapse', 32); rawset(_G, 'ImGuiCond_Always', 1)
local rec = { sizes = {}, flags = nil, constraints = nil, newlines = 0, wrapped = {}, tips = {} }
local realBegin = gui.Begin
gui.Begin = function(title, open, flags) rec.flags = flags; return realBegin(title, open, flags) end
gui.SetNextWindowSize = function(sz) rec.sizes[#rec.sizes + 1] = { sz[1], sz[2] } end
gui.SetNextWindowSizeConstraints = function(lo) rec.constraints = { lo[1], lo[2] } end
gui.NewLine = function() rec.newlines = rec.newlines + 1 end
gui.SetCursorPosX = function() end
gui.AlignTextToFramePadding = function() end
rec.wrapped, rec.tips = gui.wrapped, gui.tips -- (the stand-in records wrapped lines and tooltips the way they are drawn)
local winW, winH = 1080, 600
gui.GetWindowSize = function() return winW, winH end
local availW, availH = 1000, 560
gui.GetContentRegionAvail = function() return { availW, availH } end
GV.sizeApplied = false
step()
check(rec.flags == 32, 'the window can be resized (no NoResize flag), only NoCollapse')
check(rec.constraints and rec.constraints[1] == 720 and rec.constraints[2] == 420, 'a minimum size of 720 x 420 at 100 %')
check(#rec.sizes == 1 and rec.sizes[1][1] == 1080 and rec.sizes[1][2] == 600, 'first opening: 1080 x 600')
step()
check(#rec.sizes == 1, 'the size is set once, then left to the player')
winW, winH = 900, 520
local saves0 = settingsSaved
step(0.2); step(0.5)
check(GV.settings.win_w ~= 900, 'a size that is still changing is not saved yet')
step(1.1)
check(GV.settings.win_w == 900 and GV.settings.win_h == 520 and settingsSaved > saves0, 'the new size is saved once it settled (900 x 520)')
GV.sizeApplied = false; rec.sizes = {}
step()
check(rec.sizes[1] and rec.sizes[1][1] == 900 and rec.sizes[1][2] == 520, 'reopened (after a reload): the saved 900 x 520')
-- UI scale from the window
gui.clicks['+##gsq-scale-up'] = true
step()
check(GV.settings.scale == 110, 'Size + : 110 %')
gui.clicks['110%##gsq-scale-reset'] = true
step()
check(GV.settings.scale == 100, 'Size 100 % button resets')
for _ = 1, 15 do gui.clicks['+##gsq-scale-up'] = true; step() end
check(GV.settings.scale == 200, 'the scale stops at 200 %')
step()
check(rec.constraints[1] == 1440 and rec.constraints[2] == 840, 'the minimum size grows with the scale (1440 x 840 at 200 %)')
for _ = 1, 15 do gui.clicks['-##gsq-scale-down'] = true; step() end
check(GV.settings.scale == 70, 'and stops at 70 %')
gui.clicks['70%##gsq-scale-reset'] = true; step()
-- narrow and wide layouts: everything still draws, controls wrap instead of overflowing
Ed._S.draft = { num = 0, job = 'WHM', name = 'A rather long set name x', flags = 'o', rules = { rule('PARTY', 'HPP_LT', '40', 'MPP_GTE', '10', 'spell', 'CURE_II', '30') } }
Ed._S.sel = 1
local selRule = Ed._S.draft.rules[1]
for _, size in ipairs({ { 300, 200 }, { 700, 400 }, { 1600, 900 } }) do
    availW, availH = size[1], size[2]
    rec.newlines = 0
    step()
    check(balanced(gui), string.format('layout %d x %d draws balanced (%d controls moved to a new line)', size[1], size[2], rec.newlines))
end
check(selRule.arg == '40' and selRule.arg2 == '10' and selRule.name == 'CURE_II', 'resizing keeps the rule\'s values exactly')
availW, availH = 120, 200; rec.newlines = 0; step() -- (the stand-in's width does not shrink after SameLine: a narrow panel)
local narrowNL = rec.newlines
availW, availH = 1600, 900; rec.newlines = 0; step()
check(narrowNL > rec.newlines, string.format('a narrow window moves controls to new lines (%d), a wide one does not need to (%d)', narrowNL, rec.newlines))
-- long status lines are wrapped, never cut
local longMsg = 'Ping: 10/10 answered; round trip min 203, avg 423, max 750 ms; per request avg 1200 ms (with resends); refused by the game 0, sent again 0; interval 1.00 s'
Ed.say(longMsg)
gui.wrapped = {}
step()
local foundMsg = false
for _, w in ipairs(gui.wrapped) do if w == longMsg then foundMsg = true end end
check(foundMsg, 'a long Ping line is drawn wrapped and whole')
-- tooltips show the full set name and the full rule line
Ed._S.sets = { { num = 7, job = 'WHM', rules = 3, flags = 'o', rev = '1', id = 'u', name = 'An extremely long name xx' } }
Ed._S.selectedSet = 7
gui.IsItemHovered = function() return true end
gui.tips = {}
step()
gui.IsItemHovered = function() return false end
local tipName, tipRule = false, false
for _, tp in ipairs(gui.tips) do
    if tp:find('An extremely long name xx', 1, true) then tipName = true end
    if tp:find('Party member: HP below 40% and MP at least 10% -> Cure II (then waits 30 s)', 1, true) then tipRule = true end
end
check(tipName and tipRule, 'tooltips carry the whole set name and the whole rule line')
check(balanced(gui), 'balanced after all of it')
gui.GetContentRegionAvail = function() return { 1000, 500 } end

-- ---------------------------------------------------------------- 11b. hotfix 2026-11-21: no text is ever read as a format
section('hotfix: tooltips and wrapped lines are drawn unformatted (Ashita formats SetTooltip / TextWrapped); themes; Party tank')
do -- (a block: the file's main chunk is close to Lua's limit of 200 local variables)
local SIZE_TIPS = { 'Smaller text and controls (70-200 %).', 'Back to 100 %.', 'Larger text and controls (70-200 %).' }
local LOWEST_TIP = Ed.TARGET_HELP.PARTY_LOWEST_HPP
-- the stand-in's format model rejects exactly what the old code handed to SetTooltip / TextWrapped
local oldWay = { LOWEST_TIP, 'Party member: HP below 40% and MP at least 10% -> Cure II', SIZE_TIPS[1], SIZE_TIPS[2] }
local rejected = 0
for _, t in ipairs(oldWay) do if format_problem(t) then rejected = rejected + 1 end end
check(rejected == #oldWay and format_problem('50%% escaped') == nil and format_problem('no percent') == nil,
      'the format model: every bare % is unsafe (the Lowest HP help is even invalid for the C runtime), %% is fine')
local function hover_all(views)
    gui.errors, gui.tips, gui.wrapped, gui.formats = {}, {}, {}, 0
    gui.IsItemHovered = function() return true end
    -- (0.3.1) 'ws' = the Weapon Skills section open (it was a second tab)
    for _, v in ipairs(views) do Ed._S.wsOpen = v == 'ws'; step() end
    gui.IsItemHovered = function() return false end
    Ed._S.wsOpen = false
end
local function has_tip(text) for _, t in ipairs(gui.tips) do if t == text then return true end end return false end
local function any_tip(part) for _, t in ipairs(gui.tips) do if t:find(part, 1, true) then return true end end return false end
-- a draft with the risky texts: a Lowest HP rule (its target help), % conditions, a template-sized set
Ed._S.draft = { num = 0, job = 'WHM', name = 'Percent test', flags = 'o', rules = {
    rule('PARTY_LOWEST_HPP', 'HPP_LT', '50', nil, nil, 'family', 'CURE'),
    rule('PARTY', 'HPP_LT', '40', 'MPP_GTE', '10', 'spell', 'CURE_II', '30') } }
Ed._S.sel = 1
hover_all({ 'rules', 'ws' })
local sizeOk = has_tip(SIZE_TIPS[1]) and has_tip(SIZE_TIPS[2]) and has_tip(SIZE_TIPS[3])
check(sizeOk, 'the Size tooltips next to the Theme selector show their text exactly ("(70-200 %).", "Back to 100 %.")')
check(has_tip(LOWEST_TIP), 'the Lowest HP target help shows exactly: ' .. LOWEST_TIP)
check(any_tip('HP below 50% -> Best of Cure') and any_tip('HP below 40% and MP at least 10% -> Cure II (then waits 30 s)'),
      'rule lines with % show exactly in their tooltips')
check(gui.formats == 0, 'no text went to a formatting call at all (SetTooltip / TextWrapped / BulletText / LabelText): ' .. gui.formats)
check(balanced(gui), 'hovering everything (Rule Sets and Weapon Skills): balanced, no format problem: ' .. table.concat(gui.errors, ' | '))
-- other sequences a format would misread, through a status line (wrapped) and the selected rule's line
local tricky = 'odd: %s %d %n %x % th 100% %% %'
Ed.say(tricky)
gui.wrapped, gui.errors = {}, {}
step()
local trickyShown = false
for _, w in ipairs(gui.wrapped) do if w == tricky then trickyShown = true end end
check(trickyShown and #gui.errors == 0 and gui.formats == 0, 'a status line with %s %d %n %x "% th" "100%" "%%" "%" is shown exactly, unformatted')
local wrappedRule = false
for _, w in ipairs(gui.wrapped) do if w:find('HP below 50% -> Best of Cure', 1, true) then wrappedRule = true end end
check(wrappedRule, 'the selected rule\'s wording (with %) is drawn wrapped and exactly')
-- templates: their "about" texts (with %) as tooltips
Ed._S.draft, Ed._S.sel = nil, nil
hover_all({ 'rules' })
local aboutOk = true
for _, job in ipairs({ 'PLD', 'WHM' }) do
    local about = Ed.TEMPLATES[job][1].about
    if Ed.mate() and Ed.mate().job == job then aboutOk = aboutOk and any_tip(about) end
end
check(aboutOk and balanced(gui) and gui.formats == 0, 'the starter template tooltips (texts with "below 50 %") are unformatted too')
-- a binding without TextUnformatted / BeginTooltip / PushTextWrapPos (not Ashita v4): the old calls, with % escaped
local keepTU, keepBT, keepET, keepPW, keepPP = gui.TextUnformatted, gui.BeginTooltip, gui.EndTooltip, gui.PushTextWrapPos, gui.PopTextWrapPos
gui.TextUnformatted, gui.BeginTooltip, gui.EndTooltip, gui.PushTextWrapPos, gui.PopTextWrapPos = nil, nil, nil, nil, nil
Ed._S.draft = { num = 0, job = 'WHM', name = 'Percent test', flags = 'o', rules = { rule('PARTY_LOWEST_HPP', 'HPP_LT', '50', nil, nil, 'family', 'CURE') } }
Ed._S.sel = 1
hover_all({ 'rules' })
check(gui.formats > 0 and #gui.errors == 0 and has_tip(SIZE_TIPS[2]) and has_tip(LOWEST_TIP),
      'fallback: SetTooltip / TextWrapped get %% (the player still sees one %), never a bare %')
gui.TextUnformatted, gui.BeginTooltip, gui.EndTooltip, gui.PushTextWrapPos, gui.PopTextWrapPos = keepTU, keepBT, keepET, keepPW, keepPP
-- the three themes, switched with the header's selector in the middle of a frame (hovering everything at the same time)
local realBC, realSel = gui.BeginCombo, gui.Selectable
local maxVars, maxColors = 0, 0
local realPV, realPC = gui.PushStyleVar, gui.PushStyleColor
gui.PushStyleVar = function(...) realPV(...); maxVars = math.max(maxVars, gui.vars) end
gui.PushStyleColor = function(...) realPC(...); maxColors = math.max(maxColors, gui.colors) end
local pick
gui.BeginCombo = function(id) return id == '##gsq-theme' end
gui.Selectable = function(label) return label == pick end
local varsBy = {}
for i, name in ipairs({ 'squad', 'crimson', 'classic', 'crimson', 'squad', 'classic' }) do
    local saves = settingsSaved
    pick = Ed.THEME_NAMES[name] .. '##' .. ({ classic = 1, squad = 2, crimson = 3 })[name]
    gui.errors, gui.formats = {}, 0
    gui.IsItemHovered = function() return true end
    step()                       -- (the frame that switches: pushed with the old theme, popped by its token)
    pick = nil
    maxVars = 0
    step()                       -- (the next frame: pushed with the new theme)
    gui.IsItemHovered = function() return false end
    varsBy[name] = maxVars
    check(Ed.themeName == name and GV.settings.theme == name and settingsSaved > saves and balanced(gui) and gui.formats == 0,
          string.format('switch %d to %s from the selector (mid-frame, hovering): saved, colours %d and style vars %d back to 0',
                        i, name, gui.colors, gui.vars))
end
gui.BeginCombo, gui.Selectable, gui.PushStyleVar, gui.PushStyleColor = realBC, realSel, realPV, realPC
check(varsBy.squad > varsBy.classic and varsBy.crimson == varsBy.squad,
      string.format('Squad/Crimson push their rounding and border (%d style vars) on top of Classic\'s (%d): all popped', varsBy.squad, varsBy.classic))
-- Party tank: in the second condition's dropdown, chosen, saved, read back
local subjLabels = {}
local want
gui.BeginCombo = function(id) return id == '##gsq-subj2' or id == '##gsq-op2' end
gui.Selectable = function(label)
    subjLabels[#subjLabels + 1] = label
    return label == want
end
Ed._S.draft = { num = 0, job = 'WHM', name = 'Tank rule', flags = 'o', rules = { rule('TARGET', 'NOT_HAS_TOP_ENMITY', nil, nil, nil, 'ja', 'PROVOKE') } }
Ed._S.sel = 1
step()
local offered = false
for _, l in ipairs(subjLabels) do offered = offered or l:find('^Party tank##') ~= nil end
check(offered, 'the second condition\'s dropdown offers "Party tank"')
for _, l in ipairs(subjLabels) do if l:find('^Party tank##') then want = l end end
step()
local tr = Ed._S.draft.rules[1]
check(tr.cond2 == 'PT_HAS_TANK' and tr.arg2 == nil, 'choosing it gives PT_HAS_TANK ("there is one"): ' .. tostring(tr.cond2))
want = 'there is none##2'
step()
check(tr.cond2 == 'NOT_PT_HAS_TANK', 'and its comparison "there is none" gives NOT_PT_HAS_TANK: ' .. tostring(tr.cond2))
want = nil
gui.BeginCombo, gui.Selectable = realBC, realSel
check(balanced(gui) and Ed.rule_summary(tr, Ed._S.cat):find('Party has no tank', 1, true), 'shown as "Party has no tank"; balanced')
Ed.save(); run_until(idle, 30)
local tankNum = tonumber((Ed._S.message or ''):match('Saved as Rule Set (%d+)'))
local tankSet = stored(tankNum or -1)
check(tankSet and tankSet.rules[1].cond2 and tankSet.rules[1].cond2[1] == 'NOT_PT_HAS_TANK' and #R.ruleProblems(tankSet.rules[1]) == 0,
      'saved through the server (confirmed): the stored rule holds NOT_PT_HAS_TANK and passes the server checks')
Ed.open_set(tankNum or -1, false); run_until(idle, 20)
check(Ed._S.draft and Ed._S.draft.rules[1].cond2 == 'NOT_PT_HAS_TANK' and Ed.encode_rule(Ed._S.draft.rules[1]) == Ed.encode_rule(tr),
      'opened again: the same rule (loaded exactly)')
local usableTank = R.usableRules(tankSet, { job = 3, level = 25, subJob = 1, subLevel = 12 })
check(#usableTank == 1 and usableTank[1].cond2 and usableTank[1].cond2[1] == 'NOT_PT_HAS_TANK',
      'reapplied (WHM 25 / WAR 12): the server hands the rule to the engine with NOT_PT_HAS_TANK unchanged')
Ed._S.draft, Ed._S.sel = nil, nil
check(balanced(gui), 'balanced at the end of the hotfix checks')
end
-- ---------------------------------------------------------------- 12. version 4: the member's own eligible choices
section('v4: Mira WHM25/WAR12 sees exactly what the server allows her; clean names; saved actions kept; Check wording')
MIRA.sjob, MIRA.jobs[1] = 1, { level = 30 }       -- WAR, her own WAR level 30 -> sub level min(30, 12) = 12
GV.sizeApplied = true
Ed.load_mates(); run_until(idle, 30)
local m1 = Ed.mate()
check(m1 and m1.sub == 'WAR' and m1.subLevel == 12 and m1.level == 25, 'mates: Mira WHM 25 / WAR 12 (the sub level from the server)')
run_until(function() return Ed._S.cat and Ed._S.cat.perMate end, 30)
local c4 = Ed._S.cat
check(c4 and c4.perMate, 'the editor loaded Mira\'s own catalog (catm)')
local jaNames = {}
for _, e in ipairs(Ed.ja_choices(c4, m1)) do jaNames[e.name] = e end
check(jaNames.PROVOKE and jaNames.PROVOKE.sub and jaNames.DIVINE_SEAL and jaNames.BENEDICTION, 'offered: Provoke (WAR sub), Divine Seal, Benediction')
local wrong = {}
for _, no in ipairs({ 'BERSERK', 'DEFENDER', 'WARCRY', 'AGGRESSOR', 'RETALIATION', 'TOMAHAWK', 'MIGHTY_STRIKES', 'MARTYR', 'DEVOTION',
                      'AFFLATUS_SOLACE', 'AFFLATUS_MISERY', 'ASYLUM' }) do
    if jaNames[no] then wrong[#wrong + 1] = no end
end
check(#wrong == 0, 'not offered: Berserk, Defender, Warcry, Aggressor, Retaliation, Tomahawk, Mighty Strikes, Martyr, Devotion, Afflatus, Asylum ' .. table.concat(wrong, ','))
local sp4 = Ed.spell_choices(c4, m1)
local spIdx = {}
for i, e in ipairs(sp4) do spIdx[e.name] = i end
check(spIdx.CURE and spIdx.CURE_II == spIdx.CURE + 1 and spIdx.CURE_III == spIdx.CURE + 2 and not spIdx.CURE_IV and not spIdx.DIAGA_II,
      'spells: Cure, Cure II, Cure III together; no Cure IV, no Diaga II (no scroll)')
check(sp4[spIdx.CURE_II].label == 'Cure II' and Ed.choice_tip(sp4[spIdx.CURE_II], m1):find('level 11', 1, true),
      'names without levels; the level in the tooltip: ' .. Ed.choice_tip(sp4[spIdx.CURE_II], m1))
check(Ed.choice_tip(jaNames.PROVOKE, m1):find('sub job (WAR), level 5', 1, true), 'Provoke\'s tooltip: ' .. Ed.choice_tip(jaNames.PROVOKE, m1))
-- saved rules with actions she cannot use now: kept exactly, explained
local keep = {
    { on = true, target = 'SELF', cond = 'ALWAYS', kind = 'ja', name = 'BERSERK' },
    { on = true, target = 'SELF', cond = 'ALWAYS', kind = 'ja', name = 'MIGHTY_STRIKES' },
    { on = true, target = 'PARTY', cond = 'HPP_LT', arg = '40', kind = 'spell', name = 'CURE_IV' },
}
local before4 = {}
for i, r in ipairs(keep) do before4[i] = Ed.encode_rule(r) end
Ed._S.draft = { num = 0, job = 'WHM', name = 'Keep v4', flags = 'o', rules = keep }
for i = 1, 3 do Ed._S.sel = i; step() end
local same4 = true
for i, r in ipairs(keep) do same4 = same4 and Ed.encode_rule(r) == before4[i] end
check(same4, 'drawing keeps the saved Berserk, Mighty Strikes and Cure IV exactly')
check(Ed.action_note(keep[1], c4, m1):find('not in Mira\'s job abilities', 1, true) and Ed.action_note(keep[2], c4, m1):find('kept as saved', 1, true)
      and Ed.action_note(keep[3], c4, m1):find('spell list', 1, true), 'each gets a note: not usable now, kept as saved, the server decides')
check(Ed.action_note({ kind = 'ja', name = 'PROVOKE' }, c4, m1) == nil, 'no note for Provoke (she has it)')
-- Check wording and its levels
local labels = {}
local realButton = gui.Button
gui.Button = function(label, ...) labels[#labels + 1] = label; return realButton(label, ...) end
game.party = {}
Ed.load_mates(); run_until(idle, 20)
Ed._S.sets = { { num = 1, job = 'WHM', rules = 2, flags = 'm', rev = '1', id = 'x', name = 'WHM - Cure basics' } }
Ed._S.selectedSet = 1
labels = {}
step()
local sawLabel = false
for _, l in ipairs(labels) do if l == 'Check (Mira not summoned)##gsq-check' then sawLabel = true end end
check(sawLabel, 'the Check button reads "Check (Mira not summoned)"')
Ed.check_set(1, 1); run_until(idle, 20)
check(Ed._S.messageWarn and Ed._S.message:find('^Summon Mira before checking this Rule Set%.'), 'not summoned: ' .. tostring(Ed._S.message))
check(#game.sends > 0, '(Check asked the server; it never summons anyone)')
-- summoned and synced down to 10: Check says it checked at the current level; the editor's choices do not change
local live = trust(11)
live.getMainJob = function() return 3 end
live.getMainLvl = function() return 10 end
live.getSubJob = function() return 1 end
live.getSubLvl = function() return 5 end
game.party = { live }
Ed.load_mates(); run_until(idle, 20)
Ed.check_set(1, 1); run_until(idle, 20)
check(Ed._S.message:find('checked at Mira\'s current level: WHM 10 / WAR 5, Level Sync', 1, true), 'synced Check: ' .. tostring(Ed._S.message))
local jaAfter = {}
for _, e in ipairs(Ed.ja_choices(Ed._S.cat, Ed.mate())) do jaAfter[e.name] = true end
check(jaAfter.DIVINE_SEAL and jaAfter.PROVOKE and Ed.mate().level == 25, 'while synced to 10, the editor still shows WHM25/WAR12\'s choices (Divine Seal 15, Provoke)')
gui.Button = realButton
game.party = {}
-- an older (v3) server: the job's catalog, the editor's own filters, clean names
Ed._S.server.version = 3
Ed._S.catJob = nil
Ed.load_catalog_for(Ed.mate()); run_until(idle, 20)
check(Ed._S.cat and not Ed._S.cat.perMate and Ed.spell_choices(Ed._S.cat, Ed.mate())[1].label:find('%(') == nil,
      'a v3 server: the job catalog (cat), names still clean')
Ed._S.server.version = 4
-- a damaged member catalog is refused like any other
local mlines = {}
local realPrint = player.printToPlayer
player.printToPlayer = function(_, l) mlines[#mlines + 1] = l end
Gs.handle(player, 'catm 5 1')
player.printToPlayer = realPrint
local mi, me = {}, nil
for _, l in ipairs(mlines) do local fl = Tr.split(l, '|'); if fl[3] == 'end' then me = fl else mi[#mi + 1] = fl end end
check(Ed.parse_catalog(mi, me) and Ed.parse_catalog(mi, me).perMate, 'the member catalog parses (6 kinds)')
local cut = {}
for i = 1, #mi do cut[i] = mi[i] end
table.remove(cut, #cut)
check(Ed.parse_catalog(cut, me) == nil, 'a member catalog with a missing line is refused')
local bad = {}
for i = 1, #mi do bad[i] = mi[i] end
local swapped = false
for _, fl in ipairs(bad) do if fl[5] == 's' and not swapped then fl[5] = 'u'; swapped = true end end
check(Ed.parse_catalog(bad, me) == nil, 'a member catalog with a spell line relabelled as unconfirmed is refused')
MIRA.sjob, MIRA.jobs[1] = 0, nil
io.write(string.format('\npassed %d, failed %d\n', passed, failed))
os.exit(failed == 0 and 0 or 1)
