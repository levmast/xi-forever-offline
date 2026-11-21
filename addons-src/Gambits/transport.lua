--[[
GambitsV2 transport: sends the editor's "/say !gsq ..." and "/say !squad ..." lines through the game's chat, one line at
a time, and tells for every attempt what the game client did with it.

What the client shows (seen in its own chat log, with or without the timestamp addon):
  "Name : !gsq hello 1234"                         our line was SENT (the client's local echo of a /say)
  ">> /say !gsq mates 1235" + "...A command error occurred."   our line was REFUSED by the client; it never left the game
The classification reads the ORIGINAL message text (text_in's e.message), which other addons do not change.

Rules:
  - At least `interval` seconds (1.0 by default) between two chat lines, counting chat lines of other addons and the
    player too (command_seen); never while the chat input is open; nothing while zoning.
  - A refused line is sent again (it never reached the server), at most `rejects` times; each refusal makes the interval
    for this session 1.25 x longer (at most `maxInterval`).
  - A sent line without an answer is sent again only when the job says it is safe (idempotent ~= false), at most `retries`
    times. A job that must not run twice (Apply) is never sent again once the client confirmed sending it.
  - Only the refused-line pair of OUR exact line (and, optionally, the echo of our exact accepted line) is hidden. Every
    other line, including any other "...A command error occurred.", stays visible.
Request ids and save tokens are the job's own; this file never changes a line.
]]

local T = {}
T.VERSION  = '1.0.0'
T.MAX_LINE = 120
T.DEFAULTS = {
    interval    = 1.0,   -- s between two chat lines (configurable; see /gv2 ping N gap to measure a smaller one)
    timeout     = 3.0,   -- s without an answer after the last answer line (or the send) of a request
    retries     = 2,     -- resends of a SENT line without an answer (idempotent jobs only)
    rejects     = 3,     -- resends of a line the client REFUSED
    backoff     = 1.25,  -- interval factor after each refusal
    maxInterval = 2.0,
    echoWindow  = 1.5,   -- s to wait for the client's echo of a line that gets no server answer (Assign, Apply)
    settle      = 2.0,   -- s after zoning in before the next line
    hideEcho    = true,  -- hide the client's echo of our own accepted lines
}

local CHAT = {}
for _, c in ipairs({ '/say', '/s', '/party', '/p', '/linkshell', '/l', '/linkshell2', '/l2', '/tell', '/t', '/shout', '/sh',
                     '/yell', '/emote', '/em', '/unity', '/u' }) do
    CHAT[c] = true
end

local api, C = {}, {}
local S = {}
T._S = S

local function now()
    return api.now and api.now() or os.clock()
end

function T.reset()
    S.queue, S.current, S.owned, S.said = {}, nil, {}, {}
    S.lastChat, S.reject, S.paused, S.resumeAt = -1000, nil, false, -1000
    S.gap = C.interval or T.DEFAULTS.interval
    S.stats = { sent = 0, accepted = 0, rejected = 0, resent = 0, timeouts = 0, foreign = 0 }
end

-- a = { now, queue_command(line), input_open(), log(text, err), config = { interval = ..., ... } }
function T.init(a)
    api = a or {}
    C = {}
    for k, v in pairs(T.DEFAULTS) do
        C[k] = v
    end

    for k, v in pairs(api.config or {}) do
        if T.DEFAULTS[k] ~= nil and type(v) == type(T.DEFAULTS[k]) then
            C[k] = v
        end
    end

    C.interval = math.max(0.25, math.min(5.0, C.interval))
    T.config = C
    T.reset()
end
T.init({})

function T.get_interval()
    return S.gap
end

-- sets the interval for this session (a refusal still raises it); returns the value used
function T.set_interval(seconds)
    S.gap = math.max(0.25, math.min(5.0, tonumber(seconds) or C.interval))
    return S.gap
end

function T.stats()
    local out = {}
    for k, v in pairs(S.stats) do
        out[k] = v
    end

    out.interval = S.gap
    return out
end

-- "\30\81[22:41:16]\30\1 >> /say ..." (colour codes, and a timestamp addon's "[hh:mm:ss]" when only the changed text is
-- available) -> the bare text
function T.plain(message)
    local t = tostring(message or ''):gsub('%z', ''):gsub('[\30\31].', ''):gsub('\127.', '')
    t = t:gsub('^%s+', ''):gsub('^%[%d%d?:%d%d:%d%d%]%s*', '')
    return (t:gsub('%s+$', ''))
end

function T.is_chat(line)
    local first = string.match(line or '', '^(%S+)')
    if first == nil then
        return false
    end

    if string.sub(first, 1, 1) ~= '/' then
        return true -- typed text without a command goes to chat
    end

    return CHAT[string.lower(first)] == true
end

local function said_of(line)
    return string.match(line, '^/[sS][aA][yY]%s+(.*)$') or string.match(line, '^/[sS]%s+(.*)$') or line
end

-- job = { id, lines = { ... }, on_line(fields, job) -> 'next'|'done'|'fail'|nil, on_done(job), on_fail(why, kind, job),
--         on_retry(job), idempotent (default true), noreply (true: no GSQ answer; done once the client sent it) }
-- on_fail kinds: 'refused' (the server said no), 'rejected' (the client never sent it), 'unknown' (sent, no answer)
function T.enqueue(job)
    for _, line in ipairs(job.lines or {}) do
        if #line > T.MAX_LINE then
            if job.on_fail then
                job.on_fail('a request line is longer than ' .. T.MAX_LINE .. ' bytes', 'rejected', job)
            end

            return false
        end
    end

    if job.lines == nil or #job.lines == 0 then
        return false
    end

    job.index, job.tries, job.rejects, job.state = 1, 0, 0, 'ready'
    S.queue[#S.queue + 1] = job
    return true
end

function T.busy()
    return S.current ~= nil or #S.queue > 0
end

function T.owns(line)
    local at = S.owned[T.plain(line)]
    return at ~= nil and now() - at < 10
end

local function done(cur)
    S.current = nil
    if cur.on_done then
        cur.on_done(cur)
    end
end

local function fail(cur, why, kind)
    S.current = nil
    if cur.on_fail then
        cur.on_fail(why, kind, cur)
    end
end

local function next_line(cur)
    cur.index, cur.tries, cur.rejects = cur.index + 1, 0, 0
    if cur.index > #cur.lines then
        done(cur)
    else
        cur.state = 'ready'
    end
end

local function send(cur)
    local line = cur.lines[cur.index]
    local t = now()
    S.owned[line] = t
    cur.said = said_of(line)
    S.said[cur.said] = t
    S.lastChat = t
    cur.state, cur.sentAt, cur.lastAnswerAt = 'sent', t, nil
    cur.firstSentAt = cur.firstSentAt or t
    cur.lineFirstAt = cur.lineFirstAt or {}
    cur.lineFirstAt[cur.index] = cur.lineFirstAt[cur.index] or t
    S.stats.sent = S.stats.sent + 1
    if api.queue_command then
        api.queue_command(line)
    end
end

-- no answer (or no echo) for a sent line: send it again when that is safe, else give up as "unknown"
local function unanswered(cur, why)
    S.stats.timeouts = S.stats.timeouts + 1
    if cur.idempotent ~= false and cur.tries < C.retries then
        cur.tries = cur.tries + 1
        cur.state = 'ready'
        S.stats.resent = S.stats.resent + 1
        if cur.on_retry then
            cur.on_retry(cur)
        end
    else
        fail(cur, why, 'unknown')
    end
end

local function refused(cur)
    S.stats.rejected = S.stats.rejected + 1
    cur.rejects = cur.rejects + 1
    S.gap = math.min(C.maxInterval, math.max(S.gap, C.interval) * C.backoff)
    if cur.rejects > C.rejects then
        fail(cur, 'the game refused to send the line ' .. cur.rejects .. ' times', 'rejected')
    else
        cur.state = 'ready'
        S.stats.resent = S.stats.resent + 1
    end
end

function T.tick()
    local t = now()
    for line, at in pairs(S.owned) do
        if t - at > 10 then
            S.owned[line] = nil
        end
    end

    for said, at in pairs(S.said) do
        if t - at > 10 then
            S.said[said] = nil
        end
    end

    if S.reject and t - S.reject.at > 1.0 then
        S.reject = nil
    end

    local cur = S.current
    if cur and not S.paused then
        if cur.noreply then
            if cur.state == 'accepted' then
                next_line(cur)
            elseif cur.state == 'sent' and t - cur.sentAt > C.echoWindow then
                unanswered(cur, 'the game did not show whether it sent the line')
            end
        elseif (cur.state == 'sent' or cur.state == 'accepted') and t - (cur.lastAnswerAt or cur.sentAt) > C.timeout then
            unanswered(cur, 'no answer from the server')
        end
    end

    if S.current == nil and #S.queue > 0 and not S.paused then
        S.current = table.remove(S.queue, 1)
    end

    cur = S.current
    if cur and cur.state == 'ready' and not S.paused and t >= S.resumeAt and t - S.lastChat >= S.gap
        and not (api.input_open and api.input_open()) then
        send(cur)
    end
end

-- One answer "GSQ|id|kind|..." (already split) for the job in flight; others (old, duplicate, not ours) are ignored
function T.on_reply(fields)
    local cur = S.current
    if cur == nil or cur.noreply or fields[2] ~= cur.id or (cur.state ~= 'sent' and cur.state ~= 'accepted') then
        return
    end

    if cur.state == 'sent' then
        cur.state = 'accepted' -- an answer proves the line arrived
        S.stats.accepted = S.stats.accepted + 1
    end

    cur.lastAnswerAt = now()
    local verdict = cur.on_line and cur.on_line(fields, cur) or nil
    if S.current ~= cur then
        return
    end

    if verdict == 'next' then
        next_line(cur)
    elseif verdict == 'done' then
        done(cur)
    elseif verdict == 'fail' then
        fail(cur, cur.error or 'the server refused it', 'refused')
    end
end

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
T.split = split

-- text_in: original = e.message (unchanged by other addons), modified = e.message_modified. Returns true = hide it.
function T.text_in(original, modified)
    local text = T.plain(original ~= nil and original or modified)
    local at = string.find(text, 'GSQ|', 1, true)
    if at then
        T.on_reply(split((string.sub(text, at):gsub('%s+$', '')), '|'))
        return true
    end

    local t = now()
    local cur = S.current

    -- ">> /say !gsq ..." : the client refused one of our lines
    if string.sub(text, 1, 3) == '>> ' then
        local line = string.sub(text, 4)
        if S.owned[line] then
            S.reject = { line = line, at = t }
            if cur and cur.state == 'sent' and cur.lines[cur.index] == line then
                refused(cur)
            end

            return true
        end

        return false
    end

    -- the one error line that follows a refusal of ours (any other command error stays visible)
    if S.reject and t - S.reject.at <= 1.0 and string.match(text, '^%.%.%.%s*A command error occurred%.$') then
        S.reject = nil
        return true
    end

    -- "Name : !gsq ..." : the client sent our line
    local said = string.match(text, '^%S+ : (.+)$')
    if said and S.said[said] then
        if cur and cur.state == 'sent' and cur.said == said then
            cur.state = 'accepted'
            S.stats.accepted = S.stats.accepted + 1
        end

        return C.hideEcho == true
    end

    return false
end

-- every command the game is about to run (Ashita's command event, not blocked): chat lines count for the interval
function T.command_seen(line)
    local text = T.plain(line)
    if text == '' or S.owned[text] then
        return
    end

    if T.is_chat(text) then
        S.lastChat = math.max(S.lastChat, now())
        S.stats.foreign = S.stats.foreign + 1
    end
end

-- zoning or logging out (true) and zoning in (false)
function T.zone(out)
    local cur = S.current
    if out then
        S.paused = true
        if cur and cur.state == 'accepted' and cur.noreply then
            next_line(cur) -- the client sent it before the zone; it counts as sent
        elseif cur and (cur.state == 'sent' or cur.state == 'accepted') then
            unanswered(cur, 'interrupted by a zone change or log-out')
        end
    else
        S.paused = false
        S.resumeAt = now() + C.settle
    end
end

function T.paused()
    return S.paused
end

return T
