-- Squad Role clarity (2026-11-22), the kit side: the role help in the Squad menu (servermenu), the Squad panel
-- (squadpanel) and the launcher says what the server's role filter really does, the gold note shows only where a
-- Tank / Damage Role restricts a job's default healing, and the Gambits editor tells its Party Roles apart from the
-- Squad Role. Stand-in Ashita and ImGui; nothing is written outside a temporary folder.
--   luajit test_squad_role_clarity_ui.lua [<server>/modules/custom/lua/squad.lua]
-- With the server's squad.lua the texts are checked against its EMERGENCY_HP, MODE_HEAL_SHIFT and ROLE_KEEPS tables.
local HERE = (arg and arg[0] and arg[0]:match('^(.*)[/\\][^/\\]*$')) or '.'
local KIT = HERE .. '/../..'
local SERVER_SQUAD = arg[1]
io.stdout:setvbuf('no')
local passed, failed = 0, 0
local function check(cond, label) if cond then passed = passed + 1 else failed = failed + 1 io.write('FAIL: ', label, '\n') end end
local function section(name) io.write('\n== ', name, '\n') end
local function slurp(path) local f = io.open(path, 'rb') if not f then return nil end local s = f:read('*a') f:close() return s end
local function has(text, needle) return tostring(text):find(needle, 1, true) ~= nil end
local realPrint = print

