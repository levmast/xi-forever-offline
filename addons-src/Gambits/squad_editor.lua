--[[
GambitsV2 Squad editor: an in-game editor for your squad mates' Rule Sets (Gambits v2, milestone 2).

Everything you change here stays in this window until you press Save: editing, ordering and switching rules never talks
to the server. The server (!gsq, gambits_squad.lua) is asked only to Load, Save, Check and Delete; choosing a Rule Set
for a mate and applying it use the squad commands you could type yourself (!squad ruleset <slot> <num>, !squad reapply).
The server checks every set (it decides what a mate may use) and writes squad_rulesets_data.lua; nothing is stored by the
game client except an unsaved draft (config/addons/GambitsV2/squad_draft.lua).

Nothing is reported as done because a line was queued:
  Save / Delete  only on the server's ok; when the outcome is unknown (no answer, zoning, a lost save), the editor reads
                 the set list back before it says anything, and never writes again on its own
  Assign         confirmed by reading the mate's chosen set back from the server
  Apply          confirmed by reading back that the mates left and came back; otherwise "not confirmed"
Transport: transport.lua (one line at a time, >= 1 s apart, refused lines detected and sent again).
Saves: up to 32 rules of any valid length (server version 2 streams a save in up to 48 chunks; version 1 servers take
what fits in 16 lines).
]]

