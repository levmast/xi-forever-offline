-- Crystal Boy: step trace for finding crashes. Each line is written and the file closed before the step runs,
-- so after a crash the last line shows where it stopped. File: config\addons\crystalboy\trace.txt
-- Repeating events (frames) are only written the first few times.
local M = { path = nil, on = true, counts = {} }

function M.start(path)
    M.path = path
    M.last = path:gsub('%.txt$', '') .. '_last.txt'
    M.n = 0
    if M.lf then pcall(function() M.lf:close() end); M.lf = nil end
    -- (1.4) keep the trace of the session before this one: after a crash the game or the add-on is started again, which
    -- used to wipe the very trace that showed the crash (trace_prev.txt, trace_prev_last.txt)
    for _, pair in ipairs({ { path, (path:gsub('%.txt$', '')) .. '_prev.txt' }, { M.last, (path:gsub('%.txt$', '')) .. '_prev_last.txt' } }) do
        local old = io.open(pair[1], 'rb')
        if old then
            local text = old:read('*a')
            old:close()
            local keep = io.open(pair[2], 'wb')
            if keep then keep:write(text); keep:close() end
        end
    end
    local f = io.open(path, 'w')
    if f then f:write('Crystal Boy trace ' .. os.date('%Y-%m-%d %H:%M:%S') .. '\n'); f:close() end
end

--- key: repeated events with the same key are written at most `limit` times (default: always)
function M.log(msg, key, limit)
    if not (M.on and M.path) then return end
    if key then
        local n = (M.counts[key] or 0) + 1
        M.counts[key] = n
        if n > (limit or 5) then return end
    end
    local f = io.open(M.path, 'a')
    if f then
        f:write(string.format('%.3f %s\n', os.clock(), tostring(msg)))
        f:close()
    end
end

--- The latest step only (overwritten every time): after a crash it names the step that was running.
-- (1.5) The file stays open and each step is written over the last one and flushed: opening it again for every step
-- (several times a frame) could fail now and then, and a missed write left an older step standing as "the last one".
function M.step(msg)
    if not (M.on and M.last) then return end
    M.n = (M.n or 0) + 1
    if not M.lf then M.lf = io.open(M.last, 'w') end
    local f = M.lf
    if f then
        local line = string.format('%d %s', M.n, tostring(msg))
        f:seek('set', 0)
        f:write(line .. string.rep(' ', math.max(0, 78 - #line)) .. '\n')
        f:flush()
    end
end

--- Repeating events are written in full again (called when a game starts: the frames right after it matter most).
function M.again()
    M.counts = {}
end

return M