-- ---------------------------------------------------------------- a stand-in ImGui that records text and tooltips
local function makeImgui(W)
    local missing = W.missing or {}
    local im = setmetatable({}, { __index = function(_, name) if missing[name] then return nil end return function() end end })
    local function event(kind, text, color, extra)
        W.events[#W.events + 1] = { kind = kind, text = tostring(text), color = color, wrap = extra and extra.wrap, how = extra and extra.how }
    end
    -- (polish) a wrapped tooltip: BeginTooltip, PushTextWrapPos(w), TextUnformatted, PopTextWrapPos, EndTooltip
    W.tipBalance, W.wrapBalance, W.wrapStack = 0, 0, {}
    function im.GetFontSize() return 13 end
    function im.BeginTooltip() W.tipBalance = W.tipBalance + 1; W.inTip = true return true end
    function im.EndTooltip() W.tipBalance = W.tipBalance - 1; W.inTip = false end
    function im.PushTextWrapPos(w) W.wrapBalance = W.wrapBalance + 1; W.wrapStack[#W.wrapStack + 1] = w end
    function im.PopTextWrapPos() W.wrapBalance = W.wrapBalance - 1; W.wrapStack[#W.wrapStack] = nil end
    function im.TextUnformatted(t)
        local w = W.wrapStack[#W.wrapStack]
        if W.inTip then event('tip', t, nil, { wrap = w, how = 'unformatted' }) else event('text', t, nil, { wrap = w, how = 'unformatted' }) end
    end
    function im.Begin(title) W.balance = W.balance + 1 return true end
    function im.End() W.balance = W.balance - 1 end
    function im.BeginChild() return true end
    function im.Button(l) event('button', l) return false end
    function im.Text(t) event('text', t) end
    function im.TextWrapped(t) event('text', t) end
    function im.TextColored(c, t) event('text', t, c) end
    function im.BeginCombo(id, preview) event('combo', id .. '=' .. tostring(preview)) return false end
    function im.Selectable() return false end
    function im.Checkbox() return false end
    function im.InputText() return false end
    function im.CollapsingHeader() return false end
    function im.IsItemHovered() return true end
    function im.SetTooltip(t) event('tip', t, nil, { how = 'settooltip' }) end
    for name in pairs(missing) do im[name] = nil end
    function im.GetWindowWidth() return 620 end
    function im.GetContentRegionAvail() return { 600, 400 } end
    function im.GetCursorScreenPos() return { 0, 0 } end
    function im.GetWindowDrawList() return setmetatable({}, { __index = function() return function() end end }) end
    function im.ColorConvertFloat4ToU32() return 0 end
    function im.CalcTextSize(t) return { #tostring(t) * 7, 13 } end
    function im.GetWindowPos() return 0, 0 end
    return im
end

local function boot(path, missing)
    local W = { handlers = {}, events = {}, sent = {}, balance = 0, clock = 100, missing = missing }
    local chat = { }
    function chat:QueueCommand(_, command) W.sent[#W.sent + 1] = command end
    function chat:IsInputOpen() return false end
    local dir = os.tmpname(); os.remove(dir)
    if package.config:sub(1, 1) == '\\' then os.execute('mkdir "' .. dir .. '" 2>nul') else os.execute('mkdir -p "' .. dir .. '"') end
    addon = {}
    ashita = { events = { register = function(name, _, fn) W.handlers[name] = fn end }, time = { get_tick64 = function() return W.clock * 1000 end },
               fs = { create_directory = function() end } }
    AshitaCore = { GetChatManager = function() return chat end, GetInstallPath = function() return dir .. '/' end,
                   GetMemoryManager = function() return setmetatable({}, { __index = function() return function() return setmetatable({}, { __index = function() return function() return '' end end }) end end }) end }
    function string.args(s) local t = {} for w in s:gmatch('%S+') do t[#t + 1] = w end return t end
    package.loaded['common'] = true
    package.loaded['imgui'] = nil
    package.preload['imgui'] = function() return makeImgui(W) end
    package.loaded['ffi'], package.loaded['d3d8'] = nil, nil
    package.preload['ffi'] = function() error('no ffi here') end
    package.preload['d3d8'] = function() error('no d3d8 here') end
    for name, v in pairs({ ImGuiCol_Button = 21, ImGuiCol_ButtonHovered = 22, ImGuiCol_ButtonActive = 23, ImGuiCol_Text = 0, ImGuiCol_WindowBg = 2,
                           ImGuiStyleVar_WindowRounding = 3, ImGuiCond_FirstUseEver = 4, ImGuiCond_Always = 1, ImGuiWindowFlags_NoTitleBar = 1,
                           ImGuiWindowFlags_NoMove = 4, ImGuiCol_PlotHistogram = 40 }) do rawset(_G, name, v) end
    print = function() end
    assert(loadfile(path))()
    print = realPrint
    W.handlers.load()
    function W.frame() W.clock = W.clock + 0.25; W.events = {}; W.handlers.d3d_present() end
    function W.command(text) local e = { command = text, blocked = false } W.handlers.command(e) return e end
    function W.line(text) local e = { message = text, blocked = false } W.handlers.text_in(e) return e end
    -- the text drawn, and the tooltip right after it
    function W.tipAfter(fragment)
        for i, e in ipairs(W.events) do
            if e.kind == 'text' and has(e.text, fragment) then
                local nxt = W.events[i + 1]
                return e, nxt and nxt.kind == 'tip' and nxt.text or nil
            end
        end
        return nil
    end
    function W.texts(fragment)
        local n = 0
        for _, e in ipairs(W.events) do if e.kind == 'text' and has(e.text, fragment) then n = n + 1 end end
        return n
    end
    function W.tips(fragment)
        local n = 0
        for _, e in ipairs(W.events) do if e.kind == 'tip' and has(e.text, fragment) then n = n + 1 end end
        return n
    end
    return W
end

-- the mate lines the server sends (slot|name|main|level|sub|level|role|mode|out|switches)
local MATES = {
    'squadpanel:1|Aldric|WHM|7|BLM|3|damage|balanced|1|15',   -- the reported case
    'squadpanel:2|Bob|WAR|30|-|0|damage|balanced|1|15',        -- no healing to restrict
    'squadpanel:3|Kyo|PLD|30|WAR|15|tank|balanced|1|15',        -- the usual PLD tank: no note
    'squadpanel:4|Rhea|RDM|30|-|0|tank|aggressive|1|15',        -- RDM tank, aggressive: 55%
    'squadpanel:5|Mira|WHM|30|-|0|auto|balanced|1|15',          -- Auto: no note
    'squadpanel:6|Hild|WAR|30|WHM|15|damage|conserve|1|15',     -- a WHM sub job, conserve: 15%
    'squadpanel:7|Sera|WHM|30|-|0|healer|balanced|1|15',        -- Healer keeps healing: no note
    'squadpanel:8|Pax|PLD|30|-|0|damage|balanced|1|15',         -- PLD on Damage: its Cure is limited
    'squadpanel:end',
}
local function feed(W, prefix)
    for _, l in ipairs(MATES) do W.line(prefix .. l) end
    W.frame()
end

-- ================================================================= 1. the server's filter, read from its squad.lua
local FACTS = { cap = { tank = 40, damage = 30 }, shift = { aggressive = 15, conserve = -15 } }
section('the facts the texts must match (from the server\'s squad.lua)')
if SERVER_SQUAD then
    local src = assert(slurp(SERVER_SQUAD), 'cannot read ' .. SERVER_SQUAD)
    local cap = assert(load('return ' .. src:match('local EMERGENCY_HP%s*=%s*(%b{})')))()
    local shift = assert(load('return ' .. src:match('local MODE_HEAL_SHIFT%s*=%s*(%b{})')))()
    local keeps = assert(load('return ' .. src:match('local ROLE_KEEPS%s*=%s*(%b{})')))()
    check(cap.tank == 40 and cap.damage == 30 and shift.aggressive == 15 and shift.conserve == -15,
          'EMERGENCY_HP tank 40 / damage 30, MODE_HEAL_SHIFT +15 / -15 (what the texts say)')
    check(keeps.cleanse.tank == false and keeps.cleanse.damage == false and keeps.cleanse.healer and keeps.cleanse.support,
          'ROLE_KEEPS: Tank and Damage drop status removal, Healer and Support keep it')
    check(keeps.buff.tank == 'self' and keeps.buff.damage == 'self', 'ROLE_KEEPS: Tank and Damage keep buffs on themselves only')
    check(keeps.nuke.damage == true and keeps.nuke.tank == false and keeps.nuke.healer == false and keeps.nuke.support == false,
          'ROLE_KEEPS: only Damage nukes')
    check(keeps.debuff.healer == false and keeps.debuff.tank and keeps.debuff.damage and keeps.debuff.support, 'ROLE_KEEPS: only Healer drops debuffs')
    check(keeps.ranged.tank == false and keeps.ranged.healer == false and keeps.ranged.damage and keeps.ranged.support,
          'ROLE_KEEPS: Tank and Healer drop ranged attacks')
    check(keeps.tankja.tank and not keeps.tankja.damage and not keeps.tankja.healer and not keeps.tankja.support,
          'ROLE_KEEPS: only Tank keeps the tank abilities')
    check(keeps.meleeja.tank and keeps.meleeja.damage and not keeps.meleeja.healer and not keeps.meleeja.support and keeps.utility == nil,
          'ROLE_KEEPS: Healer and Support drop job abilities, none says anything about Convert / Chakra (they stay)')
    check(keeps.heal.tank == 'emergency' and keeps.heal.damage == 'emergency', 'ROLE_KEEPS: Tank and Damage cure only in an emergency')
    FACTS.cap, FACTS.shift = cap, shift
else
    io.write('  (no server squad.lua given: the numbers below are the ones of server dev 0d6cad7e3f)\n')
end
local function limit(role, mode) return math.max(15, math.min(90, FACTS.cap[role] + (FACTS.shift[mode] or 0))) end

-- ================================================================= 2. the Squad menu (servermenu)
section('Squad menu: role tooltips')
local W = boot(KIT .. '/addons-src/servermenu/servermenu.lua')
W.command('/sq'); W.frame()
feed(W, '[Hurami] : ')
check(W.balance == 0, 'every Begin has its End')
local tipDamage = nil
for _, e in ipairs(W.events) do if e.kind == 'tip' and has(e.text, 'Damage: keeps attacks') then tipDamage = e.text end end
check(tipDamage ~= nil, 'the Damage tooltip is shown on a Damage mate\'s Role')
for _, need in ipairs({ 'below ' .. limit('damage') .. '% HP', 'Aggressive ' .. limit('damage', 'aggressive') .. '%',
                        'Conserve ' .. limit('damage', 'conserve') .. '%', 'No status removal', 'no buffs on others',
                        'no Provoke or Sentinel', 'only the mate\'s default job rules', 'next call',
                        'A Gambits Rule Set replaces those rules and is not filtered', 'Gambits party roles (Tank / Melee / Mage / Ranged)' }) do
    check(has(tipDamage, need), 'Damage tooltip says "' .. need .. '"')
end
local tipTank, tipAuto, tipHealer
for _, e in ipairs(W.events) do
    if e.kind == 'tip' and has(e.text, 'Tank: keeps Provoke') then tipTank = e.text end
    if e.kind == 'tip' and has(e.text, 'Auto: the job') then tipAuto = e.text end
    if e.kind == 'tip' and has(e.text, 'Healer: keeps cures') then tipHealer = e.text end
end
check(tipTank and has(tipTank, 'below ' .. limit('tank') .. '% HP') and has(tipTank, 'Aggressive ' .. limit('tank', 'aggressive') .. '%')
      and has(tipTank, 'Conserve ' .. limit('tank', 'conserve') .. '%') and has(tipTank, 'No status removal') and has(tipTank, 'no nukes or ranged attacks'),
      'Tank tooltip: 40% (55 / 25), no status removal, no nukes or ranged attacks')
check(tipAuto and has(tipAuto, 'nothing filtered'), 'Auto tooltip: nothing filtered')
check(tipHealer and has(tipHealer, 'No debuffs') and has(tipHealer, 'Convert and Chakra stay') and not has(tipHealer, 'below'),
      'Healer tooltip: no debuffs, nukes, ranged or job abilities (Convert / Chakra stay), no HP limit')
check(W.tips('heals only the badly hurt') == 0, 'no "heals only the badly hurt" left on the Squad tab')

section('Squad menu: the gold note')
local e, tip = W.tipAfter('(i) WHM - Role: Damage')
check(e ~= nil and e.color ~= nil and e.color[1] > 0.8 and e.color[2] > 0.6 and e.color[3] < 0.5, 'Aldric (WHM/BLM, Damage): a gold "(i) WHM - Role: Damage"')
check(tip and has(tip, 'Default healing is heavily restricted') and has(tip, 'cures only below 30% HP') and has(tip, 'no status removal')
      and has(tip, 'no buffs on party members'), 'its tooltip: healing restricted, 30%, no status removal, no party buffs: ' .. tostring(tip))
check(tip and has(tip, 'valid choice for an offensive WHM') and has(tip, 'only to the default job rules')
      and has(tip, 'Gambits Rule Set replaces them'), 'it does not call Damage wrong, and speaks only of the default job rules')
check(tip and not has(tip, 'is filtering') and not has(tip, 'invalid'), 'it never claims the filter is active (the menu cannot see a Rule Set)')
check(W.texts('(i) ') == 4, 'exactly four notes (Aldric, Rhea, Hild, Pax): ' .. W.texts('(i) '))
local _, tipRhea = W.tipAfter('(i) RDM - Role: Tank')
check(tipRhea and has(tipRhea, 'below 55% HP') and has(tipRhea, 'no buffs on party members') and not has(tipRhea, 'status removal'),
      'Rhea (RDM, Tank, Aggressive): 55%, no party buffs, nothing about status removal (an RDM has none)')
local _, tipHild = W.tipAfter('(i) WHM - Role: Damage')
check(W.texts('(i) WHM - Role: Damage') == 2, 'Hild (WAR/WHM, Damage) gets the note for the WHM sub job')
local _, tipPax = W.tipAfter('(i) PLD - Role: Damage')
check(tipPax and has(tipPax, 'below 30% HP') and not has(tipPax, 'status removal') and not has(tipPax, 'party members'),
      'Pax (PLD, Damage): only the Cure limit')
check(W.texts('WAR - Role') == 0 and W.texts('Role: Auto') == 0 and W.texts('Role: Healer') == 0 and W.texts('(i) PLD - Role: Tank') == 0,
      'no note for WAR on Damage, Auto, Healer, or the usual PLD/WAR tank')
local hildLine = nil
for _, l in ipairs(MATES) do if has(l, 'Hild') then hildLine = l end end
check(hildLine ~= nil, 'Hild is in the list')

section('Squad menu: the Dualbox profiles keep their own text')
local SM = slurp(KIT .. '/addons-src/servermenu/servermenu.lua')
check(has(SM, 'tooltip(ROLE_INFO.DUO[role])') and has(SM, "combo('role' .. mate.slot, mate.role, ROLES, 120, ROLE_INFO.TIPS, ROLE_INFO.tip)"),
      'the squad Role uses the new tooltips, the Dualbox profile buttons their old ones')

-- ================================================================= (polish) wrapped tooltips, the same in both addons
local WRAP = 13 * 27   -- the stand-in font is 13 px: 27 characters' width, as the Gambits editor (M.TOOLTIP_WRAP_EM)
local function roleTips(X)
    local out = {}
    for _, e in ipairs(X.events) do
        if e.kind == 'tip' and (has(e.text, 'Squad Role changes only') or has(e.text, 'Default healing is heavily restricted')
            or has(e.text, 'Aggressive: cures') or has(e.text, 'Conserve: cures') or has(e.text, 'Balanced: the normal')) then out[#out + 1] = e end
    end
    return out
end
local function checkWrapped(X, name)
    local tips = roleTips(X)
    local allWrapped = #tips > 0
    for _, e in ipairs(tips) do if e.how ~= 'unformatted' or e.wrap ~= WRAP then allWrapped = false end end
    check(allWrapped, name .. ': every Role / Mode / note tooltip (' .. #tips .. ') is drawn wrapped at ' .. WRAP .. ' px with TextUnformatted')
    check(X.tipBalance == 0 and X.wrapBalance == 0, name .. ': every BeginTooltip / PushTextWrapPos is closed')
    local viaSet = 0
    for _, e in ipairs(X.events) do if e.how == 'settooltip' and has(e.text, '%') then viaSet = viaSet + 1 end end
    check(viaSet == 0, name .. ': no text with % goes through SetTooltip (Ashita reads it as a printf format)')
end
section('Squad menu: wrapped tooltips')
checkWrapped(W, 'Squad menu')
local longest = 0
for _, t in pairs({ tipDamage, tipTank, tip }) do
    local words = 0
    for line in tostring(t):gmatch('[^\n]+') do words = math.max(words, #line) end
    longest = math.max(longest, words)
end
check(longest > WRAP / 7, 'the texts are longer than one wrapped line (' .. longest .. ' characters), so the wrap is what keeps them narrow')
section('Squad menu: without BeginTooltip (an older binding): SetTooltip with % doubled')
local WF = boot(KIT .. '/addons-src/servermenu/servermenu.lua', { BeginTooltip = true })
WF.command('/sq'); WF.frame(); feed(WF, '[Hurami] : ')
local fallback = nil
for _, e in ipairs(WF.events) do if e.how == 'settooltip' and has(e.text, 'Default healing is heavily restricted') then fallback = e.text end end
check(fallback and has(fallback, '30%% HP') and not fallback:find('[^%%]%%[^%%]'), 'the note through SetTooltip: every % doubled (shows one %)')

-- ================================================================= 3. the Squad panel (squadpanel)
section('Squad panel: tooltips, the note and the legend')
local P = boot(KIT .. '/addons-src/squadpanel/squadpanel.lua')
P.command('/sq'); P.frame()
feed(P, '[Hurami] : ')
check(P.balance == 0, 'every Begin has its End')
check(P.tips('Damage: keeps attacks') >= 1 and P.tips('Tank: keeps Provoke') >= 1 and P.tips('A Gambits Rule Set replaces those rules') >= 1,
      'the role buttons carry the same tooltips as the Squad menu')
check(P.tips('Aggressive: cures at 15% more HP') >= 1, 'the mode buttons carry their help')
local pe, ptip = P.tipAfter('(i) WHM - Role: Damage')
check(pe ~= nil and pe.color ~= nil and pe.color[1] > 0.8, 'Aldric: the gold note')
check(ptip and has(ptip, 'cures only below 30% HP') and has(ptip, 'only to the default job rules'), 'with the same tooltip')
check(P.texts('(i) ') == 4, 'the same four notes: ' .. P.texts('(i) '))
check(P.texts('heals only the badly hurt') == 0 and P.texts('cures only below 30% HP, no status removal') == 1
      and P.texts('a Gambits Rule Set is not filtered') == 1, 'the legend under the mates is the new one')
local SP = slurp(KIT .. '/addons-src/squadpanel/squadpanel.lua')
check(has(SP, "addon.version = '0.14'"), 'squadpanel 0.14')
checkWrapped(P, 'Squad panel')
local legendOk = 0
for _, e in ipairs(P.events) do
    if e.kind == 'text' and e.how == 'unformatted' and e.wrap == 0 and (e.text == '' or has(e.text, 'tank: Provoke') or has(e.text, 'aggressive: cures')
        or has(e.text, 'The Role filters only')) then legendOk = legendOk + 1 end
end
check(legendOk == 3, 'the three legend lines are drawn wrapped and unformatted (they contain %): ' .. legendOk)
local PF = boot(KIT .. '/addons-src/squadpanel/squadpanel.lua', { BeginTooltip = true, TextUnformatted = true })
PF.command('/sq'); PF.frame(); feed(PF, '[Hurami] : ')
local pf, legendF = nil, nil
for _, e in ipairs(PF.events) do
    if e.how == 'settooltip' and has(e.text, 'Default healing is heavily restricted') then pf = e.text end
    if e.kind == 'text' and has(e.text, 'tank: Provoke') then legendF = e.text end
end
check(pf and has(pf, '30%% HP') and legendF and has(legendF, '40%% HP'), 'an older binding: the note and the legend with % doubled')

-- the three copies of the help say the same
section('the Squad menu, the Squad panel and the launcher say the same')
for _, line in ipairs({ "Cures only targets below 40% HP (Aggressive 55%, Conserve 25%)", "Cures only targets below 30% HP (Aggressive 45%, Conserve 15%)",
                        "No debuffs (Flash, Dia, Paralyze...), nukes, ranged attacks or job abilities (Convert and Chakra stay).",
                        "No nukes and no job abilities (Convert and Chakra stay)." }) do
    check(has(SM, line) and has(SP, line), 'both addons: ' .. line)
end
local LS = slurp(KIT .. '/launcher_squad.py')
check(has(LS, 'cures only below 40% HP') and has(LS, 'cures only below 30% HP') and has(LS, 'filtered by the role')
      and has(LS, 'not the Gambits party role'), 'the launcher\'s Behavior page: the same limits and the Rule Set / party role notes')
check(not has(slurp(KIT .. '/launcher_gui.pyw'), 'heals only the badly hurt.\\n'), 'the launcher\'s old legend is gone')

-- ================================================================= 4. the Gambits editor (U5)
section('Gambits editor: Party Roles are not the Squad Role')
local ADDON_DIR = KIT .. '/addons-src/Gambits'
package.path = ADDON_DIR .. '/?.lua;' .. package.path
print = function() end
local M = dofile(ADDON_DIR .. '/squad_editor.lua')
print = realPrint
for _, key in ipairs({ 'TANK', 'CASTER', 'MELEE', 'RANGED' }) do
    local h = M.TARGET_HELP[key]
    check(has(h, 'Gambits Party Role: decides who this target is') and has(h, 'Squad Role, which only filters default job rules')
          and has(h, 'a Rule Set replaces those and is not filtered'), key .. ': the short note names the three things')
    check(has(h, '!squad partyrole') and h:find('^A party member whose main job is') ~= nil, key .. ': the job-specific description is kept, first')
end
check(#M.PARTY_ROLE_NOTE <= 170, '(polish) the shared note is short: ' .. #M.PARTY_ROLE_NOTE .. ' characters (was 316)')
check(M.TOOLTIP_WRAP_EM == 27, 'the editor wraps its tooltips at 27 characters\' width (unchanged since 0.3.1)')
for _, key in ipairs({ 'SELF', 'PARTY', 'PARTY_LOWEST_HPP', 'TARGET', 'MASTER', 'TOP_ENMITY' }) do
    check(not has(M.TARGET_HELP[key], 'Party Role'), key .. ': no Party Role note (not a role target)')
end
check(has(M.ROLES_HELP, 'Gambits Party Roles') and has(M.ROLES_HELP, 'Mage (CASTER)') and has(M.ROLES_HELP, 'Auto / Tank / Damage / Healer / Support')
      and has(M.ROLES_HELP, 'never a Rule Set') and has(M.ROLES_HELP, 'does not make a mate a Tank target') and #M.ROLES_HELP <= 300,
      'the Party roles section help names both systems, shorter (' .. #M.ROLES_HELP .. ' characters)')
check(has(M.DEFAULT_RULES_HELP, 'filtered by the Squad Role and Mode') and has(M.DEFAULT_RULES_HELP, 'below 30% HP')
      and has(M.DEFAULT_RULES_HELP, 'replaces them and is not filtered') and #M.DEFAULT_RULES_HELP <= 200,
      'the "uses: default job rules" tooltip (' .. #M.DEFAULT_RULES_HELP .. ' characters)')
local ED = slurp(ADDON_DIR .. '/squad_editor.lua')
check(ED:find("or 'default job rules'%)%)\r?\n%s+tooltip%(M%.DEFAULT_RULES_HELP%)") ~= nil, 'it is shown on the "X uses: ..." line of the set panel')
check(has(ED, 'The Squad Role and Mode (Squad menu) filter those job rules again.'), '"Restore default job rules" says the Role filters them again')
check(M.TARGET_LABELS.CASTER == 'Mage' and M.TARGET_LABELS.TANK == 'Tank' and M.ROLE_NAMES[3] == 'Mage', 'labels and party role names unchanged')

io.write(string.format('\npassed %d, failed %d\n', passed, failed))
os.exit(failed == 0 and 0 or 1)
