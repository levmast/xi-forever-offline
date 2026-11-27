--[[
Gambits share codes (0.3.3): a whole Rule Set as one short code of letters and digits, to paste into Discord or a message.

    GS1 + Base58( payload )

Base58 is Bitcoin's alphabet: digits and letters without 0, O, I and l, so a code survives chat, copying and reading
aloud; there are no characters chat programs turn into formatting. The payload is a small bit stream:

    job (5 bits), name (text), rule count (6 bits), the name pool, the rules, a check number (32 bits)

Each rule: on (1 bit), target, role filter (1 bit + 4 + 4 bits: included / excluded roles), condition and its value,
second condition and its value, action kind (3 bits), action name, wait, level, id. A field is a token: 0 = empty,
1 = a whole number (then its value), 2.. = a word of the fixed VOCABULARY below (targets and conditions), then the name
pool - every other text (spell, ability, family and effect names, "MARCH.2", rule ids) written once in the pool, so a
name used by several rules costs its letters once. Texts use 6 bits a character (A-Z 0-9 _ . - space a-w), anything
else is escaped. The check number (the editor's M.check over the payload bytes) refuses a code that was cut or changed.

Decoding never runs anything: it reads bits and builds the editor's plain rule rows, which the editor then checks like
any typed rule. Unknown versions, bad characters, a wrong check number, a payload that ends early or has data left over,
and codes longer than MAX_CODE are refused with a reason.

VOCABULARY (format 1) must never be reordered or shortened: new words go to a new format version.
]]

local C = {}
C.PREFIX = 'GS'
C.VERSION = 2       -- the newest format this file writes and reads (it reads 1 too)
C.MAX_CODE = 6000   -- characters of one code (32 of the longest rules are far below this)
C.MAX_RULES = 32

-- (format 2, 2026-11-27: F22 / F10 / F18) each rule also carries one bit "more": when set, conditions 3 and 4 with their
-- values (tokens), the subject of each of the four conditions (2 bits: 0 the rule's target, 1 self, 2 its enemy) and Wake to
-- act (1 bit). The action kind may be burstcap (index 7). A Rule Set that uses none of these is written as format 1, exactly
-- as before, so an older Gambits still reads it; a format 2 code is refused by an older Gambits with "update Gambits".
C.SUBJECTS = { 'SELF', 'ENEMY' } -- 1, 2 (0 = the rule's target)

C.JOBS = { 'WAR', 'MNK', 'WHM', 'BLM', 'RDM', 'THF', 'PLD', 'DRK', 'BST', 'BRD', 'RNG', 'SAM', 'NIN', 'DRG', 'SMN', 'BLU',
           'COR', 'PUP', 'DNC', 'SCH', 'GEO', 'RUN' }
C.KINDS = { 'family', 'spell', 'ja', 'ranged', 'nuke', 'burst', 'burstcap' } -- (burstcap: format 2 only)
C.ROLES = { 'TANK', 'MELEE', 'CASTER', 'RANGED' }
C.VOCABULARY = {
    -- targets
    'SELF', 'PARTY', 'PARTY_LOWEST_HPP', 'TANK', 'CASTER', 'MELEE', 'RANGED', 'TOP_ENMITY', 'TARGET', 'MASTER',
    'TRIGGER_SELF_ACTION_TARGET', 'TRIGGER_TARGET_ACTION_SELF', 'PARTY_DEAD', 'PARTY_MULTI',
    -- conditions (gambits_container.h G_CONDITION)
    'ALWAYS', 'HPP_LT', 'HPP_GTE', 'MPP_LT', 'MPP_GTE', 'TP_LT', 'TP_GTE', 'LVL_LT', 'LVL_GTE', 'STATUS', 'NOT_STATUS',
    'STATUS_FLAG', 'HAS_TOP_ENMITY', 'NOT_HAS_TOP_ENMITY', 'SC_AVAILABLE', 'NOT_SC_AVAILABLE', 'MB_AVAILABLE',
    'READYING_WS', 'READYING_MS', 'READYING_JA', 'CASTING_MA', 'CASTING_DEBUFF', 'RANDOM', 'NO_SAMBA', 'NO_STORM',
    'PT_HAS_TANK', 'NOT_PT_HAS_TANK', 'IS_ECOSYSTEM', 'HP_MISSING', 'CASTING_ELEMENT_MA', 'CAST_ELE_MA_SELF',
    'CASTING_ELE_MA_AOE', 'NEED_ELE_BAREFFECT', 'NO_MAX_RUNE', 'HAS_RUNES', 'LUNGE_MB_AVAILABLE', 'SUB_ANIMATION',
    'JA_ON_COOLDOWN', 'VAL_URIEL_CHECK', 'TIMER', 'HAS_MP', 'HAS_MP_MPP_LT', 'HAS_MP_MPP_GTE', 'MOD_LT',
}
C.TEXT = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_.- abcdefghijklmnopqrstuvw' -- 63 characters; code 63 = escape + 8 bits
C.B58 = '123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz'

local function indexOf(list)
    local t = {}
    for i, v in ipairs(list) do
        t[v] = i
    end

    return t
end

local JOB_IX, KIND_IX, ROLE_IX, VOCAB_IX = indexOf(C.JOBS), indexOf(C.KINDS), indexOf(C.ROLES), indexOf(C.VOCABULARY)
local TEXT_IX = {}
for i = 1, #C.TEXT do
    TEXT_IX[C.TEXT:sub(i, i)] = i - 1
end

local B58_IX = {}
for i = 1, #C.B58 do
    B58_IX[C.B58:sub(i, i)] = i - 1
end

-- the editor's check number (squad_editor.lua M.check / gambits_squad.lua G.check), over bytes
local function check(bytes)
    local h = 7
    for i = 1, #bytes do
        h = (h * 31 + bytes[i]) % 1000000007
    end

    return h
end
C.check = check

-- ---------------------------------------------------------------- bits (plain arithmetic: LuaJIT and Lua 5.4 alike)
local function writer()
    local w = { bytes = {}, acc = 0, n = 0 }
    function w.bits(count, value)
        assert(value >= 0 and value < 2 ^ count and value == math.floor(value), 'value does not fit')
        for i = count - 1, 0, -1 do
            local bit = math.floor(value / 2 ^ i) % 2
            w.acc, w.n = w.acc * 2 + bit, w.n + 1
            if w.n == 8 then
                w.bytes[#w.bytes + 1], w.acc, w.n = w.acc, 0, 0
            end
        end
    end

    function w.varint(value) -- 4 bits a group, with a continuation bit: small numbers stay small
        repeat
            local part = value % 16
            value = math.floor(value / 16)
            w.bits(1, value > 0 and 1 or 0)
            w.bits(4, part)
        until value == 0
    end

    function w.text(s)
        local symbols = {}
        for i = 1, #s do
            local c = s:sub(i, i)
            if TEXT_IX[c] then
                symbols[#symbols + 1] = { 6, TEXT_IX[c] }
            else
                symbols[#symbols + 1] = { 6, 63 }
                symbols[#symbols + 1] = { 8, s:byte(i) }
            end
        end

        w.varint(#s)
        for _, sym in ipairs(symbols) do
            w.bits(sym[1], sym[2])
        end
    end

    function w.finish()
        if w.n > 0 then
            w.bits(8 - w.n, 0)
        end

        return w.bytes
    end

    return w
end

local function reader(bytes, limitBits)
    local r = { pos = 0 }
    function r.bits(count)
        local v = 0
        for _ = 1, count do
            if r.pos >= limitBits then
                error('the code ends too early (it was cut)', 0)
            end

            local byte = bytes[math.floor(r.pos / 8) + 1]
            local bit = math.floor(byte / 2 ^ (7 - r.pos % 8)) % 2
            v, r.pos = v * 2 + bit, r.pos + 1
        end

        return v
    end

    function r.varint()
        local v, scale = 0, 1
        for _ = 1, 8 do
            local more = r.bits(1)
            v, scale = v + r.bits(4) * scale, scale * 16
            if more == 0 then
                return v
            end
        end

        error('a number in the code is too long', 0)
    end

    function r.text(max)
        local n = r.varint()
        if n > max then
            error('a text in the code is too long', 0)
        end

        local out = {}
        for i = 1, n do
            local sym = r.bits(6)
            out[i] = sym == 63 and string.char(r.bits(8)) or C.TEXT:sub(sym + 1, sym + 1)
        end

        return table.concat(out)
    end

    return r
end

-- ---------------------------------------------------------------- Base58 (big-number conversion; leading zero bytes = '1')
function C.base58(bytes)
    local digits, zeros = {}, 0 -- (digits little-endian)
    while zeros < #bytes and bytes[zeros + 1] == 0 do
        zeros = zeros + 1
    end

    for i = 1, #bytes do
        local carry = bytes[i]
        for j = 1, #digits do
            carry = carry + digits[j] * 256
            digits[j] = carry % 58
            carry = math.floor(carry / 58)
        end

        while carry > 0 do
            digits[#digits + 1] = carry % 58
            carry = math.floor(carry / 58)
        end
    end

    local out = {}
    for _ = 1, zeros do
        out[#out + 1] = '1'
    end

    for i = #digits, 1, -1 do
        out[#out + 1] = C.B58:sub(digits[i] + 1, digits[i] + 1)
    end

    return table.concat(out)
end

function C.unbase58(text)
    local bytes, zeros = {}, 0 -- (bytes little-endian)
    while zeros < #text and text:sub(zeros + 1, zeros + 1) == '1' do
        zeros = zeros + 1
    end

    for i = 1, #text do
        local carry = B58_IX[text:sub(i, i)]
        if carry == nil then
            return nil, 'the code has a character a share code never has (' .. text:sub(i, i) .. ')'
        end

        for j = 1, #bytes do
            carry = carry + bytes[j] * 58
            bytes[j] = carry % 256
            carry = math.floor(carry / 256)
        end

        while carry > 0 do
            bytes[#bytes + 1] = carry % 256
            carry = math.floor(carry / 256)
        end
    end

    local out = {}
    for _ = 1, zeros do
        out[#out + 1] = 0
    end

    for i = #bytes, 1, -1 do
        out[#out + 1] = bytes[i]
    end

    return out
end

-- ---------------------------------------------------------------- the Rule Set
local FIELDS = { 'cond', 'arg', 'cond2', 'arg2' }
local MORE_FIELDS = { 'cond3', 'arg3', 'cond4', 'arg4' } -- (format 2)
local SUBJECT_KEYS = { 'of1', 'of2', 'of3', 'of4' }
local SUBJECT_IX = indexOf(C.SUBJECTS)

-- (format 2) does this row use anything format 1 cannot carry?
local function needsMore(r)
    if r.cond3 ~= nil or r.cond4 ~= nil or r.wake == true then
        return true
    end

    for _, key in ipairs(SUBJECT_KEYS) do
        if r[key] ~= nil then
            return true
        end
    end

    return false
end
C.needsMore = needsMore

local function isNumberText(s)
    return type(s) == 'string' and string.match(s, '^[1-9]%d*$') ~= nil and #s <= 9 or s == '0'
end

-- d = { job, name, rules = editor rows } -> the code, or nil + why
function C.encode(d)
    if type(d) ~= 'table' or type(d.rules) ~= 'table' or #d.rules == 0 or #d.rules > C.MAX_RULES then
        return nil, 'a Rule Set has 1-' .. C.MAX_RULES .. ' rules'
    end

    if JOB_IX[d.job or ''] == nil then
        return nil, 'unknown job ' .. tostring(d.job)
    end

    local pool, poolIx = {}, {}
    local function poolAdd(s)
        if s ~= nil and s ~= '' and not VOCAB_IX[s] and not isNumberText(s) and not poolIx[s] then
            pool[#pool + 1] = s
            poolIx[s] = #pool
        end
    end

    -- (format 2) only when a rule needs it: otherwise the code is format 1, byte for byte as before
    local version = 1
    for _, r in ipairs(d.rules) do
        if needsMore(r) or r.kind == 'burstcap' then
            version = 2
        end
    end

    for i, r in ipairs(d.rules) do
        if r.opaque or KIND_IX[r.kind or ''] == nil then
            return nil, 'rule ' .. i .. ' cannot be shared exactly'
        end

        for _, key in ipairs(SUBJECT_KEYS) do
            if r[key] ~= nil and SUBJECT_IX[r[key]] == nil then
                return nil, 'rule ' .. i .. ': unknown condition subject ' .. tostring(r[key])
            end
        end

        for _, key in ipairs({ 'target', 'cond', 'arg', 'cond2', 'arg2', 'cond3', 'arg3', 'cond4', 'arg4', 'name', 'retry', 'level', 'id' }) do
            local v = r[key]
            if v ~= nil and type(v) ~= 'string' then
                return nil, 'rule ' .. i .. ': ' .. key .. ' is not text'
            end

            poolAdd(v)
        end
    end

    local w = writer()
    w.bits(5, JOB_IX[d.job] - 1)
    w.text(d.name or '')
    w.bits(6, #d.rules - 1)
    w.varint(#pool)
    for _, s in ipairs(pool) do
        w.text(s)
    end

    local function token(v)
        if v == nil or v == '' then
            w.varint(0)
        elseif isNumberText(v) then
            w.varint(1)
            w.varint(tonumber(v))
        elseif VOCAB_IX[v] then
            w.varint(1 + VOCAB_IX[v])
        else
            w.varint(1 + #C.VOCABULARY + poolIx[v])
        end
    end

    local function roleBits(list)
        local bits = 0
        for role in string.gmatch(list or '', '[^%.]+') do
            local ix = ROLE_IX[role]
            if ix == nil then
                return nil
            end

            bits = bits + 2 ^ (ix - 1)
        end

        return bits
    end

    for i, r in ipairs(d.rules) do
        w.bits(1, r.on == false and 0 or 1)
        token(r.target)
        local inc, exc = roleBits(r.rolesIn), roleBits(r.rolesOut)
        if inc == nil or exc == nil then
            return nil, 'rule ' .. i .. ' has an unknown role'
        end

        if inc + exc > 0 then
            w.bits(1, 1)
            w.bits(4, inc)
            w.bits(4, exc)
        else
            w.bits(1, 0)
        end

        for _, key in ipairs(FIELDS) do
            token(r[key])
        end

        w.bits(3, KIND_IX[r.kind] - 1)
        token(r.name)
        token(r.retry)
        token(r.level)
        token(r.id)
        if version >= 2 then
            local more = needsMore(r)
            w.bits(1, more and 1 or 0)
            if more then
                for _, key in ipairs(MORE_FIELDS) do
                    token(r[key])
                end

                for _, key in ipairs(SUBJECT_KEYS) do
                    w.bits(2, r[key] and SUBJECT_IX[r[key]] or 0)
                end

                w.bits(1, r.wake == true and 1 or 0)
            end
        end
    end

    local bytes = w.finish()
    local h = check(bytes)
    for i = 3, 0, -1 do
        bytes[#bytes + 1] = math.floor(h / 256 ^ i) % 256
    end

    local code = C.PREFIX .. version .. C.base58(bytes)
    if #code > C.MAX_CODE then
        return nil, 'the Rule Set is too large for one code'
    end

    return code
end

-- true when the (cleaned) text looks like a share code (GS<digits>...), so the editor knows which reader to use
function C.looks_like(text)
    return type(text) == 'string' and string.match(text, '^' .. C.PREFIX .. '%d') ~= nil and not string.find(text, '|', 1, true)
end

-- the code (spaces, line breaks and ` around or inside are ignored) -> { job, name, rules = editor rows }, or nil + why
function C.decode(text)
    if type(text) ~= 'string' then
        return nil, 'nothing to read'
    end

    local clean = string.gsub(text, '[%s`]', '')
    if #clean > C.MAX_CODE then
        return nil, 'the code is longer than any Rule Set code (' .. #clean .. ' characters)'
    end

    local version, body = string.match(clean, '^' .. C.PREFIX .. '(%d)(.*)$')
    if version == nil then
        return nil, 'this is not a Gambits share code (it starts with ' .. C.PREFIX .. C.VERSION .. ')'
    end

    local format = tonumber(version)
    if format < 1 or format > C.VERSION then
        return nil, string.format('this code was made by a newer Gambits (format %s); this one reads formats 1-%d: update Gambits',
            version, C.VERSION)
    end

    if #body < 6 then
        return nil, 'the code is too short (it was cut)'
    end

    local bytes, why = C.unbase58(body)
    if bytes == nil then
        return nil, why
    end

    if #bytes < 5 then
        return nil, 'the code is too short (it was cut)'
    end

    local payload = {}
    for i = 1, #bytes - 4 do
        payload[i] = bytes[i]
    end

    local want = 0
    for i = #bytes - 3, #bytes do
        want = want * 256 + bytes[i]
    end

    if check(payload) ~= want then
        return nil, 'the check number does not match: the code was cut or changed on the way (copy all of it again)'
    end

    local ok, result = pcall(function()
        local r = reader(payload, #payload * 8)
        local job = C.JOBS[r.bits(5) + 1]
        if job == nil then
            error('unknown job in the code', 0)
        end

        local name = r.text(24)
        local count = r.bits(6) + 1
        local poolSize = r.varint()
        if poolSize > 4 * 11 * C.MAX_RULES then
            error('the code has too many names', 0)
        end

        local pool = {}
        for i = 1, poolSize do
            pool[i] = r.text(48)
        end

        local function token()
            local t = r.varint()
            if t == 0 then
                return nil
            elseif t == 1 then
                return string.format('%d', r.varint())
            elseif t <= 1 + #C.VOCABULARY then
                return C.VOCABULARY[t - 1]
            end

            local s = pool[t - 1 - #C.VOCABULARY]
            if s == nil then
                error('the code names something that is not in it', 0)
            end

            return s
        end

        local function roleText(bits)
            local out = {}
            for i, role in ipairs(C.ROLES) do
                if math.floor(bits / 2 ^ (i - 1)) % 2 == 1 then
                    out[#out + 1] = role
                end
            end

            return #out > 0 and table.concat(out, '.') or nil
        end

        local rules = {}
        for i = 1, count do
            local row = { on = r.bits(1) == 1 }
            row.target = token()
            if r.bits(1) == 1 then
                row.rolesIn, row.rolesOut = roleText(r.bits(4)), roleText(r.bits(4))
            end

            for _, key in ipairs(FIELDS) do
                row[key] = token()
            end

            row.kind = C.KINDS[r.bits(3) + 1]
            if row.kind == nil or (row.kind == 'burstcap' and format < 2) then
                error('unknown action kind in rule ' .. i, 0)
            end

            row.name, row.retry, row.level, row.id = token(), token(), token(), token()
            if format >= 2 and r.bits(1) == 1 then
                for _, key in ipairs(MORE_FIELDS) do
                    row[key] = token()
                end

                for _, key in ipairs(SUBJECT_KEYS) do
                    local ix = r.bits(2)
                    if ix > #C.SUBJECTS then
                        error('unknown condition subject in rule ' .. i, 0)
                    end

                    row[key] = ix > 0 and C.SUBJECTS[ix] or nil
                end

                row.wake = r.bits(1) == 1 or nil
            end

            rules[i] = row
        end

        if #payload * 8 - r.pos >= 8 then
            error('the code has data left over (it was changed)', 0)
        end

        return { job = job, name = name, rules = rules }
    end)

    if not ok then
        return nil, tostring(result)
    end

    return result
end

return C
