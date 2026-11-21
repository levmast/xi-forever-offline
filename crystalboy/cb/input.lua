--[[ Crystal Boy: keyboard and controller input.
     The game (FFXI) reads the keyboard and controllers through DirectInput / XInput, so the addon reads
     the same data Ashita hands to the game, and empties it while the Crystal Boy window has focus.
     Keyboard bindings are DirectInput scan codes (DIK). Controllers: XInput (Xbox and most PC pads)
     and DirectInput (PlayStation, Switch Pro, ...: button ids 48 + n, D-pad = id 32 with an angle). ]]
local ffi = require('ffi')
pcall(ffi.cdef, [[
typedef struct { uint16_t wButtons; uint8_t bLeftTrigger; uint8_t bRightTrigger;
                 int16_t sThumbLX; int16_t sThumbLY; int16_t sThumbRX; int16_t sThumbRY; } CB_XINPUT_GAMEPAD;
typedef struct { uint32_t dwPacketNumber; CB_XINPUT_GAMEPAD Gamepad; } CB_XINPUT_STATE;
]])

local M = {}

M.ACTIONS = {
    { id = 'up', label = 'Up' }, { id = 'down', label = 'Down' }, { id = 'left', label = 'Left' }, { id = 'right', label = 'Right' },
    { id = 'a', label = 'A' }, { id = 'b', label = 'B' }, { id = 'start', label = 'Start' }, { id = 'select', label = 'Select' },
    { id = 'fast', label = 'Fast forward (hold)' }, { id = 'save', label = 'Save state' }, { id = 'load', label = 'Load state' },
}

-- DirectInput scan codes
M.DIK = { ESCAPE = 0x01, BACK = 0x0E, TAB = 0x0F, RETURN = 0x1C, Z = 0x2C, X = 0x2D, SPACE = 0x39,
          F5 = 0x3F, F7 = 0x41, UP = 0xC8, LEFT = 0xCB, RIGHT = 0xCD, DOWN = 0xD0 }

M.DEFAULT_KEYS = { up = 0xC8, down = 0xD0, left = 0xCB, right = 0xCD, a = 0x2D, b = 0x2C, start = 0x1C, select = 0x0E,
                   fast = 0x39, save = 0x3F, load = 0x41 }

-- XInput: button bit names, plus LT / RT (triggers). Nintendo layout by position: GB A = the right face button.
M.XI_BITS = { DPAD_UP = 0x0001, DPAD_DOWN = 0x0002, DPAD_LEFT = 0x0004, DPAD_RIGHT = 0x0008, START = 0x0010, BACK = 0x0020,
              LS = 0x0040, RS = 0x0080, LB = 0x0100, RB = 0x0200, A = 0x1000, B = 0x2000, X = 0x4000, Y = 0x8000 }
M.DEFAULT_XI = { up = 'DPAD_UP', down = 'DPAD_DOWN', left = 'DPAD_LEFT', right = 'DPAD_RIGHT', a = 'B', b = 'A',
                 start = 'START', select = 'BACK', fast = 'RT', save = 'RB', load = 'LB' }

-- DirectInput: PlayStation layout as Ashita reports it (Square 48, Cross 49, Circle 50, Triangle 51, L1 52, R1 53,
-- L2 54, R2 55, Create/Share 56, Options 57). D-pad directions are 'POV_UP' etc.
M.DEFAULT_DI = { up = 'POV_UP', down = 'POV_DOWN', left = 'POV_LEFT', right = 'POV_RIGHT', a = 50, b = 49,
                 start = 57, select = 56, fast = 55, save = 53, load = 52 }

local POV = { POV_UP = { 31500, 0, 4500 }, POV_RIGHT = { 4500, 9000, 13500 }, POV_DOWN = { 13500, 18000, 22500 },
              POV_LEFT = { 22500, 27000, 31500 } }
local STICK = 12000 -- left stick dead zone (also moves the D-pad)

M.s = { kb = {}, kd = {}, xb = 0, lt = 0, rt = 0, lx = 0, ly = 0, di = {}, pov = -1 }

function M.clear()
    M.s.kb, M.s.kd, M.s.di = {}, {}, {}
    M.s.xb, M.s.lt, M.s.rt, M.s.lx, M.s.ly, M.s.pov = 0, 0, 0, 0, 0, -1
end