local M = {}
M.VERSION      = '2.0.0'
M.MAX_LINE     = 120     -- bytes, the whole /say line
M.MAX_RULES    = 32      -- the server's limit (hello) - the only limit players see
M.MAX_PARTS    = 16      -- version 1 servers (w)
M.MAX_CHUNKS   = 64      -- version 3 servers (x): 32 of the most complex valid rules need about 49
M.MAX_STREAM   = 6144    -- bytes of one save (the server's limit)
M.ROWS_SHOWN   = 14
M.NAME_MAX     = 24
M.APPLY_RECALL = 4.0     -- squad.lua: RECALL_WAIT_MS 4000, then CALL_GAP_MS 1500 per further mate
M.APPLY_GAP    = 1.5

local api = {}          -- given by GambitsV2.lua: now, input_open, queue_command, log, root, writefile, imgui, s ...
local T                 -- transport.lua
local S = {
    nonce = 0, server = nil, pings = {}, mates = {}, sets = {}, cat = nil, catJob = nil,
    mateSlot = nil, draft = nil, message = nil, messageOk = true, messageWarn = false, progress = nil, checks = {},
    confirmDelete = nil, apply = nil,
}
M._S = S

function M.init(a)
    api = a or {}
    T = api.transport or T
    if T == nil then
        local ok, mod = pcall(require, 'transport')
        T = ok and mod or nil
    end

    assert(T, 'transport.lua is missing')
    -- the Trust-summoning spells (trust_spells.lua, generated): never offered as a Specific Spell
    M.TRUSTS = api.trust_spells
    if type(M.TRUSTS) ~= 'table' then
        local okT, mod = pcall(require, 'trust_spells')
        M.TRUSTS = okT and type(mod) == 'table' and mod or {}
    end

    T.init({ now = api.now, queue_command = api.queue_command, input_open = api.input_open, log = api.log,
             config = api.transport_config })
    M.T = T
    M.load_draft()
end

local function now()
    return api.now and api.now() or os.clock()
end

-- ok: true (green), false (red, also logged), 'warn' (gold: not confirmed / wait)
local function say(text, ok)
    S.message, S.messageOk, S.messageWarn = text, ok ~= false, ok == 'warn'
    if api.log then
        api.log(text, ok == false)
    end
end
M.say = say

-- ---------------------------------------------------------------- rule codec (the same as gambits_squad.lua)
local KIND_CODE = { family = 'f', ja = 'j', spell = 's', ranged = 'r', nuke = 'n', burst = 'b' }
local CODE_KIND = { f = 'family', j = 'ja', s = 'spell', r = 'ranged', n = 'nuke', b = 'burst' }
M.NAMED_KINDS   = { family = true, ja = true, spell = true }   -- kinds with a name (ranged, nuke, burst have none)
M.MIN_SERVER    = 3                                             -- the wire format this editor writes (gambits_squad.lua)

local function split(text, sep)
    local out, start = {}, 1
    while true do
        local at = string.find(text, sep, start, true)
        if not at then
            out[#out + 1] = string.sub(text, start)
            return out
        end

        out[#out + 1] = string.sub(text, start, at - 1)
        start = at + #sep
    end
end
M.split = split

-- an editor row { on, target, cond, arg, cond2, arg2, kind, name, retry, level, id } <->
-- "1,PARTY,HPP_LT,50,,,f,CURE,[,LEVEL[,ID]]" (the same as gambits_squad.lua version 3; LEVEL and ID only when set;
-- ID only for a rule whose id is not "r<position>")
function M.encode_rule(r)
    local function s(v)
        return v == nil and '' or tostring(v)
    end

    local fields = { r.on == false and '0' or '1', s(r.target), s(r.cond), s(r.arg), s(r.cond2), s(r.arg2),
        KIND_CODE[r.kind] or s(r.kind), s(r.name), s(r.retry) }
    if r.level ~= nil or r.id ~= nil then
        fields[#fields + 1] = s(r.level)
    end

    if r.id ~= nil then
        fields[#fields + 1] = s(r.id)
    end

    return table.concat(fields, ',')
end

-- nil for "?" (a rule the server could not send exactly) or anything malformed
function M.decode_rule(text)
    local f = split(text or '', ',')
    if #f < 8 or #f > 11 then
        return nil
    end

    for _, field in ipairs(f) do
        if not string.match(field, '^[%w_%-%.]*$') then
            return nil
        end
    end

    local function v(x)
        return x ~= nil and x ~= '' and x or nil
    end

    local kind = CODE_KIND[f[7]]
    if kind == nil or (f[1] ~= '1' and f[1] ~= '0') or f[3] == '' then
        return nil
    end

    if (M.NAMED_KINDS[kind] and f[8] == '') or (not M.NAMED_KINDS[kind] and f[8] ~= '') then
        return nil
    end

    return { on = f[1] ~= '0', target = v(f[2]), cond = v(f[3]), arg = v(f[4]), cond2 = v(f[5]), arg2 = v(f[6]),
             kind = kind, name = v(f[8]), retry = v(f[9]), level = v(f[10]), id = v(f[11]) }
end

function M.name_code(name)
    return (string.gsub(name or '', ' ', '_'))
end

-- conditions that describe what the ENEMY is doing: only meaningful with the target Enemy (the engine reads them on the
-- rule's target)
M.ENEMY_CONDS = { CASTING_MA = true, READYING_WS = true, READYING_MS = true, READYING_JA = true }

-- (job expansion) the modifiers MOD_LT can name (the same list as squad_rulesets.lua R.MODS): name -> low, high, label.
-- Each one counts down as it absorbs a hit: Utsusemi shadows, Blink images.
M.MODS = {
    UTSUSEMI  = { 1, 7, 'Utsusemi shadows' },
    BLINK     = { 1, 3, 'Blink images' },
}
M.MOD_ORDER = { 'UTSUSEMI', 'BLINK' }

-- "UTSUSEMI.2" -> 'UTSUSEMI', 2 (nil for anything else)
function M.mod_parse(arg)
    local name, n = string.match(tostring(arg or ''), '^([A-Z]+)%.(%d+)$')
    if name == nil or M.MODS[name] == nil then
        return nil
    end

    return name, tonumber(n)
end

-- why a MOD_LT value is wrong, or nil
function M.mod_problem(arg)
    local name, n = M.mod_parse(arg)
    if name == nil then
        return 'needs Utsusemi shadows or Blink images and a number'
    end

    local m = M.MODS[name]
    if n < m[1] or n > m[2] then
        return string.format('needs a number %d-%d for %s', m[1], m[2], m[3])
    end

    return nil
end

-- a row the editor may not change: "?" from the server (kept exactly as it is), or a condition the server's catalog
-- does not describe (its value cannot be checked here). Returns why, or nil.
function M.protected(r, cat)
    if r.opaque then
        return 'it uses options this editor cannot show'
    end

    if cat and cat.conds then
        if r.cond and cat.conds[r.cond] == nil then
            return 'the server did not describe the condition ' .. r.cond
        end

        if r.cond2 and cat.conds[r.cond2] == nil then
            return 'the server did not describe the condition ' .. r.cond2
        end
    end

    return nil
end

-- Local checks before a save (the server checks again and decides): nil, or why
function M.check_draft(d, cat)
    if d == nil then
        return 'nothing to save'
    end

    local name = d.name or ''
    if name == '' or #name > M.NAME_MAX or not string.match(name, '^[%w %-]+$') then
        return 'the name must be 1-' .. M.NAME_MAX .. ' letters, digits, spaces or -'
    end

    if #d.rules == 0 then
        return 'add at least one rule'
    end

    if #d.rules > M.MAX_RULES then
        return 'at most ' .. M.MAX_RULES .. ' rules'
    end

    local on = 0
    for i, r in ipairs(d.rules) do
        if r.opaque then
            return 'rule ' .. i .. ' uses options this editor cannot show; saving here could lose them'
        end

        if r.on ~= false then
            on = on + 1
        end

        if not r.target or not r.cond or not r.kind then
            return 'rule ' .. i .. ' needs a target, a condition and an action'
        end

        if KIND_CODE[r.kind] == nil then
            return 'rule ' .. i .. ': unknown action ' .. tostring(r.kind)
        end

        if M.NAMED_KINDS[r.kind] and (r.name == nil or r.name == '') then
            return 'rule ' .. i .. ': choose the ' .. (r.kind == 'spell' and 'spell' or r.kind == 'ja' and 'job ability' or 'spell family')
        end

        if not M.NAMED_KINDS[r.kind] and r.name ~= nil then
            return 'rule ' .. i .. ': ' .. r.kind .. ' takes no name'
        end

        for _, pair in ipairs({ { r.cond, r.arg }, { r.cond2, r.arg2 } }) do
            local c = pair[1] and cat and cat.conds[pair[1]]
            if pair[1] and cat and c == nil then
                return 'rule ' .. i .. ': unknown condition ' .. pair[1]
            end

            if c and c.kind == 'r' then
                local n = tonumber(pair[2] or '')
                if n == nil or n ~= math.floor(n) or n < c.lo or n > c.hi then
                    return string.format('rule %d: %s needs a whole number %d-%d', i, M.cond_label(pair[1]), c.lo, c.hi)
                end
            elseif c and c.kind == 'e' then
                if not pair[2] or not string.match(pair[2], '^[A-Z][A-Z0-9_]*$') then
                    return string.format('rule %d: %s needs a status effect', i, M.cond_label(pair[1]))
                end
            elseif c and c.kind == 'j' then
                if not pair[2] or not string.match(pair[2], '^[A-Z][A-Z0-9_]*$') then
                    return string.format('rule %d: %s needs a job ability', i, M.cond_label(pair[1]))
                end
            elseif c and c.kind == 'm' then
                local why = M.mod_problem(pair[2])
                if why then
                    return string.format('rule %d: %s %s', i, M.cond_label(pair[1]), why)
                end
            elseif c and c.kind == 'n' and pair[2] ~= nil and pair[2] ~= '' then
                return string.format('rule %d: %s takes no value', i, M.cond_label(pair[1]))
            end

            if pair[1] and M.ENEMY_CONDS[pair[1]] and r.target ~= 'TARGET' then
                return string.format('rule %d: "%s" needs the target Enemy', i, M.cond_label(pair[1]))
            end
        end

        if r.retry ~= nil and r.retry ~= '' then
            local n = tonumber(r.retry)
            if n == nil or n < 0 or n > 3600 or n ~= math.floor(n) then
                return 'rule ' .. i .. ': the wait must be 0-3600 seconds'
            end
        end

        if r.level ~= nil then
            local n = tonumber(r.level)
            if n == nil or n < 0 or n > 75 or n ~= math.floor(n) then
                return 'rule ' .. i .. ': the level must be 0-75'
            end
        end
    end

    if on == 0 then
        return 'switch on at least one rule'
    end

    return nil
end
local function save_items(d)
    local items = { table.concat({ tostring(d.num or 0), d.rev or '-', d.job, tostring(#d.rules), M.name_code(d.name) }, ',') }
    for _, r in ipairs(d.rules) do
        items[#items + 1] = M.encode_rule(r)
    end

    return items
end

-- Version 1 servers: "/say !gsq w <token> <seq> <total> <items joined by ;>", each line ends on a rule boundary.
-- Item 1 is the header "num,rev,JOB,rules,name". Returns lines | nil, why
function M.pack_save(d, token)
    local items = save_items(d)
    for total = 1, M.MAX_PARTS do
        local lines, ok = {}, true
        local i = 1
        while i <= #items do
            local seq = #lines + 1
            local prefix = string.format('/say !gsq w %s %d %d ', token, seq, total)
            local data = items[i]
            if #prefix + #data > M.MAX_LINE then
                return nil, 'rule ' .. (i - 1) .. ' is too long for this server version (it needs the server update)'
            end

            i = i + 1
            while i <= #items and #prefix + #data + 1 + #items[i] <= M.MAX_LINE do
                data = data .. ';' .. items[i]
                i = i + 1
            end

            lines[#lines + 1] = prefix .. data
            if #lines > total then
                ok = false
                break
            end
        end

        if ok and #lines == total then
            return lines
        end
    end

    return nil, 'the Rule Set is too large for this server version (it needs the server update for up to ' .. M.MAX_RULES .. ' rules)'
end

-- Version 2 servers: the same text as one stream, cut into chunks at any byte:
-- "/say !gsq x <token> <seq> <total> <chunk>". 32 rules of the longest valid kind fit. Returns lines | nil, why
function M.pack_stream(d, token, maxChunks)
    maxChunks = maxChunks or M.MAX_CHUNKS
    local text = table.concat(save_items(d), ';')
    if not string.match(text, '^[%w_%-%.,;]+$') then
        return nil, 'a rule has a character that cannot be sent'
    end

    if #text > M.MAX_STREAM then
        return nil, 'the Rule Set is larger than ' .. M.MAX_STREAM .. ' bytes'
    end

    local widest = string.format('/say !gsq x %s %d %d ', token, maxChunks, maxChunks)
    local size = M.MAX_LINE - #widest
    local chunks = {}
    for at = 1, #text, size do
        chunks[#chunks + 1] = string.sub(text, at, at + size - 1)
    end

    if #chunks > maxChunks then
        return nil, 'the Rule Set is too large to send'
    end

    local lines = {}
    for seq, chunk in ipairs(chunks) do
        lines[seq] = string.format('/say !gsq x %s %d %d %s', token, seq, #chunks, chunk)
    end

    return lines
end

-- the packing the connected server understands. This editor writes the version 3 rule format (spells, ranged, nuke,
-- burst, rule levels and ids), so an older server is refused here instead of misreading a rule.
function M.pack(d, token)
    local v = S.server and S.server.version or 1
    if v < M.MIN_SERVER then
        return nil, 'the server needs the update (gambits_squad.lua version ' .. M.MIN_SERVER .. ') to save from this editor'
    end

    return M.pack_stream(d, token, S.server.maxChunks)
end

-- ---------------------------------------------------------------- transport (transport.lua)
local function next_id()
    S.nonce = S.nonce + 1
    return tostring((os.time() % 100000) * 1000 + (S.nonce % 1000))
end
M.next_id = next_id

function M.enqueue(job)
    return T.enqueue(job)
end

function M.busy()
    return T.busy()
end

function M.owns_command(line)
    return T.owns(line)
end

function M.on_reply(fields)
    return T.on_reply(fields)
end

-- text_in: message = e.message_modified, original = e.message. true = hide this line
function M.text_in(message, original)
    return T.text_in(original, message)
end

local function busy_say()
    say('Wait a moment: the editor is still talking to the server.', 'warn')
    return false
end

-- ---------------------------------------------------------------- requests
-- a read request answered by item lines and an end line: GSQ|n|<kind>|...  GSQ|n|end|count
local function read_request(words, on_items, on_fail, what)
    local id = next_id()
    local items = {}
    local job
    job = {
        id = id,
        lines = { '/say !gsq ' .. words[1] .. ' ' .. id .. (words[2] and (' ' .. table.concat(words, ' ', 2)) or '') },
        on_retry = function() items = {} end,
        on_line = function(f)
            if f[3] == 'err' then
                job.error = (f[5] or f[4] or 'error')
                job.code = f[4] -- (the server's error code: callers can tell "not out" from a real problem)
                return 'fail'
            elseif f[3] == 'end' then
                -- the server counts the set / rule / mate / chk lines only (not hdr, nor prob notes; a rule sent in
                -- segments counts once). The catalog has its own, stricter check (M.parse_catalog).
                local counted = 0
                for _, it in ipairs(items) do
                    if it[3] ~= 'hdr' and it[3] ~= 'prob' and not (it[3] == 'rule' and string.match(it[5] or '', '^%d+/%d+$')
                        and not string.match(it[5], '^1/')) then
                        counted = counted + 1
                    end
                end

                if what ~= 'cat' and tonumber(f[4]) ~= counted then
                    job.error = 'the answer was incomplete'
                    return 'fail'
                end

                local okItems, why = on_items(items, f)
                if okItems == false then
                    job.error = why or 'the answer was not usable'
                    return 'fail'
                end

                return 'done'
            elseif f[3] == 'hello' or f[3] == 'pong' then
                on_items({ f })
                return 'done'
            end

            items[#items + 1] = f
            return nil
        end,
        on_fail = on_fail,
    }
    return M.enqueue(job)
end
M.read_request = read_request

function M.ping(count, gap)
    if M.busy() then
        return busy_say()
    end

    count = math.max(1, math.min(100, math.floor(tonumber(count) or 10)))
    S.pings, S.pingBase, S.pingOldGap = {}, T.stats(), nil
    if gap then
        S.pingOldGap = T.get_interval()
        T.set_interval(gap)
    end

    local function one(i)
        local job
        job = {
            id = next_id(),
            on_line = function(f, cur)
                if f[3] == 'pong' then
                    local t = now()
                    S.pings[#S.pings + 1] = { rtt = t - cur.sentAt, wall = t - cur.firstSentAt }
                    return 'done'
                end
            end,
            on_done = function()
                if i < count then
                    one(i + 1)
                else
                    M.ping_summary(count)
                end
            end,
            on_fail = function(why)
                M.ping_summary(count, why)
            end,
        }
        job.lines = { '/say !gsq ping ' .. job.id .. ' ' .. i }
        M.enqueue(job)
    end

    say(string.format('Ping: measuring %d round trips at %.2f s between lines...', count, T.get_interval()), 'warn')
    one(1)
    return true
end

function M.ping_summary(count, why)
    local n, lo, hi, sum, wall = #S.pings, math.huge, 0, 0, 0
    for _, p in ipairs(S.pings) do
        lo, hi, sum, wall = math.min(lo, p.rtt), math.max(hi, p.rtt), sum + p.rtt, wall + p.wall
    end

    local st, base = T.stats(), S.pingBase or { rejected = 0, resent = 0 }
    local refusals, resends, interval = st.rejected - base.rejected, st.resent - base.resent, st.interval
    if S.pingOldGap then
        T.set_interval(S.pingOldGap)
        S.pingOldGap = nil
    end

    if n == 0 then
        say('Ping: no answers' .. (why and (' (' .. why .. ')') or ''), false)
        return nil
    end

    local text = string.format('Ping: %d/%d answered; round trip min %.0f, avg %.0f, max %.0f ms; per request avg %.0f ms '
        .. '(with resends); refused by the game %d, sent again %d; interval %.2f s', n, count or n, lo * 1000, sum / n * 1000,
        hi * 1000, wall / n * 1000, refusals, resends, interval)
    if why then
        text = text .. ' - stopped: ' .. why
    end

    say(text, (why == nil and refusals == 0) and true or 'warn')
    return text
end

function M.refresh()
    read_request({ 'hello' }, function(items)
        local f = items[1]
        local version = tonumber(f[4]) or 1
        if version < M.MIN_SERVER then
            -- an older server sends the old catalog and cannot carry every rule form: nothing here would be safe
            S.server, S.serverWhy = false, string.format('the server has gambits_squad.lua version %d; this editor needs version %d',
                version, M.MIN_SERVER)
            say('The Squad editor needs the server update: ' .. S.serverWhy .. '.', false)
            return
        end

        S.server = { version = version, maxRules = tonumber(f[5]) or M.MAX_RULES, maxLine = tonumber(f[6]) or 120,
                     maxChunks = tonumber(f[7]) or M.MAX_CHUNKS }
        M.MAX_RULES = math.min(S.server.maxRules, 32)
        M.load_mates()
    end, function(why)
        S.server = false
        say('The Squad editor needs the server update (!gsq): ' .. why, false)
    end)
end

local function parse_mates(items)
    local mates = {}
    for _, f in ipairs(items) do
        mates[#mates + 1] = { slot = tonumber(f[4]), id = tonumber(f[5]), name = f[6], job = f[7], level = tonumber(f[8]),
                              sub = f[9] ~= '-' and f[9] or nil, chosen = tonumber(f[10]) or 0, out = f[11] == '1',
                              subLevel = tonumber(f[12] or '') } -- (version 4: the sub job's level; nil = not known)
    end

    return mates
end

-- reads the squad back (no follow-up loads): on_mates(mates)
function M.read_mates(on_mates, on_fail)
    return read_request({ 'mates' }, function(items)
        S.mates = parse_mates(items)
        on_mates(S.mates)
    end, on_fail)
end

function M.load_mates()
    M.read_mates(function()
        if S.mateSlot == nil and S.mates[1] then
            S.mateSlot = S.mates[1].slot
        end

        local m = M.mate()
        if m then
            M.load_sets(m.job)
            if S.catJob ~= M.catalog_key(m) then
                M.load_catalog_for(m)
            end
        end
    end, function(why) say('Could not load your squad: ' .. why, false) end)
end

local function mate_by_slot(mates, slot)
    for _, m in ipairs(mates) do
        if m.slot == slot then
            return m
        end
    end

    return nil
end

function M.mate()
    return mate_by_slot(S.mates, S.mateSlot)
end

local function parse_sets(items)
    local sets = {}
    for _, f in ipairs(items) do
        if f[3] == 'set' then
            sets[#sets + 1] = { num = tonumber(f[4]), job = f[5], rules = tonumber(f[6]), flags = f[7], rev = f[8], id = f[9],
                                name = f[10] or '' }
        end
    end

    return sets
end

function M.load_sets(job, done)
    S.progress = 'Loading Rule Sets...'
    read_request({ 'list', job }, function(items)
        S.sets = parse_sets(items)
        S.progress = nil
        if done then
            done(S.sets)
        end
    end, function(why)
        S.progress = nil
        say('Could not load the Rule Sets: ' .. why, false)
    end)
end

-- The catalog check, the same as gambits_squad.lua G.check (Lua 5.1 and 5.4 give the same number)
function M.check(text, h)
    h = h or 7
    for i = 1, #text do
        h = (h * 31 + string.byte(text, i)) % 1000000007
    end

    return h
end

M.CAT_KINDS  = { 't', 'c', 'f', 'j', 's' }
M.CATM_KINDS = { 't', 'c', 'f', 'j', 's', 'u' } -- (version 4, one mate's catalog: u = allowed by job and level, not confirmed)
local CAT_ENTRY = {
    t = '^[A-Z][A-Z_]*$',
    c = '^[A-Z][A-Z0-9_]*:[nrejm][:%d]*$', -- (j: a job ability argument, server version 5 when asked for with catm "j";
                                           --  m: a modifier and a number, MOD_LT, server version 6 with catm "jm")
    f = '^[A-Z][A-Z0-9_]*$',
    j = '^[A-Z][A-Z0-9_]*:%d+s?$',
    s = '^[A-Z][A-Z0-9_]*:%d+s?$',
    u = '^[A-Z][A-Z0-9_]*:%d+s?$',
}

-- Builds the catalog from the answer lines "cat|seq|kind|entries" and the end line "end|lines|t.c.f.j.s|check".
-- Every line must be there exactly once, in order, kinds in order, every entry well formed and not repeated, the counts
-- and the check equal: else nil, why (the old catalog stays, nothing is guessed).
function M.parse_catalog(items, endFields)
    local total = tonumber(endFields and endFields[4] or '')
    local counts = split(endFields and endFields[5] or '', '.')
    local wantCheck = tonumber(endFields and endFields[6] or '')
    local kinds = #counts == #M.CATM_KINDS and M.CATM_KINDS or M.CAT_KINDS
    if total == nil or #counts ~= #kinds or wantCheck == nil then
        return nil, 'the end of the list was not readable'
    end

    local bySeq = {}
    for _, f in ipairs(items) do
        local seq = tonumber(f[4] or '')
        if f[3] ~= 'cat' or seq == nil or seq < 1 or seq > total or seq ~= math.floor(seq) or #f ~= 6 then
            return nil, 'a line of the list was not readable'
        end

        if bySeq[seq] then
            return nil, 'line ' .. seq .. ' of the list came twice'
        end

        bySeq[seq] = f
    end

    local order = {}
    for i, k in ipairs(kinds) do
        order[k] = i
    end

    local lists = { t = {}, c = {}, f = {}, j = {}, s = {}, u = {} }
    local seen = { t = {}, c = {}, f = {}, j = {}, s = {}, u = {} }
    local check, lastKind = 7, 0
    for seq = 1, total do
        local f = bySeq[seq]
        if f == nil then
            return nil, 'line ' .. seq .. ' of ' .. total .. ' of the list is missing'
        end

        local kind = f[5]
        if order[kind] == nil or order[kind] < lastKind then
            return nil, 'the list came in the wrong order'
        end

        lastKind = order[kind]
        for _, entry in ipairs(split(f[6], ',')) do
            if not string.match(entry, CAT_ENTRY[kind]) then
                return nil, 'an entry of the list was cut or changed (' .. entry .. ')'
            end

            if seen[kind][entry] then
                return nil, 'an entry of the list came twice (' .. entry .. ')'
            end

            seen[kind][entry] = true
            lists[kind][#lists[kind] + 1] = entry
            check = M.check(kind .. ':' .. entry .. '\n', check)
        end
    end

    for i, k in ipairs(kinds) do
        if #lists[k] ~= tonumber(counts[i]) then
            return nil, string.format('the list has %d %s entries, the server sent %s', #lists[k], k, tostring(counts[i]))
        end
    end

    if check ~= wantCheck then
        return nil, 'the list does not match what the server sent'
    end

    -- perMate: the server's own list for one mate (catm): its abilities and spells are already exactly the mate's
    local cat = { targets = lists.t, conds = {}, condNames = {}, families = lists.f, jas = {}, spells = {}, unconfirmed = {},
                  perMate = kinds == M.CATM_KINDS }
    for _, v in ipairs(lists.c) do
        local p = split(v, ':')
        local spec = { kind = p[2], lo = tonumber(p[3]), hi = tonumber(p[4]) }
        if (spec.kind == 'r' and (spec.lo == nil or spec.hi == nil or #p ~= 4)) or (spec.kind ~= 'r' and #p ~= 2) then
            return nil, 'a condition of the list was not readable (' .. v .. ')'
        end

        cat.conds[p[1]] = spec
        cat.condNames[#cat.condNames + 1] = p[1]
    end

    for _, pair in ipairs({ { lists.j, cat.jas }, { lists.s, cat.spells }, { lists.u, cat.unconfirmed } }) do
        for _, v in ipairs(pair[1]) do
            local name, lvl, sub = v:match('^([%w_]+):(%d+)(s?)$')
            pair[2][#pair[2] + 1] = { name = name, level = tonumber(lvl), sub = sub == 's' }
        end
    end

    return cat
end

-- what the loaded catalog was made for (a new key means it must be loaded again)
function M.catalog_key(m)
    if S.server and (S.server.version or 0) >= 4 then
        return string.format('m%d:%s%d/%s%s', m.slot or 0, m.job or '?', m.level or 0, m.sub or '-', tostring(m.subLevel or '-'))
    end

    return (m.job or '?') .. (m.sub or '')
end

-- (version 4) the catalog of ONE squad mate, made by the server with the same rules a call uses; older servers: the job's
function M.load_catalog_for(m)
    if not (S.server and (S.server.version or 0) >= 4) then
        return M.load_catalog(m.job, m.sub)
    end

    local key = M.catalog_key(m)
    -- (version 5) "j": this editor reads conditions with a job ability argument (JA_ON_COOLDOWN)
    -- (version 6, job expansion) "jm": modifier arguments too (MOD_LT)
    local words = { 'catm', tostring(m.slot) }
    if (S.server.version or 0) >= 6 then
        words[3] = 'jm'
    elseif (S.server.version or 0) >= 5 then
        words[3] = 'j'
    end

    read_request(words, function(items, endFields)
        local cat, why = M.parse_catalog(items, endFields)
        if cat == nil or not cat.perMate then
            why = why or 'the list was not made for this squad mate'
            S.catError = why
            say('The choices from the server were incomplete (' .. why .. '). Press Refresh.', false)
            return false, why
        end

        S.cat, S.catJob, S.catError = cat, key, nil
        return true
    end, function(why)
        S.catError = why
        say('Could not load the choices for ' .. tostring(m.name) .. ': ' .. why, false)
    end, 'cat')
end

function M.load_catalog(job, sub)
    read_request({ 'cat', job, sub }, function(items, endFields)
        local cat, why = M.parse_catalog(items, endFields)
        if cat == nil then
            S.catError = why
            say('The choices from the server were incomplete (' .. why .. '). Press Refresh.', false)
            return false, why
        end

        S.cat, S.catJob, S.catError = cat, job .. (sub or ''), nil
        return true
    end, function(why)
        S.catError = why
        say('Could not load the choices for ' .. tostring(job) .. ': ' .. why, false)
    end, 'cat')
end

-- one set as the server has it: on_set(hdr, rule texts) - rules reassembled from their segments; every rule 1..count
-- exactly once, every segment in order ("?" stays "?")
local function fetch_set(num, on_set, on_fail)
    return read_request({ 'get', tostring(num) }, function(items, endFields)
        local hdr, parts = nil, {}
        for _, f in ipairs(items) do
            if f[3] == 'hdr' then
                hdr = { num = tonumber(f[4]), job = f[5], flags = f[6], rev = f[7], id = f[8], name = f[9] or '' }
            elseif f[3] == 'rule' then
                local i = tonumber(f[4] or '')
                local seg, segs = string.match(f[5] or '', '^(%d+)/(%d+)$')
                seg, segs = tonumber(seg), tonumber(segs)
                if i == nil or seg == nil or #f ~= 6 then
                    return false, 'a rule line was not readable'
                end

                local p = parts[i] or { segs = segs, have = {} }
                if p.segs ~= segs or p.have[seg] or seg < 1 or seg > segs then
                    return false, 'rule ' .. i .. ' came in broken pieces'
                end

                p.have[seg] = f[6]
                parts[i] = p
            end
        end

        local count, rules = tonumber(endFields and endFields[4] or ''), {}
        for i = 1, count or 0 do
            local p = parts[i]
            if p == nil then
                return false, 'rule ' .. i .. ' is missing'
            end

            local pieces = {}
            for seg = 1, p.segs do
                if p.have[seg] == nil then
                    return false, 'a piece of rule ' .. i .. ' is missing'
                end

                pieces[seg] = p.have[seg]
            end

            rules[i] = table.concat(pieces)
        end

        if hdr == nil or count == nil then
            return false, 'the Rule Set header is missing'
        end

        on_set(hdr, rules)
        return true
    end, on_fail)
end
M.fetch_set = fetch_set

-- Loads a set into the editor (as it is, or as a new copy). A rule the server could not send exactly ("?") is kept as
-- a visible, protected row: the set is then read-only, and a copy is refused (it would lose that rule).
function M.open_set(num, copy)
    S.progress = 'Loading Rule Set ' .. num .. '...'
    fetch_set(num, function(hdr, texts)
        local d = { num = 0, rev = nil, job = nil, name = '', rules = {}, flags = '', dirty = copy and true or false }
        d.num, d.job, d.flags, d.rev, d.id, d.name = hdr.num, hdr.job, hdr.flags, hdr.rev, hdr.id, hdr.name
        local opaque = {}
        for i, text in ipairs(texts) do
            local r = M.decode_rule(text)
            if r == nil then
                r = { opaque = true, text = text, on = true }
                d.uneditable = true
                opaque[#opaque + 1] = i
            end

            d.rules[i] = r
        end

        S.progress = nil
        if copy and #opaque > 0 then
            say(string.format('Not copied: rule %s uses options this editor cannot show, and a copy would lose %s. '
                .. 'Open shows the set read-only.', table.concat(opaque, ', '), #opaque == 1 and 'it' or 'them'), false)
            return
        end

        if copy or not string.find(d.flags or '', 'o', 1, true) or string.find(d.flags or '', 'r', 1, true) or d.uneditable then
            d.readonly = not copy
        end

        if copy then
            d.num, d.rev, d.id, d.flags, d.readonly = 0, nil, nil, 'o', false
            d.name = string.sub('Copy of ' .. d.name, 1, M.NAME_MAX)
        end

        local kept = S.draft ~= d and M.keep_unsaved() -- (beta polish: unsaved edits become the unsaved draft, never lost)
        S.draft, S.checks = d, {}
        say(copy and 'Copied into a new, unsaved Rule Set.' or ('Opened "' .. tostring(d.name) .. '" (Rule Set ' .. num .. ').'
            .. (kept and ' Your earlier unsaved changes are kept as the unsaved draft.' or '')
            .. (#opaque > 0 and (' Rule ' .. table.concat(opaque, ', ') .. ' uses options this editor cannot show: read-only.') or '')))
    end, function(why)
        S.progress = nil
        say('Could not load the Rule Set: ' .. why, false)
    end)
end
-- ---------------------------------------------------------------- (beta polish) opening and switching without losing edits
-- Unsaved edits are never thrown away: before another set or another mate replaces them, they become the "unsaved draft"
-- (also written to squad_draft.lua), which "Restore unsaved draft" brings back. Returns true when it kept something.
function M.keep_unsaved()
    local d = S.draft
    if d and d.dirty and not d.readonly and not d.uneditable then
        M.save_draft_file()
        S.restorable = d
        return true
    end

    return false
end

-- One click on a Rule Set: select AND open it. With unsaved edits of another set open, ask first (M.confirm_open).
function M.select_set(num)
    S.selectedSet = num
    local d = S.draft
    if d and d.num == num and not d.copy then
        return -- (already open)
    end

    if d and d.dirty and not d.readonly and not d.uneditable then
        S.confirmOpen = num
        return
    end

    S.confirmOpen = nil
    M.open_set(num, false)
    S.sel = 1
end

-- the answer to "unsaved changes": true = keep them as the unsaved draft and open the set, false = keep editing
function M.confirm_open(open)
    local num = S.confirmOpen
    S.confirmOpen = nil
    if num == nil or not open then
        return
    end

    M.keep_unsaved()
    M.open_set(num, false)
    S.sel = 1
end

-- Another squad mate: the editor shows that mate's assigned Rule Set (or nothing), never the previous mate's
function M.switch_mate(slot)
    if slot == S.mateSlot then
        return
    end

    local kept = M.keep_unsaved()
    S.mateSlot, S.selectedSet, S.draft, S.sel, S.checks, S.confirmOpen, S.confirmDelete, S.ws = slot, nil, nil, nil, {}, nil, nil, nil
    local m = M.mate()
    if m then
        M.load_sets(m.job, function()
            if m.chosen and m.chosen > 0 and S.draft == nil and S.mateSlot == m.slot then
                S.selectedSet = m.chosen
                M.open_set(m.chosen, false)
                S.sel = 1
            end
        end)
        M.load_catalog_for(m)
    end

    if kept then
        say('Your unsaved changes were kept as the unsaved draft ("Restore unsaved draft" brings them back).', 'warn')
    end
end

function M.new_set(job)
    M.keep_unsaved() -- (beta polish: earlier unsaved edits become the unsaved draft, never lost)
    S.draft = { num = 0, rev = nil, job = job, name = 'New ' .. job .. ' set', flags = 'o', dirty = true,
                rules = { { on = true, target = 'PARTY', cond = 'HPP_LT', arg = '50', kind = 'family', name = 'CURE' } } }
    S.checks = {}
    say('New Rule Set (not saved yet).')
end

-- ---------------------------------------------------------------- starter templates (Gambits WAR/PLD/RDM batch)
-- Small examples to learn the editor with: mainly the main job's own low-level abilities and spells, a few rules each.
-- One agreed exception: Basic Paladin's Provoke needs /WAR (without it that one rule is left out when the PLD is called). A template only fills a NEW, unsaved Rule Set in the editor: nothing is saved, assigned or applied, no saved
-- set is changed and the built-in job rules stay as they are. Assigned to a mate, a Rule Set replaces that mate's usual
-- job-action rules while it is assigned ("Use job rules" goes back to them).
M.TEMPLATES = {
    WAR = { {
        name = 'Basic Warrior',
        about = 'Provoke when the enemy attacks someone else and there is no tank (level 5); Defender while the WAR has the '
            .. 'enemy\'s attention (level 25), Berserk while it does not (level 15). Defender and Berserk cancel each other, so '
            .. 'the WAR switches only when the enemy\'s attention moves, and their recasts (3 and 5 minutes) keep it slow.',
        rules = {
            { on = true, target = 'TARGET', cond = 'NOT_HAS_TOP_ENMITY', cond2 = 'NOT_PT_HAS_TANK', kind = 'ja', name = 'PROVOKE' },
            { on = true, target = 'SELF', cond = 'HAS_TOP_ENMITY', cond2 = 'NOT_STATUS', arg2 = 'DEFENDER', kind = 'ja', name = 'DEFENDER' },
            { on = true, target = 'SELF', cond = 'NOT_HAS_TOP_ENMITY', cond2 = 'NOT_STATUS', arg2 = 'BERSERK', kind = 'ja', name = 'BERSERK' },
        },
    } },
    PLD = { {
        name = 'Basic Paladin',
        about = 'Shield Bash an enemy that is casting (level 15, needs a shield); Sentinel when HP is low (30); Cure the party '
            .. 'member with the lowest HP below 60 % (5, the PLD included); Provoke (only with /WAR) and Flash (37) when the '
            .. 'enemy attacks someone else; Cure itself below 75 %. Rules the PLD cannot use yet (no /WAR, too low) are left '
            .. 'out when it is called; the others still work.',
        rules = {
            { on = true, target = 'TARGET', cond = 'CASTING_MA', kind = 'ja', name = 'SHIELD_BASH' },
            { on = true, target = 'SELF', cond = 'HPP_LT', arg = '40', cond2 = 'NOT_STATUS', arg2 = 'SENTINEL', kind = 'ja', name = 'SENTINEL' },
            { on = true, target = 'PARTY_LOWEST_HPP', cond = 'HPP_LT', arg = '60', kind = 'family', name = 'CURE' },
            { on = true, target = 'TARGET', cond = 'NOT_HAS_TOP_ENMITY', kind = 'ja', name = 'PROVOKE' },
            { on = true, target = 'TARGET', cond = 'NOT_HAS_TOP_ENMITY', kind = 'spell', name = 'FLASH' },
            { on = true, target = 'SELF', cond = 'HPP_LT', arg = '75', kind = 'family', name = 'CURE' },
        },
    } },
    WHM = { {
        name = 'Basic White Mage',
        about = 'Cure the party member with the lowest HP: the best Cure below 50 %, plain Cure (cheap) below 70 % (level 1); '
            .. 'Poisona a poisoned party member (6); Protect a party member without it (7, the best Protect it knows).',
        rules = {
            { on = true, target = 'PARTY_LOWEST_HPP', cond = 'HPP_LT', arg = '50', kind = 'family', name = 'CURE' },
            { on = true, target = 'PARTY_LOWEST_HPP', cond = 'HPP_LT', arg = '70', kind = 'spell', name = 'CURE' },
            { on = true, target = 'PARTY', cond = 'STATUS', arg = 'POISON', kind = 'spell', name = 'POISONA' },
            { on = true, target = 'PARTY', cond = 'NOT_STATUS', arg = 'PROTECT', kind = 'family', name = 'PROTECT' },
        },
    } },
    RDM = { {
        name = 'Basic Red Mage',
        about = 'Cure the party member with the lowest HP when below half (level 3), Dia on an enemy without it (level 1), '
            .. 'Paralyze on an enemy without it, then wait 30 s (level 6).',
        rules = {
            { on = true, target = 'PARTY_LOWEST_HPP', cond = 'HPP_LT', arg = '50', kind = 'family', name = 'CURE' },
            { on = true, target = 'TARGET', cond = 'NOT_STATUS', arg = 'DIA', kind = 'family', name = 'DIA' },
            { on = true, target = 'TARGET', cond = 'NOT_STATUS', arg = 'PARALYSIS', kind = 'family', name = 'PARALYZE', retry = '30' },
        },
    } },

    -- ------------------------------------------------------------ (job expansion 2026-11-21) the other jobs
    -- Levels from sql/abilities.sql and sql/spell_list.sql (v0.1.55); test_gambits_jobexp.lua checks every name and level
    -- against the server's tables. Rules a mate cannot use yet (level, sub job, expansion switched off) are left out by
    -- the server when it is called; the others still work.
    MNK = { {
        name = 'Basic Monk',
        about = 'Chakra when HP is below 40 % (level 35); Dodge while the MNK has the enemy\'s attention (15); Focus when it '
            .. 'is not on (25); Boost while it has not got the enemy\'s attention, at most every 30 s (5).',
        rules = {
            { on = true, target = 'SELF', cond = 'HPP_LT', arg = '40', kind = 'ja', name = 'CHAKRA' },
            { on = true, target = 'SELF', cond = 'HAS_TOP_ENMITY', cond2 = 'NOT_STATUS', arg2 = 'DODGE', kind = 'ja', name = 'DODGE' },
            { on = true, target = 'SELF', cond = 'NOT_STATUS', arg = 'FOCUS', kind = 'ja', name = 'FOCUS' },
            { on = true, target = 'SELF', cond = 'NOT_HAS_TOP_ENMITY', cond2 = 'NOT_STATUS', arg2 = 'BOOST', kind = 'ja', name = 'BOOST',
              retry = '30' },
        },
    } },
    BLM = { {
        name = 'Basic Black Mage',
        about = 'Magic burst: when a skillchain opens a burst window, the best spell that fits it (element, the enemy\'s '
            .. 'resistance, MP, recast, a cast that ends in time). Aspir the enemy when MP is below 30 % (level 25); Bio an '
            .. 'enemy without it (10, every 60 s at most); else nuke with the element the enemy is weakest to while MP is at '
            .. 'least 50 % and the BLM does not have the enemy\'s attention.',
        rules = {
            { on = true, target = 'TARGET', cond = 'MB_AVAILABLE', kind = 'burst' },
            { on = true, target = 'TRIGGER_SELF_ACTION_TARGET', cond = 'MPP_LT', arg = '30', kind = 'spell', name = 'ASPIR' },
            { on = true, target = 'TARGET', cond = 'NOT_STATUS', arg = 'BIO', kind = 'family', name = 'BIO', retry = '60' },
            { on = true, target = 'TRIGGER_SELF_ACTION_TARGET', cond = 'MPP_GTE', arg = '50', cond2 = 'NOT_HAS_TOP_ENMITY', kind = 'nuke' },
        },
    } },
    THF = { {
        name = 'Basic Thief',
        about = 'Sneak Attack (level 15) and Trick Attack (30) whenever they are ready: the squad moves the THF behind the '
            .. 'enemy (Sneak Attack) or behind the tank (Trick Attack) first, and gives up after 8 s (then waits 10 s). Steal '
            .. 'from the enemy (5). The weapon skill does not wait for them.',
        rules = {
            { on = true, target = 'SELF', cond = 'NOT_STATUS', arg = 'SNEAK_ATTACK', kind = 'ja', name = 'SNEAK_ATTACK' },
            { on = true, target = 'SELF', cond = 'NOT_STATUS', arg = 'TRICK_ATTACK', kind = 'ja', name = 'TRICK_ATTACK' },
            { on = true, target = 'TARGET', cond = 'ALWAYS', kind = 'ja', name = 'STEAL' },
        },
    }, {
        name = 'Thief SATA Weapon Skill',
        about = 'Sneak Attack (level 15) and Trick Attack (30) once the THF has 1000 TP, for the weapon skill: the weapon '
            .. 'skill waits up to 8 s for the THF to get into place (never at 3000 TP, never while it has the enemy\'s '
            .. 'attention, never when it could close a skillchain). Steal from the enemy (5).',
        rules = {
            { on = true, target = 'SELF', cond = 'TP_GTE', arg = '1000', cond2 = 'NOT_STATUS', arg2 = 'SNEAK_ATTACK', kind = 'ja',
              name = 'SNEAK_ATTACK' },
            { on = true, target = 'SELF', cond = 'TP_GTE', arg = '1000', cond2 = 'NOT_STATUS', arg2 = 'TRICK_ATTACK', kind = 'ja',
              name = 'TRICK_ATTACK' },
            { on = true, target = 'TARGET', cond = 'ALWAYS', kind = 'ja', name = 'STEAL' },
        },
    } },
    DRK = { {
        name = 'Basic Dark Knight',
        about = 'Stun an enemy that is casting (level 37, Rise of the Zilart); Drain the enemy when HP is below 50 % (10) '
            .. 'and Aspir it when MP is below 30 % (20) - checked on the DRK, cast on the enemy; Last Resort while the DRK '
            .. 'does not have the enemy\'s attention (15); Bio an enemy without it (15, every 60 s at most).',
        rules = {
            { on = true, target = 'TARGET', cond = 'CASTING_MA', kind = 'spell', name = 'STUN' },
            { on = true, target = 'TRIGGER_SELF_ACTION_TARGET', cond = 'HPP_LT', arg = '50', kind = 'spell', name = 'DRAIN' },
            { on = true, target = 'TRIGGER_SELF_ACTION_TARGET', cond = 'MPP_LT', arg = '30', kind = 'spell', name = 'ASPIR' },
            { on = true, target = 'SELF', cond = 'NOT_HAS_TOP_ENMITY', cond2 = 'NOT_STATUS', arg2 = 'LAST_RESORT', kind = 'ja',
              name = 'LAST_RESORT' },
            { on = true, target = 'TARGET', cond = 'NOT_STATUS', arg = 'BIO', kind = 'family', name = 'BIO', retry = '60' },
        },
    } },
    BST = { {
        name = 'Basic Beastmaster',
        about = 'The jug pet is the squad\'s: called by level, it fights what the BST fights and is tended below 50 % HP. '
            .. 'These rules are for the BST itself and depend on its sub job: Cure itself below 50 % (/WHM or /RDM), '
            .. 'Berserk while it does not have the enemy\'s attention (/WAR 15). Without such a sub job they are left out.',
        rules = {
            { on = true, target = 'SELF', cond = 'HPP_LT', arg = '50', kind = 'family', name = 'CURE' },
            { on = true, target = 'SELF', cond = 'NOT_HAS_TOP_ENMITY', cond2 = 'NOT_STATUS', arg2 = 'BERSERK', kind = 'ja', name = 'BERSERK' },
        },
    } },
    BRD = { {
        name = 'Basic Bard',
        about = 'Songs by party role (each song reaches only that role; you can change who is what with !squad partyrole): '
            .. 'Valor Minuet (level 3) and March (29) for the melee, Mage\'s Ballad (25) for the mages, Knight\'s Minne (1) '
            .. 'for the tank. Elegy (39) on an enemy without it, Foe Requiem (7) every 60 s at most. A Bard gives at most '
            .. 'two songs to one member: a third replaces the oldest.',
        rules = {
            { on = true, target = 'MELEE', cond = 'NOT_STATUS', arg = 'MINUET', kind = 'family', name = 'VALOR_MINUET' },
            { on = true, target = 'MELEE', cond = 'NOT_STATUS', arg = 'MARCH', kind = 'family', name = 'MARCH' },
            { on = true, target = 'CASTER', cond = 'NOT_STATUS', arg = 'BALLAD', kind = 'family', name = 'MAGES_BALLAD' },
            { on = true, target = 'TANK', cond = 'NOT_STATUS', arg = 'MINNE', kind = 'family', name = 'KNIGHTS_MINNE' },
            { on = true, target = 'TARGET', cond = 'NOT_STATUS', arg = 'ELEGY', kind = 'family', name = 'ELEGY' },
            { on = true, target = 'TARGET', cond = 'NOT_STATUS', arg = 'REQUIEM', kind = 'family', name = 'FOE_REQUIEM', retry = '60' },
        },
    } },
    RNG = { {
        name = 'Basic Ranger',
        about = 'Sharpshot (level 1) and Barrage (30) while the RNG does not have the enemy\'s attention, then ranged attacks. '
            .. 'A Rule Set replaces the squad\'s automatic ranged attacks, so the ranged attack rule must stay in it.',
        rules = {
            { on = true, target = 'SELF', cond = 'NOT_HAS_TOP_ENMITY', cond2 = 'NOT_STATUS', arg2 = 'SHARPSHOT', kind = 'ja', name = 'SHARPSHOT' },
            { on = true, target = 'SELF', cond = 'NOT_HAS_TOP_ENMITY', cond2 = 'NOT_STATUS', arg2 = 'BARRAGE', kind = 'ja', name = 'BARRAGE' },
            { on = true, target = 'TARGET', cond = 'ALWAYS', kind = 'ranged' },
        },
    } },
    SAM = { {
        name = 'Basic Samurai',
        about = 'Hasso while the SAM does not have the enemy\'s attention (level 25), Seigan and Third Eye while it has '
            .. '(35 and 15); Meditate below 1000 TP (30) for the next weapon skill (the squad\'s weapon skill settings decide '
            .. 'which one). Hasso and Seigan cancel each other.',
        rules = {
            { on = true, target = 'SELF', cond = 'NOT_HAS_TOP_ENMITY', cond2 = 'NOT_STATUS', arg2 = 'HASSO', kind = 'ja', name = 'HASSO' },
            { on = true, target = 'SELF', cond = 'HAS_TOP_ENMITY', cond2 = 'NOT_STATUS', arg2 = 'SEIGAN', kind = 'ja', name = 'SEIGAN' },
            { on = true, target = 'SELF', cond = 'HAS_TOP_ENMITY', cond2 = 'NOT_STATUS', arg2 = 'THIRD_EYE', kind = 'ja', name = 'THIRD_EYE' },
            { on = true, target = 'SELF', cond = 'TP_LT', arg = '1000', kind = 'ja', name = 'MEDITATE' },
        },
    } },
    NIN = { {
        name = 'Basic Ninja',
        about = 'Utsusemi: Ni (level 37) when fewer than 2 shadows are left, Ichi (12) when none are left. Kurayami (19) '
            .. 'and Hojo (23) on an enemy without Blind or Slow, every 60 s at most. Provoke (with /WAR) is switched off: '
            .. 'switch it on when this NIN tanks.',
        rules = {
            { on = true, target = 'SELF', cond = 'MOD_LT', arg = 'UTSUSEMI.2', kind = 'spell', name = 'UTSUSEMI_NI' },
            { on = true, target = 'SELF', cond = 'MOD_LT', arg = 'UTSUSEMI.1', kind = 'spell', name = 'UTSUSEMI_ICHI' },
            { on = false, target = 'TARGET', cond = 'NOT_HAS_TOP_ENMITY', kind = 'ja', name = 'PROVOKE' },
            { on = true, target = 'TARGET', cond = 'NOT_STATUS', arg = 'BLINDNESS', kind = 'spell', name = 'KURAYAMI_ICHI', retry = '60' },
            { on = true, target = 'TARGET', cond = 'NOT_STATUS', arg = 'SLOW', kind = 'spell', name = 'HOJO_ICHI', retry = '60' },
        },
    } },
    DRG = { {
        name = 'Basic Dragoon',
        about = 'High Jump while the DRG has the enemy\'s attention (level 35, it sheds some), Jump (10) and High Jump '
            .. 'below 1000 TP for TP - checked on the DRG, used on the enemy. The wyvern is the squad\'s: Spirit Link (25) '
            .. 'gives it HP when it is badly hurt, unless this Rule Set uses Spirit Link itself.',
        rules = {
            { on = true, target = 'TRIGGER_SELF_ACTION_TARGET', cond = 'HAS_TOP_ENMITY', kind = 'ja', name = 'HIGH_JUMP' },
            { on = true, target = 'TRIGGER_SELF_ACTION_TARGET', cond = 'TP_LT', arg = '1000', kind = 'ja', name = 'JUMP' },
            { on = true, target = 'TRIGGER_SELF_ACTION_TARGET', cond = 'TP_LT', arg = '1000', kind = 'ja', name = 'HIGH_JUMP' },
        },
    } },
    BLU = { {
        name = 'Basic Blue Mage',
        about = 'Healing Breeze below 40 % HP (level 16), Pollen below 60 % (1); Cocoon (8), Metallic Body (8) and '
            .. 'Refueling (48) when they are not on; Head Butt an enemy that is casting (12). The squad\'s blue magic rules '
            .. 'decide which spells a BLU has.',
        rules = {
            { on = true, target = 'SELF', cond = 'HPP_LT', arg = '40', kind = 'spell', name = 'HEALING_BREEZE' },
            { on = true, target = 'SELF', cond = 'HPP_LT', arg = '60', kind = 'spell', name = 'POLLEN' },
            { on = true, target = 'TARGET', cond = 'CASTING_MA', kind = 'spell', name = 'HEAD_BUTT' },
            { on = true, target = 'SELF', cond = 'NOT_STATUS', arg = 'DEFENSE_BOOST', kind = 'spell', name = 'COCOON' },
            { on = true, target = 'SELF', cond = 'NOT_STATUS', arg = 'STONESKIN', kind = 'spell', name = 'METALLIC_BODY' },
            { on = true, target = 'SELF', cond = 'NOT_STATUS', arg = 'HASTE', kind = 'spell', name = 'REFUELING' },
        },
    } },
    COR = { {
        name = 'Basic Corsair',
        about = 'Two rolls for the party: Chaos Roll (level 14, attack) and Hunter\'s Roll (11, accuracy) when they are not '
            .. 'on, then ranged attacks. Double-Up is not used. A Rule Set replaces the squad\'s automatic ranged attacks, so '
            .. 'the ranged attack rule must stay in it.',
        rules = {
            { on = true, target = 'SELF', cond = 'NOT_STATUS', arg = 'CHAOS_ROLL', kind = 'ja', name = 'CHAOS_ROLL' },
            { on = true, target = 'SELF', cond = 'NOT_STATUS', arg = 'HUNTERS_ROLL', kind = 'ja', name = 'HUNTERS_ROLL' },
            { on = true, target = 'TARGET', cond = 'ALWAYS', kind = 'ranged' },
        },
    } },
}
-- (job expansion) no Summoner template: an avatar is the squad's (called by level, Blood Pacts on its own); a Rule Set
-- has no pet target to give it orders. PUP is not covered yet.

function M.templates_for(job)
    return M.TEMPLATES[job or ''] or {}
end

-- A new, unsaved Rule Set from a template (a copy: the template itself never changes). A target the server does not offer
-- (an older server without PARTY_LOWEST_HPP) becomes PARTY; a rule with another target or condition it does not offer
-- is left out. Returns the draft, or nil + why.
function M.new_from_template(job, index, cat)
    local t = M.templates_for(job)[index or 1]
    if t == nil then
        return nil, 'no template for ' .. tostring(job)
    end

    local offered = {}
    for _, target in ipairs(cat and cat.targets or {}) do
        offered[target] = true
    end

    -- (job expansion) a rule whose target or condition this server does not offer at all (an older server: no
    -- "Check Self -> Act on Enemy", no shadow count) is left out of the copy; Party member, lowest HP becomes Party member
    local function usable(copy)
        if cat and not offered[copy.target] then
            if copy.target ~= 'PARTY_LOWEST_HPP' then
                return false
            end

            copy.target = 'PARTY'
        end

        for _, c in ipairs({ copy.cond, copy.cond2 }) do
            if cat and cat.conds and cat.conds[c] == nil then
                return false
            end
        end

        return true
    end

    local rules, skipped = {}, 0
    for _, r in ipairs(t.rules) do
        local copy = {}
        for k, v in pairs(r) do
            copy[k] = v
        end

        if usable(copy) then
            rules[#rules + 1] = copy
        else
            skipped = skipped + 1
        end
    end

    if #rules == 0 then
        return nil, 'this server cannot use the template "' .. t.name .. '" (update the server)'
    end

    M.keep_unsaved() -- (beta polish: earlier unsaved edits become the unsaved draft, never lost)
    S.draft = { num = 0, rev = nil, job = job, name = t.name, flags = 'o', dirty = true, rules = rules, template = t.name }
    S.checks = {}
    say(string.format('"%s" loaded as a new Rule Set (not saved). Change it as you like, then Save; assigning it replaces '
        .. 'the mate\'s usual job rules while it is assigned.%s', t.name,
        skipped > 0 and string.format(' %d rule(s) left out: this server does not offer them yet.', skipped) or ''), skipped > 0 and 'warn' or nil)
    return S.draft
end

local function encodings(rules)
    local out = {}
    for i, r in ipairs(rules) do
        out[i] = M.encode_rule(r)
    end

    return out
end

local function same_list(a, b)
    if #a ~= #b then
        return false
    end

    for i = 1, #a do
        if a[i] ~= b[i] then
            return false
        end
    end

    return true
end

-- the server's rule texts in the editor's own encoding (so the comparison does not depend on spelling details)
local function normal(texts)
    local out = {}
    for i, text in ipairs(texts) do
        local r = M.decode_rule(text)
        out[i] = r and M.encode_rule(r) or ('?' .. tostring(text))
    end

    return out
end

-- the draft as it was when Save was pressed
local function snapshot(d)
    local known = {}
    for _, set in ipairs(S.sets) do
        known[set.num] = true
    end

    return { num = d.num or 0, job = d.job, name = d.name, rules = encodings(d.rules), known = known }
end

-- the server has (or wrote) the snapshot as set num: update the draft
local function saved(d, snap, num, rev, id)
    d.num, d.rev, d.id, d.flags = num, rev, id, 'o'
    d.dirty = not same_list(encodings(d.rules), snap.rules) or d.name ~= snap.name
    if not d.dirty then
        M.delete_draft_file()
    end

    local m = M.mate()
    if m then
        M.load_sets(m.job)
    end
end

-- The outcome of a save is not known (no answer, a zone change, the server lost the unfinished save, or "stale"):
-- read the set list back and decide from what the server has. Never writes.
function M.verify_save(d, snap, why)
    S.progress = 'Not sure the save went through (' .. why .. '): checking on the server...'
    local function unresolved(w)
        S.progress = nil
        M.save_draft_file()
        say('Save NOT confirmed: ' .. why .. '; the check failed too (' .. tostring(w) .. '). Your rows are kept. '
            .. 'Press Refresh and look at the list before you save again.', 'warn')
    end

    read_request({ 'list', snap.job }, function(items)
        local cands = {}
        for _, set in ipairs(parse_sets(items)) do
            if snap.num > 0 then
                if set.num == snap.num then
                    cands[#cands + 1] = set.num
                end
            elseif not snap.known[set.num] and set.name == snap.name and set.rules == #snap.rules
                and string.find(set.flags or '', 'o', 1, true) then
                cands[#cands + 1] = set.num
            end
        end

        table.sort(cands, function(a, b) return a > b end)
        local function try(i)
            if cands[i] == nil then
                S.progress = nil
                M.save_draft_file()
                say('Not saved (checked on the server: ' .. why .. '). Your rows are kept; press Save to try again.', false)
                return
            end

            fetch_set(cands[i], function(hdr, texts)
                if hdr and hdr.name == snap.name and same_list(normal(texts), snap.rules) then
                    S.progress = nil
                    saved(d, snap, hdr.num, hdr.rev, hdr.id)
                    say(string.format('Saved as Rule Set %d (confirmed by reading it back from the server).', hdr.num))
                else
                    try(i + 1)
                end
            end, unresolved)
        end

        try(1)
    end, unresolved)
end

function M.save()
    if M.busy() then
        return busy_say()
    end

    local d = S.draft
    local why = M.check_draft(d, S.cat)
    if why then
        say('Not saved: ' .. why, false)
        return false
    end

    if d.readonly then
        say('This Rule Set cannot be changed here. Use Copy to make your own.', false)
        return false
    end

    local token = next_id()
    local lines, perr = M.pack(d, token)
    if not lines then
        say('Not saved: ' .. perr, false)
        return false
    end

    local snap = snapshot(d)
    local job
    job = {
        id = token, lines = lines,
        on_line = function(f, cur)
            if f[3] == 'ack' then
                if tonumber(f[4]) ~= cur.index then
                    return nil -- an answer to an earlier copy of another part: ignore it
                end

                if cur.index == #lines and #lines > 1 then
                    job.lost = true -- the last part, only acknowledged: the server lost the earlier parts
                    job.error = 'the server lost the unfinished save'
                    return 'fail'
                end

                S.progress = string.format('Saving... %s/%d', f[4], #lines)
                return 'next'
            elseif f[3] == 'ok' then
                job.result = { tonumber(f[4]), f[5], f[6] }
                return 'done'
            elseif f[3] == 'err' then
                job.code = f[4]
                job.error = f[5] or f[4] or 'error'
                return 'fail'
            end
        end,
        on_done = function()
            S.progress = nil
            saved(d, snap, job.result[1], job.result[2], job.result[3])
            say(string.format('Saved as Rule Set %d (server confirmed). Assign & Apply puts it to use (also for a mate that already '
                .. 'uses it).', job.result[1]))
        end,
        on_fail = function(failWhy, kind)
            if kind == 'unknown' or job.lost or job.code == 'stale' then
                M.verify_save(d, snap, failWhy) -- it may have been written: look before saying anything
                return
            end

            S.progress = nil
            M.save_draft_file()
            say('Not saved: ' .. failWhy .. '. Your rows are kept.', false)
        end,
    }
    S.progress = string.format('Saving... 0/%d', #lines)
    return M.enqueue(job)
end

function M.delete_set(num, rev)
    if M.busy() then
        return busy_say()
    end

    local token = next_id()
    local job
    local function deleted()
        say('Rule Set ' .. num .. ' deleted (server confirmed). A mate that used it goes back to its job rules.')
        if S.draft and S.draft.num == num then
            S.draft = nil
        end

        local m = M.mate()
        if m then
            M.load_sets(m.job)
        end
    end

    job = {
        id = token, lines = { string.format('/say !gsq del %s %d %s', token, num, rev or '-') },
        on_line = function(f)
            if f[3] == 'ok' then
                return 'done'
            elseif f[3] == 'err' then
                job.error = f[5] or f[4]
                return 'fail'
            end
        end,
        on_done = deleted,
        on_fail = function(why, kind)
            if kind ~= 'unknown' then
                say('Not deleted: ' .. why, false)
                return
            end

            local job2 = S.sets[1] and S.sets[1].job or (M.mate() and M.mate().job)
            S.progress = 'Not sure the delete went through: checking on the server...'
            read_request({ 'list', job2 }, function(items)
                S.progress = nil
                for _, set in ipairs(parse_sets(items)) do
                    if set.num == num then
                        say('Not deleted (checked on the server: ' .. why .. ').', false)
                        return
                    end
                end

                deleted()
            end, function(w)
                S.progress = nil
                say('Delete NOT confirmed: ' .. why .. '; the check failed too (' .. tostring(w) .. '). Press Refresh.', 'warn')
            end)
        end,
    }
    return M.enqueue(job)
end

function M.check_set(slot, num)
    S.checks = {}
    read_request({ 'chk', tostring(slot), tostring(num) }, function(items, endFields)
        for _, f in ipairs(items) do
            if f[3] == 'chk' then
                S.checks[tonumber(f[4]) or 0] = f[5]
            end
        end

        local n = 0
        for _ in pairs(S.checks) do
            n = n + 1
        end

        -- (version 4) the levels it was checked at: the summoned mate's current ones, Level Sync included
        local m = M.mate()
        local at = ''
        local lvl, sub, subLvl = tonumber(endFields and endFields[5] or ''), endFields and endFields[6], tonumber(endFields and endFields[7] or '')
        if lvl then
            at = string.format(' (checked at %s\'s current level: %s %d%s%s)', m and m.name or 'the mate', m and m.job or '', lvl,
                (sub and sub ~= '-') and string.format(' / %s %d', sub, subLvl or 0) or '',
                (m and m.level and lvl < m.level) and ', Level Sync' or '')
        end

        say((n == 0 and 'Check: the mate can use every rule now.' or ('Check: ' .. n .. ' rule(s) left out for this mate now (see the rows).')) .. at)
    end, function(why, kind, job)
        if job and job.code == 'notout' then
            -- the server checks with the mate's current levels and sub job, so it must be summoned; the set was not judged
            local m = M.mate()
            local who = m and m.name or 'the squad mate'
            say(string.format('Summon %s before checking this Rule Set. (Check uses %s\'s current level and sub job; '
                .. 'this is not a problem in the set.)', who, who), 'warn')
            return
        end

        say('Check: ' .. why, false)
    end)
end

-- (beta polish) the name of a Rule Set by its number, from the server's list for the mate's job (S.sets, read with
-- "list"); "Rule Set #n" when it is not in that list (another job's set, not loaded yet)
function M.set_label(num)
    if num == nil or num == 0 then
        return 'default job rules'
    end

    for _, set in ipairs(S.sets or {}) do
        if set.num == num and set.name and set.name ~= '' then
            return set.name
        end
    end

    return 'Rule Set #' .. tostring(num)
end

-- Assign: "!squad ruleset <slot> <num|off>" (no GSQ answer; setting a value twice is harmless), confirmed only by
-- reading the mate's chosen set back from the server. thenApply (beta polish, "Assign & Apply" / "Restore default job
-- rules"): once confirmed, and only when the mate is summoned, the existing Apply (!squad reapply) runs by itself.
function M.assign(slot, num, thenApply)
    if M.busy() then
        return busy_say()
    end

    local want, rounds = num or 0, 0
    local what = num and M.set_label(num) or 'its default job rules'
    local assign_round
    local function readback()
        S.progress = 'Assigning: reading it back from the server...'
        M.read_mates(function(mates)
            local m = mate_by_slot(mates, slot)
            if m and m.chosen == want then
                S.progress = nil
                if thenApply and m.out then
                    S.pendingApply = true -- (M.tick starts Apply once the queue is free)
                    say(string.format('%s now uses %s (server confirmed). Applying...', m.name, what))
                elseif thenApply then
                    say(string.format('%s now uses %s (server confirmed). %s is not summoned: it applies when called.', m.name, what, m.name))
                else
                    say(string.format('%s now uses %s (server confirmed). It applies when %s is called again.', m.name, what, m.name))
                end
            elseif rounds < 2 then
                assign_round()
            else
                S.progress = nil
                say(string.format('Not assigned: the server still shows %s for slot %d.', m and (m.chosen > 0 and ('Rule Set ' .. m.chosen)
                    or 'the job rules') or 'no mate', slot), false)
            end
        end, function(why)
            S.progress = nil
            say('Assign NOT confirmed: ' .. why .. '. Press Refresh to see what the mate uses.', 'warn')
        end)
    end

    assign_round = function()
        rounds = rounds + 1
        S.progress = 'Assigning ' .. what .. '...'
        M.enqueue({
            id = 'assign', noreply = true, idempotent = true,
            lines = { string.format('/say !squad ruleset %d %s', slot, num and tostring(num) or 'off') },
            on_done = readback,
            on_fail = function(why, kind)
                if kind == 'unknown' then
                    readback() -- the server may have it anyway: look
                else
                    S.progress = nil
                    say('Not assigned: ' .. why, false)
                end
            end,
        })
    end

    assign_round()
    return true
end

-- (beta polish) Assign & Apply: the selected SAVED Rule Set. An unsaved edit of that same set is not what would be
-- assigned, so it is refused with a message instead of being saved or ignored silently.
function M.assign_apply(slot, num)
    local d = S.draft
    if num ~= nil and d and d.dirty and not d.readonly and d.num == num then
        say(string.format('%s has unsaved changes. Save first: Assign & Apply uses the saved Rule Set.', M.set_label(num)), 'warn')
        return false
    end

    return M.assign(slot, num, true)
end

-- Apply: "!squad reapply" sends the mates that are out away and calls them again (it must not run twice, so it is sent
-- again only when the game client refused it). Confirmed by reading back that they left and came back.
function M.apply()
    if M.busy() then
        return busy_say()
    end

    S.progress = 'Applying: checking which mates are out...'
    M.read_mates(function(mates)
        local out = {}
        for _, m in ipairs(mates) do
            if m.out then
                out[#out + 1] = m
            end
        end

        if #out == 0 then
            S.progress = nil
            say('No squad mate is out. Call one first; the assignment applies when it is called.', false)
            return
        end

        S.progress = 'Applying: sending the squad off...'
        M.enqueue({
            id = 'apply', noreply = true, idempotent = false, lines = { '/say !squad reapply' },
            on_done = function()
                local t = now()
                S.apply = { phase = 1, at = t + 1.0, out = out, sentAt = t, tries = 0,
                            back = t + M.APPLY_RECALL + M.APPLY_GAP * (#out - 1) + 2.0 }
            end,
            on_fail = function(why, kind)
                S.progress = nil
                if kind == 'rejected' then
                    say('Not applied: ' .. why .. '.', false)
                else
                    say('Apply NOT confirmed: ' .. why .. '. Press Refresh to see where your mates are before you try again.', 'warn')
                end
            end,
        })
    end, function(why)
        S.progress = nil
        say('Not applied: could not read your squad (' .. why .. ').', false)
    end)
    return true
end

local function names(list)
    local out = {}
    for _, m in ipairs(list) do
        out[#out + 1] = m.name
    end

    return table.concat(out, ', ')
end

-- the two Apply read-backs (sent off, then back); run from M.tick
local function apply_tick()
    local a = S.apply
    if a == nil or a.reading or now() < a.at or T.busy() then
        return
    end

    a.reading = true
    M.read_mates(function(mates)
        a.reading = false
        local still, missing = {}, {}
        for _, m in ipairs(a.out) do
            local cur = mate_by_slot(mates, m.slot)
            if cur and cur.out then
                still[#still + 1] = m
            else
                missing[#missing + 1] = m
            end
        end

        if a.phase == 1 then
            if #still == 0 then
                a.phase, a.at = 2, a.back
                S.progress = 'Applying: calling ' .. names(a.out) .. ' again...'
            else
                S.apply, S.progress = nil, nil
                say('Apply NOT confirmed: ' .. names(still) .. ' did not leave. Press Refresh before you try again.', 'warn')
            end
        elseif #missing == 0 then
            S.apply, S.progress = nil, nil
            say('Applied: ' .. names(a.out) .. ' called again with the chosen Rule Sets (server confirmed).')
        elseif a.tries < 2 then
            a.tries, a.at = a.tries + 1, now() + 3.0
        else
            S.apply, S.progress = nil, nil
            say('Apply NOT confirmed: ' .. names(missing) .. ' sent off but not back yet. Press Refresh in a moment.', 'warn')
        end
    end, function(why)
        S.apply, S.progress = nil, nil
        say('Apply NOT confirmed: ' .. why .. '. Press Refresh.', 'warn')
    end)
end

function M.tick()
    T.tick()
    apply_tick()
    if S.pendingApply and not T.busy() and S.apply == nil then
        S.pendingApply = nil
        M.apply()
    end
end

-- ---------------------------------------------------------------- weapon skill settings (server version 5, squad_ws.lua)
-- Per squad mate and main job, separate from Rule Sets. Save stores (server confirmed), Apply puts the stored setting on
-- the called mate now, Reset stores "Squad default" (the automatic skillchains; the stored choices are kept for later).
M.WS_MODES = { 'Open', 'Close', 'Open + Close', 'Independent' }
M.WS_MODE_HELP = {
    'Opens skillchains: uses its weapon skill at your TP threshold, but only when another party member (you included) has '
        .. '1000 TP to close it, and never over a skillchain that is already going. It does not close.',
    'Closes skillchains: waits for an open skillchain and closes it from 1000 TP with a weapon skill that chains. '
        .. 'No threshold.',
    'Both: closes an open skillchain from 1000 TP; otherwise opens like Open, at your TP threshold.',
    'On its own: uses its weapon skill at your TP threshold without waiting for anyone. When a skillchain is open it '
        .. 'closes it if it can.',
}
M.WS_TPS = { 1000, 1500, 2000, 3000 }
M.WS_BEST_HELP = 'Best available: when a skillchain is open, the weapon skill that forms the best chain; otherwise the last '
    .. 'one of the mate\'s list (the server\'s order). It is not a damage calculation.'
M.WS_3000_HELP = 'At 3000 TP the mate always uses a weapon skill (in every mode), so TP is never held for ever.'

function M.ws_supported()
    return S.server and (S.server.version or 0) >= 5 or false
end

-- GSQ|n|ws|slot|JOB|src|ctl|mode|tp|ws|ltp|lws|out|usable|applied|eng
function M.parse_ws(f)
    if f == nil or f[3] ~= 'ws' or #f < 16 then
        return nil
    end

    local function tri(v) -- '1' true, '0' false, anything else nil (not known)
        if v == '1' then
            return true
        elseif v == '0' then
            return false
        end

        return nil
    end

    local d = { slot = tonumber(f[4]), job = f[5], source = f[6], control = tonumber(f[7]), mode = tonumber(f[8]),
                tp = tonumber(f[9]), ws = tonumber(f[10]), legacyTp = tonumber(f[11]) or 0, legacyWs = tonumber(f[12]) or 0,
                out = f[13] == '1', usable = tri(f[14]), applied = tri(f[15]), engine = f[16] == '1' }
    if d.slot == nil or d.mode == nil or d.tp == nil or d.ws == nil or (d.source ~= 'c' and d.source ~= 'd' and d.source ~= 'l') then
        return nil
    end

    return d
end

-- wsl lines "id:Name,..." -> { { id, name, label } ... } in the server's order, or nil + why
function M.parse_wsl(items)
    local list, seen = {}, {}
    for _, f in ipairs(items) do
        if f[3] ~= 'wsl' then
            return nil, 'a line of the weapon skill list was not readable'
        end

        for _, entry in ipairs(split(f[4] or '', ',')) do
            local id, name = string.match(entry, '^(%d+):([%w_]+)$')
            if id == nil or seen[id] then
                return nil, 'the weapon skill list was cut or changed (' .. entry .. ')'
            end

            seen[id] = true
            list[#list + 1] = { id = tonumber(id), name = name, label = (name:gsub('_', ' ')) }
        end
    end

    return list
end

-- the editable copy of a stored setting (Custom only when the server says Custom is in use)
local function ws_edit_from(d)
    return { control = d.source == 'c' and 1 or 0, mode = d.mode, tp = d.tp, ws = d.ws }
end
M.ws_edit_from = ws_edit_from

function M.ws_dirty()
    local w = S.ws
    if not (w and w.data and w.edit) then
        return false
    end

    local saved = ws_edit_from(w.data)
    return w.data.source == 'l' or saved.control ~= w.edit.control or saved.mode ~= w.edit.mode or saved.tp ~= w.edit.tp
        or saved.ws ~= w.edit.ws
end

function M.ws_name(id)
    if id == nil or id == 0 then
        return 'Best available'
    end

    return (S.wsNames and S.wsNames[id]) or ('weapon skill ' .. id)
end

local function ws_got(slot, items, keepEdit)
    local d = M.parse_ws(items[1])
    if d == nil or d.slot ~= slot then
        return false, 'the answer was not readable'
    end

    S.ws = S.ws and S.ws.slot == slot and S.ws or { slot = slot }
    S.ws.data = d
    if not keepEdit or S.ws.edit == nil then
        S.ws.edit = ws_edit_from(d)
    end

    return true, d
end

function M.ws_load(slot)
    S.ws = { slot = slot, loading = true }
    read_request({ 'wsg', tostring(slot) }, function(items)
        local ok, d = ws_got(slot, items)
        if not ok then
            return false, d
        end

        S.ws.loading = false
        if d.out then
            M.ws_list(slot)
        end

        return true
    end, function(why)
        S.ws = { slot = slot, error = why }
        say('Could not load the weapon skill settings: ' .. why, false)
    end)
end

function M.ws_list(slot)
    read_request({ 'wsl', tostring(slot) }, function(items)
        local list, why = M.parse_wsl(items)
        if list == nil then
            return false, why
        end

        if S.ws and S.ws.slot == slot then
            S.ws.list = list
        end

        S.wsNames = S.wsNames or {}
        for _, e in ipairs(list) do
            S.wsNames[e.id] = e.label
        end

        return true
    end, function(why, kind, job)
        if S.ws and S.ws.slot == slot then
            S.ws.list, S.ws.listWhy = nil, (job and job.code == 'notout') and 'notout' or why
        end
    end)
end

-- Save: the edit as the stored setting for the mate's job (server confirmed)
function M.ws_save(slot, edit)
    if M.busy() then
        return busy_say()
    end

    S.progress = 'Saving the weapon skill settings...'
    read_request({ 'wss', tostring(slot), tostring(edit.control), tostring(edit.mode), tostring(edit.tp), tostring(edit.ws) },
        function(items)
            S.progress = nil
            local ok, d = ws_got(slot, items)
            if not ok then
                return false, d
            end

            say(string.format('Weapon skill settings saved (server confirmed): %s. %s', d.source == 'c' and 'Custom' or 'Squad default',
                d.out and (d.applied and 'In use now.' or 'Press Apply WS settings now to use them.') or 'They apply when the mate is called.'))
            return true
        end, function(why)
            S.progress = nil
            say('Weapon skill settings NOT saved: ' .. why, false)
        end)
    return true
end

-- Reset to Squad default: stores control 0 and keeps the other choices for later
function M.ws_reset(slot)
    local w = S.ws
    if not (w and w.data) then
        return false
    end

    w.edit = ws_edit_from(w.data)
    w.edit.control = 0
    return M.ws_save(slot, w.edit)
end

-- Apply: the stored setting on the called mate now
function M.ws_apply(slot)
    if M.busy() then
        return busy_say()
    end

    S.progress = 'Applying the weapon skill settings...'
    read_request({ 'wsa', tostring(slot) }, function(items)
        S.progress = nil
        local ok, d = ws_got(slot, items, true)
        if not ok then
            return false, d
        end

        say(d.applied and 'Weapon skill settings in use now (server confirmed).' or 'Applied, but the server does not confirm it yet. Press Refresh.',
            d.applied and true or 'warn')
        return true
    end, function(why, kind, job)
        S.progress = nil
        if job and job.code == 'notout' then
            say('Not summoned: the saved weapon skill settings apply when the mate is called.', 'warn')
        else
            say('Weapon skill settings NOT applied: ' .. why, false)
        end
    end)
    return true
end

-- ---------------------------------------------------------------- unsaved draft
local function draft_path()
    local root = api.root and api.root()
    return root and (root .. 'squad_draft.lua') or nil
end

function M.save_draft_file()
    local path = draft_path()
    if path and api.writefile and S.draft then
        api.writefile(path, S.draft, 'GambitsV2: a Squad Rule Set that was not saved on the server yet.')
    end
end

function M.load_draft()
    local path = draft_path()
    if not path then
        return
    end

    local chunk = loadfile(path)
    if chunk then
        local ok, d = pcall(chunk)
        if ok and type(d) == 'table' and type(d.rules) == 'table' then
            S.restorable = d
        end
    end
end

function M.delete_draft_file()
    local path = draft_path()
    if path then
        os.remove(path)
    end

    S.restorable = nil
end

-- unloading: keep unsaved edits for the next session
function M.on_unload()
    if S.draft and S.draft.dirty and not S.draft.readonly then
        M.save_draft_file()
    end
end

-- ---------------------------------------------------------------- readable names (what players see; the data keeps the ids)
-- Wording follows the Gambits v2 WHM prototype (dev/gambits-v2-prototype/rule_model.py) and the launcher's rule editor
-- (launcher_rules.py). Anything without an entry is shown as a tidied name ("SOME_NAME" -> "Some Name").
M.TARGET_LABELS = { SELF = 'Self', PARTY = 'Party member', PARTY_LOWEST_HPP = 'Party member, lowest HP', TANK = 'Tank',
                    CASTER = 'Mage', MELEE = 'Melee', RANGED = 'Ranged', TOP_ENMITY = 'Ally with aggro',
                    TARGET = 'Enemy (current target)', MASTER = 'Master (you)',
                    TRIGGER_SELF_ACTION_TARGET = 'Check Self -> Act on Enemy' }
-- what each target really means in the engine (gambits_container.cpp), shown as a tooltip
M.TARGET_HELP = {
    SELF = 'The squad mate itself.',
    PARTY = 'The first party member, in party order, that matches the conditions.',
    PARTY_LOWEST_HPP = 'The party member with the lowest HP % that matches the conditions (alive, within 15 yalms; '
        .. 'equal HP % keeps party order). Good for healing.',
    TANK = 'A party member whose main job is PLD or RUN, or one given the role tank with !squad partyrole.',
    CASTER = 'A party member whose main job is WHM, BLM, RDM, BRD, SMN, BLU, SCH, GEO or RUN, or one given the role mage '
        .. 'with !squad partyrole.',
    MELEE = 'A party member whose main job is a melee job (WAR MNK THF PLD DRK BST SAM NIN DRG BLU PUP DNC RUN), or one '
        .. 'given the role melee with !squad partyrole.',
    RANGED = 'A party member whose main job is RNG or COR, or one given the role ranged with !squad partyrole.',
    TOP_ENMITY = 'The party member the enemy is attacking (highest enmity).',
    TARGET = 'The enemy the squad mate is fighting.',
    MASTER = 'You, the player.',
    TRIGGER_SELF_ACTION_TARGET = 'The conditions are checked on the squad mate itself, the action goes to the enemy. '
        .. 'E.g. "MP below 50 %" -> Aspir the enemy, or "HP below 50 %" -> Drain the enemy.',
}
M.KIND_LABELS   = { family = 'Best of Family', spell = 'Specific Spell', ja = 'Job Ability', ranged = 'Ranged attack',
                    nuke = 'Best nuke (weakness)', burst = 'Magic burst' }
-- (job expansion) offered for new rules: ranged (RNG/COR), nuke (the best nuke for the enemy's weakness) and burst (the
-- best spell for the open magic burst window) too
M.NEW_KINDS     = { 'family', 'spell', 'ja', 'ranged', 'nuke', 'burst' }
M.KIND_HELP     = {
    family = 'The best spell of a family the mate knows (e.g. Cure -> Cure IV).',
    spell  = 'One exact spell.',
    ja     = 'One job ability.',
    ranged = 'A ranged attack (needs a ranged weapon and ammunition).',
    nuke   = 'The strongest elemental nuke of the element the enemy is weakest to.',
    burst  = 'The best spell for the open magic burst: an element of the skillchain, the enemy\'s weakest resistance, '
        .. 'enough MP, not on recast, and a cast that ends before the window closes. Use it with "A magic burst is possible".',
}

-- The condition builder (Target -> Conditions -> Action): a subject, a comparison and a value. Each pair is one engine
-- condition; nothing here is emulated. Conditions outside it (level, random, timer, ...) stay as they are in existing
-- rules and are shown with their own names.
M.SUBJECTS = {
    { key = 'ALWAYS',  label = 'Always',      ops = { { 'always', 'ALWAYS' } } },
    { key = 'HP',      label = 'HP',          ops = { { 'below', 'HPP_LT' }, { 'at least', 'HPP_GTE' } }, unit = '%', default = 50 },
    { key = 'MP',      label = 'MP',          ops = { { 'below', 'MPP_LT' }, { 'at least', 'MPP_GTE' } }, unit = '%', default = 50 },
    -- (server version 5) MP of characters that have MP: false for a target without MP (a Warrior), unlike MP above
    { key = 'MPUSER',  label = 'MP (mages)',  ops = { { 'below', 'HAS_MP_MPP_LT' }, { 'at least', 'HAS_MP_MPP_GTE' } }, unit = '%',
      default = 50 },
    { key = 'HASMP',   label = 'Uses MP',     ops = { { 'yes (has an MP pool)', 'HAS_MP' } } },
    { key = 'TP',      label = 'TP',          ops = { { 'below', 'TP_LT' }, { 'at least', 'TP_GTE' } }, unit = 'TP', default = 1000 },
    { key = 'MISSING', label = 'Missing HP',  ops = { { 'at least', 'HP_MISSING' } }, unit = 'HP', default = 500 },
    { key = 'AGGRO',   label = 'Aggro',       ops = { { 'has it (the mate itself)', 'HAS_TOP_ENMITY' },
                                                      { 'does not have it', 'NOT_HAS_TOP_ENMITY' } } },
    -- (hotfix 2026-11-21) the engine's party tank test (a party member whose main job is NIN, PLD or RUN; the rule's
    -- target does not matter). The Basic Warrior starter uses NOT_PT_HAS_TANK, which the builder could not offer.
    { key = 'PTTANK',  label = 'Party tank',  ops = { { 'there is one (NIN, PLD or RUN)', 'PT_HAS_TANK' },
                                                      { 'there is none', 'NOT_PT_HAS_TANK' } } },
    { key = 'STATUS',  label = 'Status',      ops = { { 'has', 'STATUS' }, { 'is missing', 'NOT_STATUS' } } },
    { key = 'ENEMY',   label = 'Enemy',       ops = { { 'is casting a spell', 'CASTING_MA' }, { 'is readying a weapon skill', 'READYING_WS' },
                                                      { 'is readying a special move', 'READYING_MS' },
                                                      { 'is readying a job ability', 'READYING_JA' } }, enemyOnly = true },
    -- (server version 5) the mate's own recast of a job ability is running (whatever the rule's target is)
    { key = 'COOLDOWN', label = 'Ability on Cooldown', ops = { { 'is on cooldown (the mate\'s)', 'JA_ON_COOLDOWN' } } },
    -- (job expansion, server version 6) Utsusemi shadows / Blink images left below a number (MOD_LT): Utsusemi again
    -- before the last shadow goes
    { key = 'SHADOWS', label = 'Shadows / images', ops = { { 'below', 'MOD_LT' } }, default = 'UTSUSEMI.2' },
    -- (job expansion) the advanced conditions: offered only with "More conditions" ticked (a saved rule with one is
    -- always shown)
    { key = 'SKILLCHAIN', label = 'Skillchain', ops = { { 'a magic burst is possible', 'MB_AVAILABLE' },
                                                        { 'a skillchain is open', 'SC_AVAILABLE' },
                                                        { 'no skillchain is open', 'NOT_SC_AVAILABLE' } },
      enemyOnly = true, advanced = true },
    { key = 'LEVEL',   label = 'Level',       ops = { { 'below', 'LVL_LT' }, { 'at least', 'LVL_GTE' } }, unit = '', default = 30,
      advanced = true },
    { key = 'TIMER',   label = 'Timer',       ops = { { 'every', 'TIMER' } }, unit = 's', default = 60, advanced = true },
    { key = 'RANDOM',  label = 'Random',      ops = { { 'chance', 'RANDOM' } }, unit = '%', default = 50, advanced = true },
}

-- (job expansion) how the conditions are offered: common (always in the builder), advanced (with "More conditions"),
-- hidden (never offered: other jobs' conditions or engine internals; a saved rule with one is still shown and kept)
M.CONDITION_CLASS = {}
for _, subj in ipairs(M.SUBJECTS) do
    for _, op in ipairs(subj.ops) do
        M.CONDITION_CLASS[op[2]] = subj.advanced and 'advanced' or 'common'
    end
end
for _, id in ipairs({ 'CASTING_DEBUFF', 'CASTING_ELEMENT_MA', 'CAST_ELE_MA_SELF', 'CASTING_ELE_MA_AOE', 'NEED_ELE_BAREFFECT',
                      'NO_SAMBA', 'NO_STORM', 'NO_MAX_RUNE', 'HAS_RUNES', 'LUNGE_MB_AVAILABLE', 'STATUS_FLAG', 'IS_ECOSYSTEM' }) do
    M.CONDITION_CLASS[id] = 'hidden'
end
M.SUBJECT_OF = {}   -- condition id -> subject, op index
for _, subj in ipairs(M.SUBJECTS) do
    for i, op in ipairs(subj.ops) do
        M.SUBJECT_OF[op[2]] = { subj = subj, op = i }
    end
end

-- Status effects offered first in the picker (any other effect can be typed; the server checks the name)
M.COMMON_EFFECTS = { 'PROTECT', 'SHELL', 'REGEN', 'HASTE', 'STONESKIN', 'BLINK', 'AQUAVEIL', 'REFRESH', 'RERAISE',
                     'POISON', 'PARALYSIS', 'BLINDNESS', 'SILENCE', 'PETRIFICATION', 'DISEASE', 'PLAGUE', 'CURSE_I',
                     'SLEEP_I', 'SLOW', 'WEIGHT', 'BIND', 'BIO', 'DIA', 'DOOM' }

-- condition id -> { label, unit } ; unit: '%', 'HP', 's' (seconds), '' (a plain number), 'effect', nil (no value)
M.COND_LABELS = {
    ALWAYS             = { 'Always' },
    HPP_LT             = { 'HP below', '%' },
    HPP_GTE            = { 'HP at least', '%' },
    MPP_LT             = { 'MP below', '%' },
    MPP_GTE            = { 'MP at least', '%' },
    TP_LT              = { 'TP below', '' },
    CASTING_DEBUFF     = { 'Casting a debuff' },
    CASTING_ELEMENT_MA = { 'Casting elemental magic' },
    CAST_ELE_MA_SELF   = { 'Casting elemental magic on itself' },
    CASTING_ELE_MA_AOE = { 'Casting area elemental magic' },
    NEED_ELE_BAREFFECT = { 'Needs an element bar-spell' },
    NO_SAMBA           = { 'No samba active' },
    NO_STORM           = { 'No storm active' },
    NO_MAX_RUNE        = { 'Runes not at maximum' },
    HAS_RUNES          = { 'Has runes' },
    TP_GTE             = { 'TP at least', '' },
    LVL_LT             = { 'Level below', '' },
    LVL_GTE            = { 'Level at least', '' },
    HP_MISSING         = { 'HP missing at least', 'HP' },
    RANDOM             = { 'Random chance', '%' },
    TIMER              = { 'Every', 's' },
    STATUS             = { 'Has effect', 'effect' },
    NOT_STATUS         = { 'Missing effect', 'effect' },
    HAS_TOP_ENMITY     = { 'Has the enemy\'s attention' },
    NOT_HAS_TOP_ENMITY = { 'Does not have the enemy\'s attention' },
    PT_HAS_TANK        = { 'Party has a tank' },
    NOT_PT_HAS_TANK    = { 'Party has no tank' },
    SC_AVAILABLE       = { 'A skillchain is open' },
    NOT_SC_AVAILABLE   = { 'No skillchain is open' },
    MB_AVAILABLE       = { 'A magic burst is possible' },
    LUNGE_MB_AVAILABLE = { 'A Lunge burst is possible' },
    READYING_WS        = { 'Readying a weapon skill' },
    READYING_MS        = { 'Readying a special move' },
    READYING_JA        = { 'Readying a job ability' },
    CASTING_MA         = { 'Casting a spell' },
    HAS_MP             = { 'Uses MP' },
    HAS_MP_MPP_LT      = { 'MP (mages) below', '%' },
    HAS_MP_MPP_GTE     = { 'MP (mages) at least', '%' },
    JA_ON_COOLDOWN     = { 'On cooldown:', 'ja' },
    MOD_LT             = { 'Below:', 'mod' },
}

local ROMAN = { I = true, II = true, III = true, IV = true, V = true, VI = true }

-- "CURE_II" -> "Cure II", "DIVINE_SEAL" -> "Divine Seal"
function M.pretty(name)
    if name == nil or name == '' then
        return ''
    end

    local words = {}
    for word in tostring(name):gmatch('[^_]+') do
        local upper = word:upper()
        words[#words + 1] = ROMAN[upper] and upper or (upper:sub(1, 1) .. upper:sub(2):lower())
    end

    return table.concat(words, ' ')
end

function M.target_label(id)
    return M.TARGET_LABELS[id or ''] or M.pretty(id)
end

function M.kind_label(id)
    return M.KIND_LABELS[id or ''] or M.pretty(id)
end

function M.cond_label(id)
    local l = M.COND_LABELS[id or '']
    return l and l[1] or M.pretty(id)
end

function M.cond_unit(id, cat)
    local l = M.COND_LABELS[id or '']
    if l then
        return l[2]
    end

    local c = cat and cat.conds and cat.conds[id or '']
    return c and (c.kind == 'e' and 'effect' or c.kind == 'j' and 'ja' or c.kind == 'm' and 'mod' or c.kind == 'r' and '' or nil) or nil
end

-- "UTSUSEMI.2" -> "Utsusemi shadows below 2"
function M.mod_text(arg)
    local name, n = M.mod_parse(arg)
    if name == nil then
        return '? below ?'
    end

    return M.MODS[name][3] .. ' below ' .. tostring(n)
end

-- "HP below 50%", "Missing effect Protect", "Always"
function M.cond_text(id, arg, cat)
    if id == nil then
        return ''
    end

    local unit = M.cond_unit(id, cat)
    local label = M.cond_label(id)
    if id == 'JA_ON_COOLDOWN' then
        return (arg and arg ~= '' and M.pretty(arg) or '?') .. ' is on cooldown' -- "Provoke is on cooldown"
    elseif unit == 'mod' then
        return M.mod_text(arg)
    elseif unit == nil then
        return label
    elseif unit == 'effect' or unit == 'ja' then
        return label .. ' ' .. (arg and arg ~= '' and M.pretty(arg) or '?')
    elseif unit == 's' then
        return label .. ' ' .. tostring(arg or '?') .. ' s'
    elseif unit == 'HP' then
        return label .. ' ' .. tostring(arg or '?') .. ' HP'
    end

    return label .. ' ' .. tostring(arg or '?') .. unit
end

function M.action_text(r)
    if r == nil or r.kind == nil then
        return '(no action)'
    end

    if not M.NAMED_KINDS[r.kind] then
        return M.kind_label(r.kind)
    end

    if r.name == nil or r.name == '' then
        return M.kind_label(r.kind) .. ': ?'
    end

    return r.kind == 'family' and ('Best of ' .. M.pretty(r.name)) or M.pretty(r.name)
end

-- (beta polish) the compact rule line of the rule list: "Enemy: Not top enmity + No tank -> Provoke". The full wording
-- (M.rule_summary) stays in the tooltip and under the selected rule.
M.TARGET_SHORT = { SELF = 'Self', PARTY = 'Party', PARTY_LOWEST_HPP = 'Lowest HP', TANK = 'Tank', CASTER = 'Mage', MELEE = 'Melee',
                   RANGED = 'Ranged', TOP_ENMITY = 'Aggro ally', TARGET = 'Enemy', MASTER = 'You',
                   TRIGGER_SELF_ACTION_TARGET = 'Self->Enemy' }
M.COND_SHORT = {
    ALWAYS = 'Always', HAS_TOP_ENMITY = 'Top enmity', NOT_HAS_TOP_ENMITY = 'Not top enmity', PT_HAS_TANK = 'Tank in party',
    NOT_PT_HAS_TANK = 'No tank', SC_AVAILABLE = 'Skillchain open', NOT_SC_AVAILABLE = 'No skillchain', MB_AVAILABLE = 'Burst window',
    CASTING_MA = 'Casting', CASTING_DEBUFF = 'Casting a debuff', READYING_WS = 'Readying WS', READYING_MS = 'Readying move',
    READYING_JA = 'Readying JA', HAS_MP = 'Uses MP',
}
M.COND_SHORT_VALUE = { -- id -> prefix, suffix
    HPP_LT = { 'HP < ', '%' }, HPP_GTE = { 'HP >= ', '%' }, MPP_LT = { 'MP < ', '%' }, MPP_GTE = { 'MP >= ', '%' },
    HAS_MP_MPP_LT = { 'Mage MP < ', '%' }, HAS_MP_MPP_GTE = { 'Mage MP >= ', '%' }, TP_LT = { 'TP < ', '' }, TP_GTE = { 'TP >= ', '' },
    HP_MISSING = { 'Missing ', ' HP' }, LVL_LT = { 'Lv < ', '' }, LVL_GTE = { 'Lv >= ', '' }, RANDOM = { '', '% chance' },
    TIMER = { 'Every ', ' s' },
}

function M.cond_short(id, arg, cat)
    if id == nil then
        return ''
    elseif M.COND_SHORT[id] then
        return M.COND_SHORT[id]
    elseif M.COND_SHORT_VALUE[id] then
        return M.COND_SHORT_VALUE[id][1] .. tostring(arg or '?') .. M.COND_SHORT_VALUE[id][2]
    elseif id == 'STATUS' then
        return 'Has ' .. (arg and M.pretty(arg) or '?')
    elseif id == 'NOT_STATUS' then
        return 'No ' .. (arg and M.pretty(arg) or '?')
    elseif id == 'JA_ON_COOLDOWN' then
        return (arg and M.pretty(arg) or '?') .. ' on cooldown'
    elseif id == 'MOD_LT' then
        local name, n = M.mod_parse(arg)
        local short = { UTSUSEMI = 'Shadows', BLINK = 'Images' }
        return (name and short[name] or '?') .. ' < ' .. tostring(n or '?')
    end

    return M.cond_text(id, arg, cat)
end

function M.rule_short(r, cat)
    if r == nil then
        return ''
    elseif r.opaque then
        return '(kept unchanged, read-only)'
    end

    local when = M.cond_short(r.cond, r.arg, cat)
    if r.cond2 then
        when = when .. ' + ' .. M.cond_short(r.cond2, r.arg2, cat)
    end

    local text = string.format('%s: %s -> %s', M.TARGET_SHORT[r.target or ''] or M.target_label(r.target), when ~= '' and when or '?',
        M.action_text(r))
    if r.retry and tonumber(r.retry) and tonumber(r.retry) > 0 then
        text = text .. string.format(' (wait %s s)', r.retry)
    end

    if r.level ~= nil then
        text = text .. string.format(' (Lv %s+)', r.level)
    end

    return text
end

-- One line for the rule list: "Party member: HP below 50% -> Best of Cure"
function M.rule_summary(r, cat)
    if r == nil then
        return ''
    end

    if r.opaque then
        return '(uses options this editor cannot show - kept unchanged, read-only)'
    end

    local when = M.cond_text(r.cond, r.arg, cat)
    if r.cond2 then
        when = when .. ' and ' .. M.cond_text(r.cond2, r.arg2, cat)
    end

    local text = string.format('%s: %s -> %s', M.target_label(r.target), when ~= '' and when or '(no condition)', M.action_text(r))
    if r.retry and r.retry ~= '' and tonumber(r.retry) and tonumber(r.retry) > 0 then
        text = text .. string.format(' (then waits %s s)', r.retry)
    end

    if r.level ~= nil then
        text = text .. string.format(' (from level %s)', r.level)
    end

    return text
end

-- A server reason with ids in it ("MARTYR needs level 75") as players read it ("Martyr needs level 75")
function M.readable(text)
    return (tostring(text or ''):gsub('%f[%w_]([A-Z][A-Z0-9_]+)%f[^%w_]', function(word)
        if #word >= 4 or word:find('_', 1, true) then
            return M.pretty(word)
        end
    end))
end

-- "Protect" / "protect" / "PROTECT" -> "PROTECT" (the id the server checks)
function M.effect_id(text)
    return (tostring(text or ''):upper():gsub('[^A-Z0-9]+', '_'):gsub('^_+', ''):gsub('_+$', ''))
end

-- ---------------------------------------------------------------- rule list operations (local, no server)
function M.new_rule()
    return { on = true, target = 'PARTY', cond = 'HPP_LT', arg = '50', kind = 'family', name = 'CURE' }
end

-- Each returns the new selected index
function M.add_rule(d, sel)
    if #d.rules >= M.MAX_RULES then
        return sel
    end

    local at = math.min((sel or #d.rules) + 1, #d.rules + 1)
    table.insert(d.rules, at, M.new_rule())
    d.dirty = true
    return at
end

function M.remove_rule(d, sel)
    if sel == nil or d.rules[sel] == nil then
        return sel
    end

    table.remove(d.rules, sel)
    d.dirty = true
    if #d.rules == 0 then
        return nil
    end

    return math.min(sel, #d.rules)
end

function M.move_rule(d, sel, delta)
    local to = (sel or 0) + delta
    if sel == nil or d.rules[sel] == nil or d.rules[to] == nil then
        return sel
    end

    d.rules[sel], d.rules[to] = d.rules[to], d.rules[sel]
    d.dirty = true
    return to
end

function M.toggle_rule(d, sel)
    local r = sel and d.rules[sel]
    if r then
        r.on = r.on == false
        d.dirty = true
    end

    return sel
end

-- ---------------------------------------------------------------- theme
-- The colours of FFXIPort 1.2.0 (ffxiport/ui/theme.lua, Copyright (C) 2026 wildthing, GPL-3.0-only; the same author's
-- palettes, reused here, value for value, with its rounding and frame border). GambitsV2 owns its whole window, so the
-- theme applies to all of it (GambitsV2.lua pushes the window colours from M.theme). Classic is the default.
local function rgba(r, g, b, a)
    return { r, g, b, a or 1.0 }
end

local function times(c, f)
    return { math.min(c[1] * f, 1.0), math.min(c[2] * f, 1.0), math.min(c[3] * f, 1.0), c[4] }
end

M.THEMES = {
    classic = {
        window = rgba(0.105, 0.095, 0.082), panel = rgba(0.105, 0.095, 0.082), header = rgba(0.23, 0.18, 0.10),
        button = rgba(0.24, 0.19, 0.10), border = times(rgba(0.23, 0.18, 0.10), 1.25), text = rgba(0.91, 0.89, 0.80),
        gold = rgba(0.82, 0.63, 0.22), tabSel = rgba(0.53, 0.42, 0.09), rowSel = rgba(0.53, 0.42, 0.09),
        muted = rgba(0.47, 0.44, 0.36), secondary = rgba(0.64, 0.60, 0.50), goGold = rgba(0.82, 0.62, 0.10),
        goText = rgba(0.10, 0.08, 0.05), ok = rgba(0.55, 0.80, 0.45), bad = rgba(0.90, 0.35, 0.30), dot = rgba(0.86, 0.67, 0.22),
    },
    squad = {
        window = rgba(0.067, 0.075, 0.106), panel = rgba(0.110, 0.118, 0.161), header = rgba(0.150, 0.165, 0.220),
        button = rgba(0.169, 0.188, 0.255), border = rgba(0.300, 0.320, 0.400, 0.55), text = rgba(0.902, 0.922, 0.949),
        gold = rgba(0.890, 0.741, 0.400), tabSel = rgba(0.600, 0.470, 0.190), rowSel = rgba(0.215, 0.255, 0.360),
        muted = rgba(0.459, 0.490, 0.549), secondary = rgba(0.580, 0.612, 0.678), goGold = rgba(0.780, 0.620, 0.260),
        goText = rgba(0.075, 0.075, 0.095), ok = rgba(0.450, 0.780, 0.500), bad = rgba(0.900, 0.420, 0.400),
        dot = rgba(0.360, 0.560, 0.880), title = rgba(0.080, 0.090, 0.125), titleActive = rgba(0.110, 0.125, 0.175),
        rounding = { window = 6, child = 5, frame = 4, tab = 4 }, frameBorder = 1,
    },
    crimson = {
        window = rgba(0.090, 0.068, 0.074), panel = rgba(0.125, 0.090, 0.100), header = rgba(0.215, 0.110, 0.130),
        button = rgba(0.285, 0.130, 0.155), border = rgba(0.420, 0.220, 0.250, 0.60), text = rgba(0.930, 0.895, 0.885),
        gold = rgba(0.900, 0.620, 0.580), tabSel = rgba(0.500, 0.165, 0.205), rowSel = rgba(0.360, 0.140, 0.175),
        muted = rgba(0.560, 0.470, 0.480), secondary = rgba(0.700, 0.610, 0.610), goGold = rgba(0.640, 0.215, 0.255),
        goText = rgba(0.985, 0.935, 0.925), ok = rgba(0.560, 0.800, 0.520), bad = rgba(0.990, 0.520, 0.440),
        dot = rgba(0.820, 0.270, 0.370), title = rgba(0.250, 0.085, 0.105), titleActive = rgba(0.340, 0.115, 0.140),
        rounding = { window = 6, child = 5, frame = 4, tab = 4 }, frameBorder = 1,
    },
}
M.THEME_ORDER = { 'classic', 'squad', 'crimson' }
M.THEME_NAMES = { classic = 'Classic', squad = 'Squad', crimson = 'Crimson' }
M.theme, M.themeName = M.THEMES.classic, 'classic'
M.times = times

-- selects a theme by name (anything unknown: Classic); returns the name used
function M.set_theme(name)
    name = M.THEMES[name or ''] and name or 'classic'
    M.theme, M.themeName = M.THEMES[name], name
    return name
end

-- ---------------------------------------------------------------- UI (ImGui, drawn inside the GambitsV2 window)
local function imgui()
    return api.imgui
end

local function s(px)
    return api.s and api.s(px) or px
end

-- Pushes colours, runs fn, pops exactly what was pushed (also when fn fails), then re-raises the error
local function with_colors(list, fn, ...)
    local g = imgui()
    local pushed = 0
    for _, item in ipairs(list) do
        local id = rawget(_G, item[1])
        if id ~= nil and item[2] ~= nil and g.PushStyleColor then
            g.PushStyleColor(id, item[2])
            pushed = pushed + 1
        end
    end

    local ok, err = pcall(fn, ...)
    if pushed > 0 and g.PopStyleColor then
        g.PopStyleColor(pushed)
    end

    if not ok then
        error(err, 0)
    end
end
M.with_colors = with_colors

-- Runs fn between open() and close(); close() always runs (an error must not leave ImGui's stacks unbalanced)
local function scoped(open, close, fn, ...)
    local ok, err = pcall(fn, ...)
    close()
    if not ok then
        error(err, 0)
    end
end

local function child(id, size, fn)
    local g = imgui()
    local shown = g.BeginChild(id, size, rawget(_G, 'ImGuiChildFlags_Borders') or 1)
    scoped(nil, function() g.EndChild() end, function()
        if shown then
            fn()
        end
    end)
end

local function colored(color, text)
    local g = imgui()
    if g.TextColored then
        g.TextColored(color, text)
    else
        g.Text(text)
    end
end

local function heading(text)
    colored(M.theme.gold, text)
end

local function note(text)
    colored(M.theme.secondary, text)
end

local function button(label, w)
    return imgui().Button(label, { w or 0, 0 })
end

local function same(spacing)
    imgui().SameLine(0, spacing or s(6))
end

local function width(w)
    local g = imgui()
    if g.SetNextItemWidth then
        g.SetNextItemWidth(w)
    end
end

local function available()
    local g = imgui()
    if api.available then
        local w = api.available()
        if type(w) == 'number' and w > 0 then
            return w
        end
    end

    if g.GetContentRegionAvail then
        local a, b = g.GetContentRegionAvail()
        if type(a) == 'table' then
            return tonumber(a[1] or a.x) or s(600)
        elseif type(a) == 'number' then
            return a
        end
    end

    return s(600)
end

-- (hotfix 2026-11-21) Ashita's Lua bindings hand the text of imgui.SetTooltip and imgui.TextWrapped to ImGui as a
-- printf FORMAT (addons.dll passes the Lua string as the only argument of IGuiManager::SetTooltip(fmt, ...) and
-- TextWrapped(fmt, ...)). A '%' in such a text is read as a conversion: "40% and" printed garbage (% a), and the Lowest
-- HP help ("HP % that") is an invalid format, on which the C runtime ends the game (0xC0000409). TextUnformatted never
-- formats, so tooltips and wrapped lines are drawn with it; the text the player sees is unchanged.
local function format_safe(text)
    return (tostring(text or ''):gsub('%%', '%%%%')) -- (only for a binding without TextUnformatted: '%%' shows one '%')
end

local function tooltip(text)
    local g = imgui()
    if not (g.IsItemHovered and g.IsItemHovered()) then
        return
    end

    if g.BeginTooltip and g.EndTooltip and g.TextUnformatted then
        if g.BeginTooltip() ~= false then -- (true when shown; nil from a binding that returns nothing)
            g.TextUnformatted(tostring(text or ''))
            g.EndTooltip()
        end
    elseif g.SetTooltip then
        g.SetTooltip(format_safe(text))
    end
end

-- the height left in the current window or panel
local function available_h()
    local g = imgui()
    if g.GetContentRegionAvail then
        local a, b = g.GetContentRegionAvail()
        if type(a) == 'table' then
            return tonumber(a[2] or a.y) or s(400)
        elseif type(b) == 'number' then
            return b
        end
    end

    return s(400)
end
M.available_h = available_h

-- coloured text that wraps at the panel's edge (status lines, warnings: never cut off)
-- (hotfix 2026-11-21) drawn unformatted: see tooltip() above. PushTextWrapPos(0) + TextUnformatted is what TextWrapped
-- does inside ImGui, without reading the text as a format.
local function wrapped(color, text)
    local g = imgui()
    if g.PushTextWrapPos and g.PopTextWrapPos and g.TextUnformatted then
        with_colors({ { 'ImGuiCol_Text', color } }, function()
            g.PushTextWrapPos(0)
            scoped(nil, function() g.PopTextWrapPos() end, function() g.TextUnformatted(tostring(text or '')) end)
        end)
    elseif g.TextWrapped then
        with_colors({ { 'ImGuiCol_Text', color } }, function() g.TextWrapped(format_safe(text)) end)
    else
        colored(color, text)
    end
end

-- continue the line when `w` pixels still fit, else start a new one (narrow windows, large scales; FFXIPort's pattern)
local function same_if_fits(w, indent)
    local g = imgui()
    g.SameLine(0, s(6))
    if g.NewLine and available() < w then
        g.NewLine()
        if indent and g.SetCursorPosX then
            g.SetCursorPosX(indent)
        end
    end
end
M.same_if_fits = same_if_fits

-- a label for a control on the same line, vertically centred on it
local function label_text(text)
    local g = imgui()
    if g.AlignTextToFramePadding then
        g.AlignTextToFramePadding()
    end

    g.Text(text)
end

-- a drop-down of ids shown by their readable names: returns the chosen id (tipOf: an optional tooltip per entry)
local function combo(id, current, values, labelOf, tipOf)
    local g = imgui()
    local function label(v)
        if v == nil then
            return '(none)'
        end

        return labelOf and labelOf(v) or tostring(v)
    end

    if not g.BeginCombo then
        -- older ImGui bindings: a button that steps through the choices
        if g.Button(label(current) .. id, { 0, 0 }) and #values > 0 then
            local at = 0
            for i, v in ipairs(values) do
                if v == current then
                    at = i
                end
            end

            current = values[at % #values + 1]
        end

        return current
    end

    if g.BeginCombo(id, label(current)) then
        for i, v in ipairs(values) do
            if g.Selectable(label(v) .. '##' .. tostring(i), v == current) then
                current = v
            end

            local tip = tipOf and tipOf(v)
            if tip then
                tooltip(tip)
            end
        end

        g.EndCombo()
    end

    return current
end

local function text_field(id, value, size)
    local buf = { value or '' }
    imgui().InputText(id, buf, size or 32)
    return buf[1]
end

-- a whole number field that keeps exactly what the player typed: nothing is clamped or replaced; the value changes
-- only when the player changes it (a value out of range is shown in red and blocks Save, M.check_draft)
local function int_input(id, value)
    local g = imgui()
    if g.InputInt then
        local buf = { tonumber(value) or 0 }
        if g.InputInt(id, buf) then
            local n = tonumber(buf[1])
            if n ~= nil then
                return string.format('%d', math.floor(n))
            end
        end

        return value
    end

    local typed = text_field(id, value or '', 8)
    if typed ~= (value or '') and string.match(typed, '^%-?%d*$') then
        return typed
    end

    return value
end

-- ---------------------------------------------------------------- edits without ImGui (the window calls these; tests too)
local function cond_keys(slot)
    if slot == 2 then
        return 'cond2', 'arg2'
    end

    return 'cond', 'arg'
end

-- Sets condition slot 1 or 2 (cond nil clears slot 2). Changing only the comparison (HP below -> HP at least) keeps the
-- value exactly; another subject starts from its default value (a status effect is left to choose).
function M.set_condition(r, slot, cond, cat)
    local ck, ak = cond_keys(slot)
    if cond == nil then
        if slot == 2 then
            r.cond2, r.arg2 = nil, nil
        end

        return
    end

    local old = r[ck]
    if old == cond then
        return
    end

    r[ck] = cond
    local so, sn = old and M.SUBJECT_OF[old], M.SUBJECT_OF[cond]
    if so and sn and so.subj == sn.subj then
        return
    end

    local spec = cat and cat.conds and cat.conds[cond]
    if spec and spec.kind == 'r' then
        local v = sn and sn.subj.default or spec.lo
        r[ak] = string.format('%d', math.max(spec.lo, math.min(spec.hi, v)))
    elseif spec and spec.kind == 'm' then
        r[ak] = (sn and sn.subj.default) or 'UTSUSEMI.2' -- (job expansion) MOD_LT: "MODIFIER.number"
    else
        r[ak] = nil
    end
end

-- Sets the action kind (and name); another kind clears the name, a kind without a name has none
function M.set_action(r, kind, name)
    if kind ~= r.kind then
        r.kind, r.name = kind, nil
    end

    if M.NAMED_KINDS[kind] then
        r.name = name or r.name
    else
        r.name = nil
    end
end

-- the subjects the builder offers for a slot: only those whose engine conditions the server's catalog reports
-- (job expansion) advanced = true also offers the advanced subjects (skillchain, level, timer, random)
function M.subjects_for(slot, target, cat, advanced)
    local out = {}
    for _, subj in ipairs(M.SUBJECTS) do
        local reported = true
        for _, op in ipairs(subj.ops) do
            reported = reported and cat and cat.conds and cat.conds[op[2]] ~= nil
        end

        if reported and not (subj.key == 'ALWAYS' and slot == 2) and not (subj.enemyOnly and target ~= 'TARGET')
            and (advanced or not subj.advanced) then
            out[#out + 1] = subj
        end
    end

    return out
end

-- one condition slot: subject, comparison, value
local function condition_editor(r, slot, cat, labelW)
    local g = imgui()
    local ck, ak = cond_keys(slot)
    local cond = r[ck]
    local info = cond and M.SUBJECT_OF[cond]
    local subjects = M.subjects_for(slot, r.target, cat, S.moreConds == true)
    local keys, byKey = {}, {}
    if slot == 2 then
        keys[1] = 'NONE'
    end

    for _, subj in ipairs(subjects) do
        keys[#keys + 1] = subj.key
        byKey[subj.key] = subj
    end

    local current = cond == nil and 'NONE' or (info and info.subj.key) or 'OTHER'
    if info and byKey[current] == nil then
        byKey[current] = info.subj -- (an Enemy condition with another target: shown, flagged by the check)
    end

    width(s(130))
    local picked = combo('##gsq-subj' .. slot, current, keys, function(v)
        if v == 'NONE' then
            return '(nothing else)'
        elseif v == 'OTHER' then
            return M.cond_label(cond)
        end

        return byKey[v] and byKey[v].label or v
    end)
    if picked ~= current then
        if picked == 'NONE' then
            M.set_condition(r, 2, nil, cat)
        elseif byKey[picked] then
            M.set_condition(r, slot, byKey[picked].ops[1][2], cat)
        end

        cond = r[ck]
        info = cond and M.SUBJECT_OF[cond]
    end

    if cond == nil then
        return
    end

    if info and #info.subj.ops > 1 then
        same_if_fits(s(190), labelW)
        width(s(190))
        local idx = {}
        for i = 1, #info.subj.ops do
            idx[i] = i
        end

        local op = combo('##gsq-op' .. slot, info.op, idx, function(i) return info.subj.ops[i][1] end)
        if op ~= info.op then
            M.set_condition(r, slot, info.subj.ops[op][2], cat)
            cond = r[ck]
        end
    end

    local spec = cat.conds[cond]
    if spec and spec.kind == 'r' then
        same_if_fits(s(150), labelW)
        width(s(110))
        r[ak] = int_input('##gsq-val' .. slot, r[ak])
        tooltip(string.format('A whole number, %d to %d. Kept exactly as you type it.', spec.lo, spec.hi))
        local unit = M.cond_unit(cond, cat)
        if unit and unit ~= '' and unit ~= 'effect' then
            same(s(3))
            g.Text(unit)
        end

        local n = tonumber(r[ak] or '')
        if n == nil or n < spec.lo or n > spec.hi or n ~= math.floor(n) then
            same()
            colored(M.theme.bad, string.format('(%d-%d)', spec.lo, spec.hi))
        end
    elseif spec and spec.kind == 'e' then
        same_if_fits(s(170), labelW)
        width(s(170))
        local list = {}
        for _, e in ipairs(M.COMMON_EFFECTS) do
            list[#list + 1] = e
        end

        local chosen = combo('##gsq-eff' .. slot, r[ak], list, function(v) return v and M.pretty(v) or '(choose)' end)
        if chosen ~= r[ak] then
            r[ak] = chosen
        end

        same_if_fits(s(130), labelW)
        width(s(130))
        local shown = r[ak] and M.pretty(r[ak]) or ''
        local typed = text_field('##gsq-efftype' .. slot, shown, 32)
        if typed ~= shown then
            r[ak] = typed ~= '' and M.effect_id(typed) or nil
        end

        tooltip('Pick a common effect, or type any status effect (the server checks the name).')
    elseif spec and spec.kind == 'j' then
        -- (server version 5) JA_ON_COOLDOWN: one of the mate's own job abilities
        same_if_fits(s(220), labelW)
        width(s(220))
        local names, info = {}, {}
        for _, e in ipairs(M.ja_choices(cat, M.mate())) do
            names[#names + 1] = e.name
            info[e.name] = e
        end

        local chosen = combo('##gsq-ja' .. slot, r[ak], names, function(v)
            return v and (info[v] and info[v].label or M.pretty(v)) or '(choose)'
        end)
        if chosen ~= r[ak] then
            r[ak] = chosen
        end

        tooltip('True while the squad mate\'s own recast of this job ability is running (e.g. Flash while Provoke is not ready).')
    elseif spec and spec.kind == 'm' then
        -- (job expansion, server version 6) MOD_LT: which count, and the number it must be below ("UTSUSEMI.2")
        local name, n = M.mod_parse(r[ak])
        same_if_fits(s(170), labelW)
        width(s(170))
        local chosen = combo('##gsq-mod' .. slot, name, M.MOD_ORDER, function(v) return v and M.MODS[v][3] or '(choose)' end)
        same_if_fits(s(110), labelW)
        width(s(110))
        local typed = int_input('##gsq-modn' .. slot, tostring(n or 2))
        r[ak] = string.format('%s.%s', chosen or 'UTSUSEMI', typed ~= nil and typed ~= '' and typed or '2')
        tooltip('True while the target has fewer than this many left (Utsusemi shadows or Blink images). '
            .. 'E.g. Utsusemi shadows below 2: cast Utsusemi again before the last shadow is gone.')
        local why = M.mod_problem(r[ak])
        if why then
            same()
            colored(M.theme.bad, '(' .. why .. ')')
        end
    end

    if M.ENEMY_CONDS[cond] and r.target ~= 'TARGET' then
        same_if_fits(s(180), labelW)
        colored(M.theme.bad, '(needs the target Enemy)')
    end
end

-- A readable tooltip for a spell or job ability choice: its level, and whether it comes from the sub job
local function choice_tip(e, mate)
    if e == nil then
        return nil
    end

    local who = mate and mate.name or 'The mate'
    if e.sub then
        return string.format('%s: from the sub job%s, level %d.', M.pretty(e.name), mate and mate.sub and (' (' .. mate.sub .. ')') or '',
            e.level or 0)
    end

    return string.format('%s: %s level %d.%s', M.pretty(e.name), mate and mate.job or 'main job', e.level or 0,
        e.confirmed == false and (' Not confirmed for ' .. who .. ' (not learned yet, or blue magic).') or '')
end
M.choice_tip = choice_tip

-- The Specific Spell choices for a mate, one alphabetical list without duplicates, names only (levels in the tooltip).
-- Version 4 server (catm): exactly the spells the server says the mate has (its main and sub job at their levels, the
-- same rules a call uses), Trust spells left out once more. Older server (cat): the job's spells without Trust spells,
-- main-job ones up to the mate's level; the sub job's level is not known then, so its spells are kept up to the main
-- level and the server decides. Returns { { name, level, sub, label } ... }.
function M.spell_choices(cat, mate)
    local out, seen = {}, {}
    local exact = cat and cat.perMate == true
    local maxLevel = (not exact) and mate and tonumber(mate.level) or nil
    for _, sp in ipairs(cat and cat.spells or {}) do
        local name = sp.name
        if name and not (M.TRUSTS and M.TRUSTS[name]) and (maxLevel == nil or (sp.level or 0) <= maxLevel) then
            local prev = seen[name]
            if prev == nil or (prev.sub and not sp.sub) then
                local entry = { name = name, level = sp.level or 0, sub = sp.sub == true, label = M.pretty(name) }
                if prev then
                    for i, e in ipairs(out) do
                        if e == prev then
                            out[i] = entry
                        end
                    end
                else
                    out[#out + 1] = entry
                end

                seen[name] = entry
            end
        end
    end

    table.sort(out, function(a, b)
        if a.label ~= b.label then
            return a.label < b.label
        end

        return a.name < b.name
    end)
    return out
end

-- The Job Ability choices: version 4 (catm) = exactly the abilities the server's U13 rules allow the mate; older
-- servers = the job's list as it comes. Names only, one alphabetical list.
function M.ja_choices(cat, mate)
    local out, seen = {}, {}
    for _, ja in ipairs(cat and cat.jas or {}) do
        if ja.name and not seen[ja.name] then
            seen[ja.name] = true
            out[#out + 1] = { name = ja.name, level = ja.level or 0, sub = ja.sub == true, label = M.pretty(ja.name) }
        end
    end

    table.sort(out, function(a, b) return a.label < b.label end)
    return out
end

local function in_list(list, name)
    for _, e in ipairs(list) do
        if e.name == name then
            return e
        end
    end

    return nil
end

-- Why a saved spell or job ability is not among the mate's choices now (nil when it is): it is kept as it is, never
-- changed; the server decides when the mate is called
function M.action_note(r, cat, mate)
    if r.name == nil or (r.kind ~= 'spell' and r.kind ~= 'ja') then
        return nil
    end

    local who = mate and mate.name or 'the mate'
    local list = r.kind == 'spell' and M.spell_choices(cat, mate) or M.ja_choices(cat, mate)
    local e = in_list(list, r.name)
    if e then
        if e.sub and not (cat and cat.perMate) then
            return string.format('%s uses this with its sub job: the server checks the sub job\'s level.', who:gsub('^%l', string.upper))
        end

        return nil
    end

    if r.kind == 'spell' and M.TRUSTS and M.TRUSTS[r.name] then
        return M.pretty(r.name) .. ' is a Trust spell, not a squad action. It is kept as saved; the server decides.'
    end

    for _, u in ipairs(cat and cat.unconfirmed or {}) do
        if r.kind == 'spell' and u.name == r.name then
            return string.format('%s\'s jobs and levels allow %s, but it is not confirmed (not learned yet, or blue magic). '
                .. 'It is kept as saved; the server decides when %s is called.', who, M.pretty(r.name), who)
        end
    end

    return string.format('%s is not in %s\'s %s now (job, level%s). It is kept as saved; the server decides when %s is called.',
        M.pretty(r.name), who, r.kind == 'spell' and 'spell list' or 'job abilities',
        r.kind == 'ja' and ', main job only or merit' or '', who)
end

-- (kept for the earlier callers and tests)
function M.spell_note(r, cat, mate)
    if r.kind ~= 'spell' then
        return nil
    end

    return M.action_note(r, cat, mate)
end

-- the action's name: spell family, specific spell or job ability, from the server's catalog (names only; details in
-- the tooltip)
local function name_picker(r, cat)
    if not M.NAMED_KINDS[r.kind] then
        return
    end

    local mate = M.mate()
    same_if_fits(s(260), s(100))
    width(s(260))
    local names, info = {}, {}
    if r.kind == 'family' then
        for _, item in ipairs(cat.families or {}) do
            names[#names + 1] = item
        end
    else
        for _, e in ipairs(r.kind == 'spell' and M.spell_choices(cat, mate) or M.ja_choices(cat, mate)) do
            names[#names + 1] = e.name
            info[e.name] = e
        end
    end

    -- (a saved name that is not in the list stays selected and unchanged until the player picks another one)
    r.name = combo('##gsq-name', r.name, names, function(v)
        local it = info[v or '']
        return it and it.label or (v and M.pretty(v) or '(choose)')
    end, function(v) return choice_tip(info[v or ''], mate) end)
    tooltip(choice_tip(info[r.name or ''], mate) or (r.name and M.pretty(r.name)) or 'Choose one.')

    -- spells the mate's jobs allow but the server cannot confirm: shown, not offered
    if r.kind == 'spell' and cat.perMate and #(cat.unconfirmed or {}) > 0 then
        local listed = {}
        for _, u in ipairs(cat.unconfirmed) do
            listed[#listed + 1] = M.pretty(u.name)
        end

        same_if_fits(s(160), s(100))
        note(string.format('(%d more not confirmed)', #listed))
        tooltip('Allowed by ' .. (mate and mate.name or 'the mate') .. '\'s jobs and levels, but not confirmed - not learned yet '
            .. '(spells from scrolls), or blue magic set when called. Not offered:\n' .. table.concat(listed, ', '))
    end
end
-- The selected rule: Target -> Conditions -> Action (edits go straight into the draft; nothing is sent)
local function rule_editor(d, r, cat, readonly)
    local g = imgui()
    local labelW = s(100)
    local function label(text)
        -- the label, vertically centred on its control, then the control at a fixed x position (one aligned column)
        label_text(text)
        g.SameLine(labelW)
    end

    local why = M.protected(r, cat)
    if why then
        colored(M.theme.bad, 'This rule cannot be changed here: ' .. why .. '. It is kept exactly as it is.')
        note('You can still switch it on or off and move it.')
        return
    end

    local disabled = readonly and g.BeginDisabled ~= nil
    if disabled then
        g.BeginDisabled(true)
    end

    local before = M.encode_rule(r)
    scoped(nil, function() if disabled then g.EndDisabled() end end, function()

    label('Target')
    width(s(210))
    local targets = {}
    for _, t in ipairs(cat.targets) do
        targets[#targets + 1] = t
    end

    r.target = combo('##gsq-target', r.target, targets, M.target_label)
    tooltip(M.TARGET_HELP[r.target or ''] or 'Who the rule is about.')

    label('Condition')
    condition_editor(r, 1, cat, labelW)
    label('And')
    condition_editor(r, 2, cat, labelW)
    if g.SetCursorPosX then
        g.SetCursorPosX(labelW)
    end

    -- (job expansion) the advanced conditions (skillchain, level, timer, random) only when asked for
    local more = { S.moreConds == true }
    if g.Checkbox('More conditions##gsq-more', more) then
        S.moreConds = more[1]
    end

    tooltip('Also offer the advanced conditions: skillchain and magic burst windows (target Enemy), level, timer and random.')

    label('Action')
    width(s(160))
    local kinds = {}
    for _, k in ipairs(M.NEW_KINDS) do
        kinds[#kinds + 1] = k
    end

    local kind = combo('##gsq-kind', r.kind, kinds, M.kind_label, function(v) return M.KIND_HELP[v or ''] end)
    if kind ~= r.kind then
        M.set_action(r, kind)
    end

    tooltip(M.KIND_HELP[r.kind or ''] or 'What the squad mate does.')

    name_picker(r, cat)
    local spellNote = M.action_note(r, cat, M.mate())
    if spellNote then
        if g.SetCursorPosX then
            g.SetCursorPosX(labelW)
        end

        wrapped(M.theme.gold, spellNote)
    end

    label('Then wait')
    local hasRetry = { r.retry ~= nil and r.retry ~= '' }
    if g.Checkbox('##gsq-retry-on', hasRetry) then
        r.retry = hasRetry[1] and '30' or nil
    end

    tooltip('After the action, this rule is skipped for this many seconds.')
    if r.retry ~= nil and r.retry ~= '' then
        same()
        width(s(110))
        r.retry = int_input('##gsq-retry', r.retry)
        same(s(3))
        g.Text('seconds before repeating')
    else
        same()
        note('no wait')
    end

    if r.level ~= nil then
        label('From level')
        note(tostring(r.level) .. ' (kept from the saved rule)')
    end
    end)

    if readonly then
        -- (without BeginDisabled the controls still move; nothing may change)
        local back = M.decode_rule(before)
        for k in pairs(r) do
            r[k] = nil
        end

        for k, v in pairs(back) do
            r[k] = v
        end
    elseif M.encode_rule(r) ~= before then
        d.dirty, S.checks = true, {}
    end
end
-- The rule list: order, on/off, a readable line per rule, the selected one highlighted
local function rule_list(d, cat, readonly, height)
    local g = imgui()
    child('##gsq-rules', { 0, height }, function()
        if #d.rules == 0 then
            note('No rules yet. Press Add rule.')
        end

        for i, r in ipairs(d.rules) do
            g.PushID('gsq-rule-' .. i)
            scoped(nil, function() g.PopID() end, function()
            if r.opaque then
                colored(M.theme.bad, '[kept]')
                tooltip('This rule uses options this editor cannot show. It is kept exactly as it is.')
            else
                local on = { r.on ~= false }
                if g.Checkbox('##on', on) and not readonly then
                    r.on = on[1]
                    d.dirty = true
                end

                tooltip(r.on ~= false and 'On: the mate uses this rule.' or 'Off: skipped.')
            end

            same()
            local text = string.format('%d. %s', i, M.rule_short(r, cat)) -- (compact; the full wording is the tooltip)
            local full = string.format('%d. %s', i, M.rule_summary(r, cat))
            local selected = S.sel == i
            local list = { { 'ImGuiCol_Text', r.on == false and M.theme.muted or nil } }
            if selected then
                list[#list + 1] = { 'ImGuiCol_Header', M.theme.rowSel }
                list[#list + 1] = { 'ImGuiCol_HeaderHovered', times(M.theme.rowSel, 1.25) }
            end

            with_colors(list, function()
                if g.Selectable(text .. '##sel', selected) then
                    S.sel = i
                end
            end)

            tooltip(full) -- (the full wording, also when the panel is too narrow for the line)
            if S.checks[i] then
                wrapped(M.theme.bad, 'Rule ' .. i .. ' is left out for this mate now: ' .. M.readable(S.checks[i]))
            end
            end)
        end
    end)
end

local function sets_panel(mate, listH)
    local g = imgui()
    heading(mate.job .. ' Rule Sets')
    wrapped(M.theme.secondary, string.format('%s uses: %s', mate.name, mate.chosen > 0 and M.set_label(mate.chosen) or 'default job rules'))
    child('##gsq-sets', { 0, listH or s(150) }, function()
        if #S.sets == 0 then
            note('No ' .. mate.job .. ' Rule Sets yet. Press New.')
        end

        for _, set in ipairs(S.sets) do
            local mine = string.find(set.flags, 'o', 1, true) ~= nil
            local ro = string.find(set.flags, 'r', 1, true) ~= nil
            local label = string.format('%d  %s%s', set.num, set.name, set.num == mate.chosen and '   (in use)' or '')
            local selected = S.selectedSet == set.num
            local list = {}
            if selected then
                list = { { 'ImGuiCol_Header', M.theme.rowSel }, { 'ImGuiCol_HeaderHovered', times(M.theme.rowSel, 1.25) } }
            end

            with_colors(list, function()
                if g.Selectable(label .. '##gsq-set-' .. set.num, selected) then
                    M.select_set(set.num) -- (one click selects and opens it)
                end
            end)

            tooltip(string.format('Rule Set %d: %s\n%d rules, %s%s', set.num, set.name, set.rules,
                mine and 'yours' or 'written by hand (copy it to change it)', ro and ', read-only' or ''))
        end
    end)

    local sel
    for _, set in ipairs(S.sets) do
        if set.num == S.selectedSet then
            sel = set
        end
    end

    if button('New##gsq-new') then
        M.new_set(mate.job)
        S.sel = 1
    end

    tooltip('A new ' .. mate.job .. ' Rule Set (saved only when you press Save).')
    for i, t in ipairs(M.templates_for(mate.job)) do
        same_if_fits(s(150))
        if button('Starter: ' .. t.name .. '##gsq-tpl' .. i) then
            local made, why = M.new_from_template(mate.job, i, S.cat)
            if made == nil then
                say(why, false)
            end

            S.sel = 1
        end

        tooltip(t.about .. '\n\nOptional: it only fills a new, unsaved Rule Set to look at and change. Saving, assigning and '
            .. 'applying stay your choice. Once assigned, a Rule Set replaces ' .. mate.name .. '\'s usual job rules; the built-in '
            .. 'rules are never changed and "Restore default job rules" goes back to them.')
    end

    if S.confirmOpen then
        wrapped(M.theme.gold, string.format('"%s" has unsaved changes. Open %s anyway? Your changes are kept as the unsaved draft.',
            S.draft and S.draft.name or '?', M.set_label(S.confirmOpen)))
        if button('Open it##gsq-confirm-open') then M.confirm_open(true) end
        same_if_fits(s(110))
        if button('Keep editing##gsq-confirm-keep') then M.confirm_open(false) end
    end

    if sel then
        same_if_fits(s(60))
        if button('Copy##gsq-copy') then
            M.open_set(sel.num, true)
            S.sel = 1
        end

        tooltip('A new set of your own with the same rules.')
        if string.find(sel.flags, 'o', 1, true) and not string.find(sel.flags, 'r', 1, true) then
            same_if_fits(s(110))
            if S.confirmDelete == sel.num then
                with_colors({ { 'ImGuiCol_Button', M.theme.bad }, { 'ImGuiCol_ButtonHovered', times(M.theme.bad, 1.15) } }, function()
                    if button('Really delete?##gsq-del2') then
                        S.confirmDelete = nil
                        M.delete_set(sel.num, sel.rev)
                    end
                end)
            elseif button('Delete##gsq-del') then
                S.confirmDelete = sel.num
            end
        end
    end

    g.Separator()
    heading('Use it')
    if sel then
        if button('Assign & Apply##gsq-assign') then M.assign_apply(mate.slot, sel.num) end
        tooltip(string.format('Use the saved "%s" for %s now: assigns it (!squad ruleset) and, when %s is summoned, calls '
            .. 'the squad again (!squad reapply). Unsaved changes are not included: Save first.', sel.name, mate.name, mate.name))
        local checkLabel = mate.out and 'Check' or ('Check (' .. mate.name .. ' not summoned)')
        same_if_fits(s(80))
        if button(checkLabel .. '##gsq-check') then M.check_set(mate.slot, sel.num) end
        tooltip('Which rules ' .. mate.name .. ' would leave out now, and why. The server checks with ' .. mate.name
            .. '\'s current level and sub job, so ' .. mate.name .. ' must be called (out).'
            .. (mate.out and '' or ('\nThe last Refresh showed ' .. mate.name .. ' not summoned: summon ' .. mate.name .. ', press Refresh, then Check.'))
            .. ' Check never summons anyone.')
    end

    if button('Restore default job rules##gsq-off') then M.assign(mate.slot, nil, true) end
    tooltip(mate.name .. ' stops using its Rule Set and goes back to the usual ' .. mate.job .. ' job rules (applied at once '
        .. 'when summoned). Your saved Rule Sets are kept.')
    -- (the separate "Apply now" button is gone: Assign & Apply also re-calls a mate after its set was changed and saved)
    local r = S.restorable
    if r and r.job == mate.job and not (S.draft and S.draft.dirty) then
        if button('Restore unsaved draft##gsq-restore') then
            S.draft, S.restorable, S.sel = r, nil, 1
        end

        tooltip('Your unsaved changes to "' .. tostring(r.name) .. '".')
    end
end

local function editor_panel(height)
    local g = imgui()
    local d = S.draft
    if d == nil then
        heading('Rules')
        note('Click a Rule Set to open it, or press New or a Starter. Edits stay here until you press Save.')
        return
    end

    if S.cat == nil then
        if S.catError then
            colored(M.theme.bad, 'The choices from the server were incomplete (' .. S.catError .. '). Press Refresh.')
        else
            note('Loading the choices from the server...')
        end

        return
    end

    local readonly = d.readonly == true
    if S.sel == nil or d.rules[S.sel] == nil then
        S.sel = #d.rules > 0 and 1 or nil
    end

    -- (beta polish) always say what is being edited, by name, and for which job
    local title = (d.name and d.name ~= '' and ('"' .. d.name .. '"') or 'New Rule Set') .. ' (' .. tostring(d.job) .. (d.num > 0 and (', #' .. d.num) or ', new') .. ')'
    heading(readonly and ('Viewing ' .. title .. ' - read-only: Copy it to change it')
        or ('Editing ' .. title .. (d.dirty and '  - not saved' or '')))
    local m = M.mate()
    if m and d.job ~= m.job then
        wrapped(M.theme.gold, string.format('This is a %s Rule Set; %s is %s now.', tostring(d.job), m.name, m.job))
    end
    same_if_fits(s(100))
    colored(#d.rules >= M.MAX_RULES and M.theme.gold or M.theme.secondary, string.format('%d of %d rules', #d.rules, M.MAX_RULES))
    if not readonly then
        same_if_fits(s(180))
        width(math.max(s(180), math.min(s(320), available() - s(4))))
        local name = text_field('##gsq-setname', d.name, M.NAME_MAX + 1)
        if name ~= d.name then
            d.name, d.dirty = name, true
        end

        tooltip('The name of this Rule Set (letters, digits, spaces, -).')
    end

    if d.uneditable then
        wrapped(M.theme.bad, 'Rules marked [kept] use options this editor cannot show. They are kept exactly as they are, '
            .. 'so this set is read-only here.')
    end

    rule_list(d, S.cat, readonly, height)
    if not readonly then
        if button('Add rule##gsq-add') then S.sel = M.add_rule(d, S.sel) end
        same_if_fits(s(40))
        if button('Up##gsq-up') then S.sel = M.move_rule(d, S.sel, -1) end
        same_if_fits(s(50))
        if button('Down##gsq-down') then S.sel = M.move_rule(d, S.sel, 1) end
        same_if_fits(s(70))
        if button('On / off##gsq-toggle') then M.toggle_rule(d, S.sel) end
        same_if_fits(s(70))
        if button('Remove##gsq-remove') then
            S.sel, S.checks = M.remove_rule(d, S.sel), {}
        end
    end

    g.Separator()
    local r = S.sel and d.rules[S.sel]
    if r then
        heading(string.format('Selected rule %d: Target -> Conditions -> Action', S.sel))
        rule_editor(d, r, S.cat, readonly)
        wrapped(M.theme.secondary, M.rule_summary(r, S.cat))
    end

    if not readonly and not d.uneditable then
        local busy = M.busy()
        with_colors({ { 'ImGuiCol_Button', M.theme.goGold }, { 'ImGuiCol_ButtonHovered', times(M.theme.goGold, 1.15) },
                      { 'ImGuiCol_Text', M.theme.goText } }, function()
            if button((busy and 'Wait...' or (d.dirty and 'Save *' or 'Save')) .. '##gsq-save', s(110)) and not busy then
                M.save()
            end
        end)

        tooltip(busy and 'The editor is talking to the server; Save is possible again in a moment.'
            or 'Send this Rule Set to the server, which checks and stores it.')
    end
end

-- The Weapon Skills section (server version 5): one squad mate, its current main job
local function ws_panel(mate)
    local g = imgui()
    heading('Weapon Skills: ' .. mate.name .. ' (' .. mate.job .. ')')
    note('Separate from Rule Sets: a Rule Set never changes these, and these never change a Rule Set.')
    if not M.ws_supported() then
        wrapped(M.theme.gold, 'This needs the server update (gambits_squad.lua version 5).')
        return
    end

    local w = S.ws
    if w == nil or w.slot ~= mate.slot then
        if not M.busy() then
            M.ws_load(mate.slot)
        end

        note('Loading...')
        return
    end

    if w.error then
        colored(M.theme.bad, 'Could not load them: ' .. M.readable(w.error))
        if button('Try again##gsq-ws-retry') then S.ws = nil end
        return
    end

    local d, e = w.data, w.edit
    if d == nil or e == nil then
        note('Loading...')
        return
    end

    -- what is stored now
    local stored
    if d.source == 'c' then
        stored = string.format('Custom: %s%s, %s.', M.WS_MODES[d.mode] or '?', d.mode == 2 and '' or (' at ' .. d.tp .. ' TP'), M.ws_name(d.ws))
    elseif d.source == 'd' then
        stored = 'Squad default (automatic skillchains, every weapon skill).'
    else
        stored = 'No Gambits setting yet: the squad\'s own behaviour'
        if (d.legacyTp or 0) > 0 or (d.legacyWs or 0) > 0 then
            stored = stored .. string.format(' with your !squad ws choice (%s, %s).', d.legacyTp > 0 and (d.legacyTp .. ' TP') or 'skillchains',
                M.ws_name(d.legacyWs))
        else
            stored = stored .. ' (automatic skillchains).'
        end
    end

    wrapped(M.theme.secondary, 'Saved: ' .. stored)
    if not d.engine then
        wrapped(M.theme.gold, 'Custom needs the updated map server (xi_map); only Squad default can be used here.')
    end

    if d.usable == false then
        wrapped(M.theme.bad, string.format('%s cannot use %s now (weapon, skill level or quest): it uses Best available until it '
            .. 'can. Your choice is kept.', mate.name, M.ws_name(d.ws)))
    end

    if not d.out then
        wrapped(M.theme.secondary, mate.name .. ' is not summoned: saved settings apply when called. Summon ' .. mate.name
            .. ' and press Refresh to choose a specific weapon skill.')
    elseif d.applied == false then
        wrapped(M.theme.gold, 'Saved but not in use yet: press Apply WS settings now.')
    end

    g.Separator()
    local labelW = s(110)
    local function label(text)
        label_text(text)
        g.SameLine(labelW)
    end

    label('Control')
    width(s(200))
    local control = combo('##gsq-ws-ctl', e.control, { 0, 1 }, function(v) return v == 1 and 'Custom' or 'Squad default' end,
        function(v) return v == 1 and 'Your own mode, TP and weapon skill.' or 'The automatic party skillchains (as without Gambits).' end)
    if control ~= e.control and (control == 0 or d.engine) then
        e.control = control
    end

    if e.control == 1 then
        label('Mode')
        width(s(200))
        e.mode = combo('##gsq-ws-mode', e.mode, { 1, 2, 3, 4 }, function(v) return M.WS_MODES[v] or '?' end,
            function(v) return M.WS_MODE_HELP[v] end)
        tooltip(M.WS_MODE_HELP[e.mode] or '')
        if g.SetCursorPosX then
            g.SetCursorPosX(labelW)
        end

        wrapped(M.theme.secondary, M.WS_MODE_HELP[e.mode] or '')
        if e.mode ~= 2 then
            label(e.mode == 4 and 'TP' or 'TP to open')
            width(s(120))
            e.tp = combo('##gsq-ws-tp', e.tp, M.WS_TPS, function(v) return tostring(v) end)
            if e.mode == 3 then
                same()
                note('(opening only: closing is allowed from 1000 TP)')
            end
        end

        label('Weapon skill')
        width(s(240))
        local ids = { 0 }
        local inList = e.ws == 0
        for _, it in ipairs(w.list or {}) do
            ids[#ids + 1] = it.id
            inList = inList or it.id == e.ws
        end

        if not inList then
            ids[#ids + 1] = e.ws -- (the saved choice stays selectable, even when not in the list now)
        end

        e.ws = combo('##gsq-ws-ws', e.ws, ids, M.ws_name, function(v) return v == 0 and M.WS_BEST_HELP or nil end)
        tooltip(e.ws == 0 and M.WS_BEST_HELP or ('Only ' .. M.ws_name(e.ws) .. ' (when the mate can use it; otherwise Best available).'))
        if w.list == nil then
            same()
            note(d.out and '(loading the list...)' or '(summon to see the list)')
        elseif not inList then
            same()
            colored(M.theme.bad, '(not usable now)')
        end

        if g.SetCursorPosX then
            g.SetCursorPosX(labelW)
        end

        note(M.WS_3000_HELP)
    end

    g.Separator()
    local dirty = M.ws_dirty()
    with_colors({ { 'ImGuiCol_Button', M.theme.goGold }, { 'ImGuiCol_ButtonHovered', times(M.theme.goGold, 1.15) },
                  { 'ImGuiCol_Text', M.theme.goText } }, function()
        if button((dirty and 'Save *' or 'Save') .. '##gsq-ws-save', s(90)) then
            M.ws_save(mate.slot, e)
        end
    end)
    tooltip('Store these settings for ' .. mate.name .. ' as ' .. mate.job .. ' (the server checks them).')
    same_if_fits(s(100))
    if button('Apply WS settings now##gsq-ws-apply') then M.ws_apply(mate.slot) end
    tooltip('Use the saved settings on ' .. mate.name .. ' now, without calling again (' .. mate.name .. ' must be summoned).')
    same_if_fits(s(170))
    if button('Reset to Squad default##gsq-ws-reset') then M.ws_reset(mate.slot) end
    tooltip('Back to the automatic skillchains for ' .. mate.job .. '. Your Custom choices are kept for later. Then Apply WS settings now.')
    same_if_fits(s(70))
    if button('Refresh##gsq-ws-refresh') then S.ws = nil end
end
M.ws_panel = ws_panel

function M.draw()
    local g = imgui()
    if g == nil then
        return
    end

    if S.server == nil and not S.refreshing then
        S.refreshing = true
        M.refresh()
    end

    if S.server == false then
        heading('Squad Rule Sets')
        wrapped(nil, 'The Squad editor needs the server update with !gsq (gambits_squad.lua version ' .. M.MIN_SERVER .. ')'
            .. (S.serverWhy and (': ' .. S.serverWhy) or '') .. '.')
        if button('Try again##gsq-retry') then
            S.server = nil
            S.refreshing = false
        end

        return
    end

    -- the header: squad mate, Refresh, Ping, theme and size (controls move to a new line when the window is narrow)
    label_text('Squad mate')
    same()
    width(math.max(s(180), math.min(s(280), available() - s(10))))
    local labels, slots = {}, {}
    for _, m in ipairs(S.mates) do
        labels[m.slot] = string.format('%d  %s  %s %d%s%s', m.slot, m.name, m.job, m.level,
            m.sub and (' / ' .. m.sub .. (m.subLevel and (' ' .. m.subLevel) or '')) or '', m.out and '' or '  (not summoned)')
        slots[#slots + 1] = m.slot
    end

    local picked = combo('##gsq-mate', S.mateSlot, slots, function(v) return labels[v] or tostring(v) end)
    if picked ~= S.mateSlot then
        M.switch_mate(picked) -- (beta polish: the new mate's own Rule Set, never the previous mate's; unsaved edits kept)
    end

    same_if_fits(s(70))
    if button('Refresh##gsq-refresh') then
        S.ws = nil -- (the Weapon Skills section loads again too)
        M.load_mates()
    end
    tooltip('Ask the server again for your squad and its Rule Sets.')
    same_if_fits(s(50))
    if button('Ping##gsq-ping') then M.ping(10) end
    tooltip('Measure 10 round trips to the server (and whether the game refused any line).')
    same_if_fits(s(170))
    label_text('Theme')
    same()
    width(s(110))
    local theme = combo('##gsq-theme', M.themeName, M.THEME_ORDER, function(v) return M.THEME_NAMES[v] or v end)
    if theme ~= M.themeName then
        M.set_theme(theme)
        if api.on_theme then
            api.on_theme(theme)
        end
    end

    if api.get_scale and api.set_scale then
        local scale = api.get_scale()
        same_if_fits(s(150))
        label_text('Size')
        same()
        if button('-##gsq-scale-down') and scale > 70 then api.set_scale(scale - 10) end
        tooltip('Smaller text and controls (70-200 %).')
        same(s(4))
        if button(string.format('%d%%##gsq-scale-reset', scale)) then api.set_scale(100) end
        tooltip('Back to 100 %.')
        same(s(4))
        if button('+##gsq-scale-up') and scale < 200 then api.set_scale(scale + 10) end
        tooltip('Larger text and controls (70-200 %).')
    end

    -- the two panels take the room that is left, above a status area of about three lines (wrapped, never cut)
    local mate = M.mate()
    local statusH = s(58)
    if mate == nil then
        wrapped(M.theme.secondary, #S.mates == 0 and 'No squad mates yet. Make one with !squad new <name> <job>.' or 'Loading your squad...')
    else
        local total = available()
        local panelH = math.max(s(260), available_h() - statusH)
        local leftW = math.floor(math.max(s(240), math.min(total * 0.36, total - s(380))))
        local setsH = math.max(s(80), panelH - s(250))
        local rulesH = math.max(s(90), math.floor((panelH - s(120)) * 0.38))
        with_colors({ { 'ImGuiCol_Border', M.theme.border } }, function()
            child('##gsq-left', { leftW, panelH }, function() sets_panel(mate, setsH) end)
            same()
            child('##gsq-right', { 0, panelH }, function()
                -- (version 5) Rules or Weapon Skills on the right
                if M.ws_supported() then
                    for _, v in ipairs({ { 'rules', 'Rule Set editor' }, { 'ws', 'Weapon Skills' } }) do
                        local on = (S.view or 'rules') == v[1]
                        with_colors(on and { { 'ImGuiCol_Button', M.theme.tabSel } } or {}, function()
                            if button(v[2] .. '##gsq-view-' .. v[1]) then
                                S.view = v[1]
                            end
                        end)
                        same()
                    end

                    g.NewLine()
                end

                if S.view == 'ws' and M.ws_supported() then
                    ws_panel(mate)
                else
                    editor_panel(rulesH - (M.ws_supported() and s(28) or 0))
                end
            end)
        end)
    end

    if S.progress then
        wrapped(M.theme.secondary, S.progress)
    elseif S.message then
        wrapped(S.messageWarn and M.theme.gold or (S.messageOk and M.theme.ok or M.theme.bad), M.readable(S.message))
    end
end
return M