--- (1.7) Buffered keyboard events (Ashita's key_data: DirectInput GetDeviceData). FFXI takes many key presses from
-- this buffer rather than from the key state, so they are both read here and kept from the game.
function M.key_data(key, down)
    if type(key) ~= 'number' or key < 1 or key > 255 then return end
    M.s.kd[key] = down and true or nil
end

--- Keyboard state (256 bytes, DirectInput). Read it, then empty it so the game sees no key.
function M.take_keyboard(ptr, block)
    -- (1.4) a Lua string is a copy of the state: read it, never write through it (writing into a string's memory
    -- corrupts the game's Lua and crashes it some time later)
    if type(ptr) == 'string' then
        local kb = {}
        for i = 1, math.min(255, #ptr - 1) do
            if ptr:byte(i + 1) >= 0x80 then kb[i] = true end
        end
        M.s.kb = kb
        return
    end
    local p = ffi.cast('uint8_t *', ptr)
    local kb = {}
    for i = 1, 255 do
        if p[i] >= 0x80 then kb[i] = true end
    end
    M.s.kb = kb
    if block then ffi.fill(p, 256, 0) end
end

--- XInput state. Read it from `state`, and empty `modified` (what the game gets) when given.
function M.take_xinput(state, modified)
    local g = ffi.cast('CB_XINPUT_STATE *', state).Gamepad
    M.s.xb, M.s.lt, M.s.rt, M.s.lx, M.s.ly = g.wButtons, g.bLeftTrigger, g.bRightTrigger, g.sThumbLX, g.sThumbLY
    if modified ~= nil then
        local m = ffi.cast('CB_XINPUT_STATE *', modified).Gamepad
        m.wButtons, m.bLeftTrigger, m.bRightTrigger, m.sThumbLX, m.sThumbLY, m.sThumbRX, m.sThumbRY = 0, 0, 0, 0, 0, 0, 0
    end
end

--- One DirectInput button event (id 32 = D-pad with its angle; 65535 or -1 = centred).
function M.dinput(button, state)
    button, state = tonumber(button), tonumber(state)
    if not button then return end
    if button == 32 then
        M.s.pov = (state and state >= 0 and state < 36000) and state or -1
    else
        M.s.di[button] = (state or 0) >= 128 or nil
    end
end

local function pov_is(name)
    local a, r = M.s.pov, POV[name]
    if a < 0 or not r then return false end
    if name == 'POV_UP' then return a >= 31500 or a <= 4500 end
    return a >= r[1] and a <= r[3]
end

local function xi_is(name)
    if name == 'LT' then return M.s.lt > 64 end
    if name == 'RT' then return M.s.rt > 64 end
    local bitv = M.XI_BITS[name]
    return bitv ~= nil and bit.band(M.s.xb, bitv) ~= 0
end

local function di_is(code)
    if type(code) == 'string' then return pov_is(code) end
    return M.s.di[tonumber(code)] == true
end

--- Is this action held, by any device?
function M.held(action, binds)
    if binds.kb[action] and (M.s.kb[binds.kb[action]] or M.s.kd[binds.kb[action]]) then return true end
    if binds.xi[action] and xi_is(binds.xi[action]) then return true end
    if binds.di[action] and di_is(binds.di[action]) then return true end
    if action == 'up' then return M.s.ly > STICK end
    if action == 'down' then return M.s.ly < -STICK end
    if action == 'left' then return M.s.lx < -STICK end
    if action == 'right' then return M.s.lx > STICK end
    return false
end

--- Everything pressed right now, for "press a key / button" binding: list of { kind, code }.
function M.pressed_now()
    local out = {}
    for k in pairs(M.s.kb) do out[#out + 1] = { 'kb', k } end
    for name in pairs(M.XI_BITS) do if xi_is(name) then out[#out + 1] = { 'xi', name } end end
    if xi_is('LT') then out[#out + 1] = { 'xi', 'LT' } end
    if xi_is('RT') then out[#out + 1] = { 'xi', 'RT' } end
    for b in pairs(M.s.di) do out[#out + 1] = { 'di', b } end
    for name in pairs(POV) do if pov_is(name) then out[#out + 1] = { 'di', name } end end
    return out
end

local KEYNAMES = { [0x01] = 'Esc', [0x0E] = 'Backspace', [0x0F] = 'Tab', [0x1C] = 'Enter', [0x1D] = 'Left Ctrl', [0x2A] = 'Left Shift',
    [0x36] = 'Right Shift', [0x38] = 'Left Alt', [0x39] = 'Space', [0x9C] = 'Numpad Enter', [0xC8] = 'Up', [0xD0] = 'Down',
    [0xCB] = 'Left', [0xCD] = 'Right', [0xC7] = 'Home', [0xCF] = 'End', [0xC9] = 'Page Up', [0xD1] = 'Page Down',
    [0xD2] = 'Insert', [0xD3] = 'Delete', [0x29] = '`', [0x0C] = '-', [0x0D] = '=', [0x1A] = '[', [0x1B] = ']',
    [0x27] = ';', [0x28] = "'", [0x2B] = '\\', [0x33] = ',', [0x34] = '.', [0x35] = '/' }
local ROWS = { [0x02] = '1234567890', [0x10] = 'QWERTYUIOP', [0x1E] = 'ASDFGHJKL', [0x2C] = 'ZXCVBNM' }
for start, letters in pairs(ROWS) do
    for i = 1, #letters do KEYNAMES[start + i - 1] = letters:sub(i, i) end
end
for i = 0, 9 do KEYNAMES[0x3B + i] = 'F' .. (i + 1) end
KEYNAMES[0x57], KEYNAMES[0x58] = 'F11', 'F12'
local NUMPAD = { [0x47] = 7, [0x48] = 8, [0x49] = 9, [0x4B] = 4, [0x4C] = 5, [0x4D] = 6, [0x4F] = 1, [0x50] = 2, [0x51] = 3, [0x52] = 0 }
for code, n in pairs(NUMPAD) do KEYNAMES[code] = 'Numpad ' .. n end

local XINAMES = { DPAD_UP = 'D-pad Up', DPAD_DOWN = 'D-pad Down', DPAD_LEFT = 'D-pad Left', DPAD_RIGHT = 'D-pad Right',
    START = 'Start', BACK = 'Back', LS = 'Left stick click', RS = 'Right stick click', LB = 'LB', RB = 'RB',
    A = 'A (bottom)', B = 'B (right)', X = 'X (left)', Y = 'Y (top)', LT = 'LT', RT = 'RT' }
local DINAMES = { [48] = 'Square / button 1', [49] = 'Cross / button 2', [50] = 'Circle / button 3', [51] = 'Triangle / button 4',
    [52] = 'L1', [53] = 'R1', [54] = 'L2', [55] = 'R2', [56] = 'Share / Create', [57] = 'Options', [58] = 'L3', [59] = 'R3',
    POV_UP = 'D-pad Up', POV_DOWN = 'D-pad Down', POV_LEFT = 'D-pad Left', POV_RIGHT = 'D-pad Right' }

function M.name(kind, code)
    if code == nil then return '-' end
    if kind == 'kb' then return KEYNAMES[code] or string.format('Key %02X', code) end
    if kind == 'xi' then return XINAMES[code] or tostring(code) end
    return DINAMES[code] or ('Button ' .. tostring((tonumber(code) or 48) - 47))
end

--- Fresh copy of the default bindings.
function M.defaults()
    local b = { kb = {}, xi = {}, di = {} }
    for k, v in pairs(M.DEFAULT_KEYS) do b.kb[k] = v end
    for k, v in pairs(M.DEFAULT_XI) do b.xi[k] = v end
    for k, v in pairs(M.DEFAULT_DI) do b.di[k] = v end
    return b
end

--- Bindings from settings, falling back to the defaults for anything missing or wrong.
function M.load(saved)
    local b = M.defaults()
    if type(saved) ~= 'table' then return b end
    for _, a in ipairs(M.ACTIONS) do
        local id = a.id
        if type(saved.kb) == 'table' and tonumber(saved.kb[id]) then b.kb[id] = tonumber(saved.kb[id]) end
        if type(saved.xi) == 'table' and (M.XI_BITS[saved.xi[id]] or saved.xi[id] == 'LT' or saved.xi[id] == 'RT') then b.xi[id] = saved.xi[id] end
        if type(saved.di) == 'table' and saved.di[id] ~= nil then
            local v = saved.di[id]
            if POV[v] or tonumber(v) then b.di[id] = POV[v] and v or tonumber(v) end
        end
    end
    return b
end

return M
