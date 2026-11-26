--[[
Tetra Master 0.3 (XI: Forever Offline)
The Tetra Master card game inside FFXI. The server runs the match (!tm); this addon draws the board and sends your
moves. Art, sounds and the original Tetra Master addon: Nalfey (github.com/Nalfey/TetraMaster). See CREDITS.md.

  /tm                    open or close the board
  /tm play [easy|normal|hard]
  /tm quit               give up the current match
  /tm scale <1-4>        board size (default 2)
  /tm music              music on or off
  /tm sound              sound effects on or off
  /tm volume <0-100>     how loud the sounds and music are (default 40)

Talk to a card trader in a tavern to buy starter cards (and sell cards back). Cards also drop from monsters of their
family, notorious monsters and treasure caskets.

Click a card in your hand (right side), then a free square. If your card can start more than one battle, click the
card you want to fight. Lines from the server starting with "tetramaster:" are hidden from the chat log.
]]

addon.name    = 'tetramaster'
addon.author  = 'XI: Forever Offline (art: Nalfey)'
addon.version = '0.3'
addon.desc    = 'Tetra Master inside FFXI.'
addon.link    = ''

require('common')
local imgui = require('imgui')
local ffi   = require('ffi')
local d3d8  = require('d3d8')

pcall(ffi.cdef, [[
    int __stdcall PlaySoundA(const char* pszSound, void* hmod, uint32_t fdwSound);
    uint32_t __stdcall mciSendStringA(const char* cmd, char* ret, uint32_t len, void* hwnd);
]])
local okWinmm, winmm = pcall(ffi.load, 'winmm')

------------------------------------------------------------------------------
-- Paths and settings
------------------------------------------------------------------------------
local HERE = (addon.path or debug.getinfo(1, 'S').source:sub(2):gsub('[^\\/]*$', ''))
if not HERE:match('[\\/]$') then HERE = HERE .. '\\' end
local ASSETS = HERE .. 'assets\\'

local function configDir()
    local ok, base = pcall(function() return AshitaCore:GetInstallPath() end)
    if not ok or type(base) ~= 'string' then return nil end
    if not base:match('[\\/]$') then base = base .. '\\' end
    return base .. 'config\\addons\\tetramaster\\'
end

local S = { scale = 2, music = false, sound = true, level = 'normal', volume = 40 }

local function loadSettings()
    local dir = configDir()
    local f = dir and io.open(dir .. 'settings.txt', 'r')
    if not f then return end
    for line in f:lines() do
        local k, v = line:match('^%s*(%w+)%s*=%s*(.-)%s*$')
        if k == 'scale' then S.scale = math.max(1, math.min(4, tonumber(v) or 2))
        elseif k == 'music' then S.music = (v == 'on')
        elseif k == 'sound' then S.sound = (v ~= 'off')
        elseif k == 'volume' then S.volume = math.max(0, math.min(100, tonumber(v) or 40))
        elseif k == 'level' and (v == 'easy' or v == 'normal' or v == 'hard') then S.level = v end
    end
    f:close()
end

local function saveSettings()
    local dir = configDir()
    if not dir then return end
    pcall(ashita.fs.create_directory, dir)
    local f = io.open(dir .. 'settings.txt', 'w')
    if not f then return end
    f:write(string.format('scale = %d\nmusic = %s\nsound = %s\nlevel = %s\nvolume = %d\n', S.scale, S.music and 'on' or 'off',
        S.sound and 'on' or 'off', S.level, S.volume))
    f:close()
end

local function say(msg)
    print('[tetramaster] ' .. tostring(msg))
end

local function now()
    local ok, t = pcall(function() return tonumber(ashita.time.get_tick64()) / 1000 end)
    if ok and t then return t end
    return os.clock()
end

------------------------------------------------------------------------------
-- Textures (PNG files, loaded pixel for pixel into a power-of-two texture; uv = pixel / texture size)
------------------------------------------------------------------------------
local tex = {}

local function nextPow2(n)
    local p = 1
    while p < n do p = p * 2 end
    return p
end

local function loadTexture(path)
    local f = io.open(path, 'rb')
    if not f then return nil end
    local data = f:read('*a')
    f:close()
    if #data < 24 or data:sub(2, 4) ~= 'PNG' then return nil end
    local function be32(at)
        local a, b, c, d = data:byte(at, at + 3)
        return ((a * 256 + b) * 256 + c) * 256 + d
    end
    local w, h = be32(17), be32(21)
    local tw, th = nextPow2(w), nextPow2(h)

    local ok, t = pcall(function()
        local device = d3d8.get_device()
        local raw = ffi.new('IDirect3DTexture8*[1]')
        -- D3DX_FILTER_NONE (1): the picture is copied as it is into the top left of the texture
        local hr = ffi.C.D3DXCreateTextureFromFileInMemoryEx(ffi.cast('IDirect3DDevice8*', device), data, #data,
            tw, th, 1, 0, ffi.C.D3DFMT_A8R8G8B8, ffi.C.D3DPOOL_MANAGED, 1, 1, 0, nil, nil, raw)
        if hr ~= 0 or raw[0] == nil then return nil end
        local image = d3d8.gc_safe_release(ffi.cast('IDirect3DTexture8*', raw[0]))
        return { image = image, ptr = tonumber(ffi.cast('uint32_t', image)), w = w, h = h, tw = tw, th = th }
    end)
    if ok then return t end
    return nil
end

local function loadAll()
    tex.sheet = loadTexture(ASSETS .. 'sprites\\graphics.png')
    tex.cards, tex.coin, tex.boom = {}, {}, {}
    for i = 1, 8 do
        tex.coin[i] = loadTexture(string.format('%ssprites\\Coin\\coin_%02d.png', ASSETS, i))
        tex.boom[i] = loadTexture(string.format('%ssprites\\Explosion\\explosion_%02d.png', ASSETS, i))
    end
    if tex.sheet == nil then
        say('Could not load ' .. ASSETS .. 'sprites\\graphics.png - is the assets folder next to tetramaster.lua?')
    end
end

local function cardTexture(id)
    local t = tex.cards[id]
    if t == nil then
        t = loadTexture(string.format('%ssprites\\Cards\\%03d.png', ASSETS, id)) or false
        tex.cards[id] = t
    end
    return t or nil
end

-- Sprite sheet pieces (from Nalfey's init.lua): { x, y, w, h }
local Q =
{
    background = { 10, 498, 320, 240 },
    grid       = { 340, 498, 224, 240 },
    backBlue   = { 18, 822, 42, 51 },
    backRed    = { 66, 822, 42, 51 },
    block1     = { 114, 822, 42, 51 },
    block2     = { 162, 822, 42, 51 },
    divider    = { 202, 759, 43, 23 },
    cardBack   = { 210, 822, 42, 51 },
    arrows     =
    {
        upleft = { 202, 790, 8, 8 }, up = { 210, 790, 8, 8 }, upright = { 218, 790, 8, 8 },
        downleft = { 226, 790, 8, 8 }, down = { 234, 790, 8, 8 }, downright = { 242, 790, 8, 8 },
        left = { 202, 798, 8, 8 }, right = { 210, 798, 8, 8 },
    },
    score =
    {
        blue = { { 154, 762, 16, 20 }, { 11, 764, 13, 19 }, { 26, 763, 16, 21 }, { 42, 763, 16, 22 }, { 58, 764, 17, 21 },
                 { 75, 763, 15, 21 }, { 90, 762, 16, 21 }, { 106, 763, 16, 20 }, { 122, 762, 16, 22 }, { 138, 762, 16, 22 },
                 { 171, 762, 27, 20 } },
        red  = {},
    },
    stat = {},
}
for i, q in ipairs(Q.score.blue) do Q.score.red[i] = { q[1], q[2] + 34, q[3], q[4] } end
for i, ch in ipairs({ '0', '1', '2', '3', '4', '5', '6', '7', '8', '9', 'A', 'B', 'C', 'D', 'E', 'F', 'P', 'M', 'X' }) do
    Q.stat[ch] = { 356 + (i - 1) * 8, 822, 7, 7 }
end

local NAMES = nil -- card names (cardnames.lua)

local DIRS = { 'up', 'down', 'left', 'right', 'upleft', 'upright', 'downleft', 'downright' }

local function hasArrow(mask, i)
    return math.floor(mask / (2 ^ (i - 1))) % 2 == 1
end

------------------------------------------------------------------------------
-- Drawing (Nalfey's 320x240 layout, times S.scale)
------------------------------------------------------------------------------
local ox, oy = 0, 0 -- top left of the board on screen

local function image(t, x, y, w, h, u, v, uw, vh, tint)
    if t == nil then return end
    local s = S.scale
    imgui.SetCursorScreenPos({ ox + x * s, oy + y * s })
    local uv0 = { u / t.tw, v / t.th }
    local uv1 = { (u + uw) / t.tw, (v + vh) / t.th }
    if tint then
        if pcall(imgui.Image, t.ptr, { w * s, h * s }, uv0, uv1, tint) then return end
    end
    imgui.Image(t.ptr, { w * s, h * s }, uv0, uv1)
end

local function sheet(q, x, y, scale, tint)
    scale = scale or 1
    image(tex.sheet, x, y, q[3] * scale, q[4] * scale, q[1], q[2], q[3], q[4], tint)
end

-- One card: back colour, picture, arrows and its code (card.lua Card:draw). small = the 35x42 size in a full hand.
local function drawCard(c, x, y, side, small, tint)
    local s = small and (42 / 51) or 1
    local cw, ch = small and 35 or 42, small and 42 or 51
    if side == 'blue' then sheet(Q.backBlue, x, y, s, tint)
    elseif side == 'red' then sheet(Q.backRed, x, y, s, tint) end
    local pic = cardTexture(c.id)
    if pic then image(pic, x, y, 42 * s, 51 * s, 0, 0, pic.w, pic.h, tint) end

    local xo, yo = small and 13 or 18, small and 17 or 22
    local pos =
    {
        up = { x + xo, y }, down = { x + xo, y + ch - 8 }, left = { x, y + yo }, right = { x + cw - 8, y + yo },
        upleft = { x, y }, upright = { x + cw - 8, y }, downleft = { x, y + ch - 8 }, downright = { x + cw - 8, y + ch - 8 },
    }
    for i, name in ipairs(DIRS) do
        if hasArrow(c.arrows, i) then sheet(Q.arrows[name], pos[name][1], pos[name][2], 1, tint) end
    end

    local tx, ty = cw / 2 - 12 + x, ch - 15 + y
    for k = 1, 4 do
        local q = Q.stat[c.code:sub(k, k)]
        if q then sheet(q, tx + (k - 1) * 6, ty, 1, tint) end
    end
end

local function cellPos(x, y)
    return 73 + (x - 1) * 42, 9 + (y - 1) * 52
end

------------------------------------------------------------------------------
-- The match as the addon sees it, and the queue of things to show
------------------------------------------------------------------------------
local G =
{
    open = { false }, phase = 'menu',   -- menu, coin, play, over
    cells = {}, hand = {}, ohand = 0, turn = 'blue', choose = nil, level = 'normal',
    queue = {}, anim = nil, busy = false, selected = nil, placedIndex = nil,
    result = nil, cards = nil, incomingCards = nil, deckPick = {}, note = '', noteUntil = 0,
    sendQueue = {}, lastSend = -10, hideUntil = 0, started = 0,
    shop = nil, incomingShop = nil, gil = nil, sellPrices = nil, maxCards = 200,
}

local TIER_NAMES = { 'Common', 'Uncommon', 'Rare', 'Epic', 'Legendary' }
local TIER_COLORS = { { 0.80, 0.80, 0.80, 1 }, { 0.45, 0.85, 0.45, 1 }, { 0.40, 0.65, 1.00, 1 }, { 0.75, 0.45, 1.00, 1 },
                      { 1.00, 0.70, 0.25, 1 } }

if TETRAMASTER_TEST then TETRAMASTER_TEST.G = G end -- the headless tests look at the match

local function note(text, secs)
    G.note, G.noteUntil = text, now() + (secs or 3)
end

local function key(x, y) return x * 10 + y end

-- sound and music
-- (2026-11-25, Jaymz: the card chime from a casket was far louder than the game) Windows plays a .wav at full volume,
-- whatever the game's own sound settings are. So each sound is played from a copy at S.volume percent, made once and
-- kept in config\addons\tetramaster\sound\<volume>\ (16-bit PCM samples scaled down).
local function scaledWav(src, name)
    if S.volume >= 100 then return src end
    local dir = configDir()
    if not dir then return src end
    dir = dir .. 'sound\\' .. tostring(S.volume) .. '\\'
    local out = dir .. name
    local f = io.open(out, 'rb')
    if f then f:close(); return out end
    local inf = io.open(src, 'rb')
    if not inf then return src end
    local data = inf:read('*a')
    inf:close()
    if #data < 44 or data:sub(1, 4) ~= 'RIFF' or data:sub(9, 12) ~= 'WAVE' then return src end
    local buf = ffi.new('uint8_t[?]', #data)
    ffi.copy(buf, data, #data)
    local pos, bits = 12, 16
    while pos + 8 <= #data do
        local id = data:sub(pos + 1, pos + 4)
        local size = buf[pos + 4] + buf[pos + 5] * 256 + buf[pos + 6] * 65536 + buf[pos + 7] * 16777216
        if id == 'fmt ' then
            bits = buf[pos + 22] + buf[pos + 23] * 256
        elseif id == 'data' then
            if bits ~= 16 then return src end
            local n = math.floor(math.min(size, #data - pos - 8) / 2)
            local s = ffi.cast('int16_t*', buf + pos + 8)
            local k = S.volume / 100
            for i = 0, n - 1 do s[i] = math.floor(s[i] * k) end
            pcall(ashita.fs.create_directory, dir)
            local w = io.open(out, 'wb')
            if not w then return src end
            w:write(ffi.string(buf, #data))
            w:close()
            return out
        end
        pos = pos + 8 + size + (size % 2)
    end
    return src
end

local function playSound(name)
    if not S.sound or S.volume <= 0 or not okWinmm then return end
    local file = 'snd_' .. name .. '.wav'
    local path = scaledWav(ASSETS .. 'sound\\wav\\' .. file, file)
    pcall(function() winmm.PlaySoundA(path, nil, 0x00020003) end) -- SND_ASYNC | SND_NODEFAULT | SND_FILENAME
end

local musicOpen = false
local function music(on)
    if not okWinmm then return end
    if on and not musicOpen then
        local path = ASSETS .. 'sound\\mus_quadmist.mp3'
        pcall(function()
            winmm.mciSendStringA('open "' .. path .. '" type mpegvideo alias tm_music', nil, 0, nil)
            winmm.mciSendStringA('setaudio tm_music volume to ' .. tostring(S.volume * 10), nil, 0, nil)
            winmm.mciSendStringA('play tm_music repeat', nil, 0, nil)
        end)
        musicOpen = true
    elseif not on and musicOpen then
        pcall(function() winmm.mciSendStringA('close tm_music', nil, 0, nil) end)
        musicOpen = false
    end
end

-- sending commands to the server, one at a time and never while you are typing
local function send(cmd)
    G.sendQueue[#G.sendQueue + 1] = '/say !tm ' .. cmd
end

local function typing()
    local ok, open = pcall(function() return AshitaCore:GetChatManager():IsInputOpen() end)
    return ok and (open == true or (type(open) == 'number' and open ~= 0))
end

local function pump()
    local t = now()
    local first = G.sendQueue[1]
    if first == nil or t - G.lastSend < 0.6 or typing() then return end
    table.remove(G.sendQueue, 1)
    G.lastSend, G.hideUntil = t, t + 3
    pcall(function() AshitaCore:GetChatManager():QueueCommand(1, first) end)
end

------------------------------------------------------------------------------
-- Server lines
------------------------------------------------------------------------------
local function split(body)
    local f = {}
    for part in (body .. '|'):gmatch('([^|]*)|') do f[#f + 1] = part end
    return f
end

local function card(id, arrows, code)
    return { id = tonumber(id), arrows = tonumber(arrows), code = code }
end

-- things that change the board are queued, so they are shown one after another
local QUEUED = { place = true, capture = true, combo = true, battle = true, upgrade = true, turn = true, choose = true,
                 ['end'] = true }

local function onLine(body)
    local f = split(body)
    local k = f[1]
    if QUEUED[k] then
        G.queue[#G.queue + 1] = f
        return
    end

    if k == 'new' then
        -- a new match: the coin toss is shown before the first move
        G.phase, G.started, G.result = 'coin', now(), nil
        G.open[1] = true
        if S.music then music(true) end
        playSound('coin')
    elseif k == 'start' then
        -- the whole match follows (also after a reload or a refused move)
        G.cells, G.hand, G.queue, G.anim, G.choose, G.selected, G.placedIndex = {}, {}, {}, nil, nil, nil, nil
        G.level, G.turn = f[2], f[3]
        if G.phase ~= 'coin' then G.phase = 'play' end
        G.open[1] = true
    elseif k == 'block' then
        G.cells[key(tonumber(f[2]), tonumber(f[3]))] = { block = tonumber(f[4]) }
    elseif k == 'cell' then
        local c = card(f[5], f[6], f[7])
        c.side = f[4]
        G.cells[key(tonumber(f[2]), tonumber(f[3]))] = c
    elseif k == 'hand' then
        G.hand[tonumber(f[2])] = card(f[3], f[4], f[5])
    elseif k == 'ohand' then
        G.ohand = tonumber(f[2]) or 0
    elseif k == 'sync' then
        G.turn = f[2]
        G.busy = false
    elseif k == 'quit' then
        G.phase, G.queue, G.anim = 'menu', {}, nil
        music(false)
    elseif k == 'none' then
        if G.phase ~= 'over' then G.phase = 'menu' end
    elseif k == 'error' then
        G.busy = false
        if f[2] == 'no match' then G.phase = 'menu' end
        note('Server: ' .. tostring(f[2]))
    elseif k == 'cards' then
        G.incomingCards = {}
        G.maxCards = tonumber(f[3]) or G.maxCards
    elseif k == 'card' and G.incomingCards then
        local c = card(f[3], f[4], f[5])
        c.uid, c.inDeck, c.tier = tonumber(f[2]), f[6] == '1', tonumber(f[7]) or 1
        G.incomingCards[#G.incomingCards + 1] = c
    elseif k == 'shop' then
        G.incomingShop = { n = tonumber(f[2]), name = f[3], stock = {} }
        G.gil = tonumber(f[4])
    elseif k == 'sellprices' then
        G.sellPrices = {}
        for i = 2, #f do G.sellPrices[i - 1] = tonumber(f[i]) end
    elseif k == 'stock' and G.incomingShop then
        G.incomingShop.stock[tonumber(f[2])] = { id = tonumber(f[3]), code = f[4], price = tonumber(f[5]), tier = tonumber(f[6]) or 1 }
    elseif k == 'stockend' then
        G.shop, G.incomingShop = G.incomingShop, nil
        G.open[1] = true
        if G.phase == 'over' then G.phase = 'menu' end
    elseif k == 'bought' then
        G.gil = tonumber(f[5]) or G.gil
        note(string.format('Bought %s (%s).', NAMES and NAMES[tonumber(f[2])] or 'a card', f[4]), 4)
        playSound('win_card')
    elseif k == 'sold' then
        G.gil = tonumber(f[3]) or G.gil
        note(string.format('Sold for %s gil.', f[2]), 4)
        playSound('coin')
    elseif k == 'starter' then
        note('Luto Mewrilah gave you a starter deck! Open My cards to see it, or press Play.', 8)
        playSound('win_card')
    elseif k == 'found' then
        note(string.format('You found a card: %s (%s)!', NAMES and NAMES[tonumber(f[2])] or 'a card', f[4]), 6)
        playSound('win_card')
    elseif k == 'cardsend' then
        G.cards, G.incomingCards = G.incomingCards or {}, nil
        G.deckPick = {}
        for _, c in ipairs(G.cards) do if c.inDeck then G.deckPick[c.uid] = true end end
    end
end

-- how long each queued thing is shown
local DUR = { place = 0.25, capture = 0.35, combo = 0.25, battle = 1.4, upgrade = 0.8, turn = 0.05, choose = 0,
              ['end'] = 0 }

local function startNext()
    local f = table.remove(G.queue, 1)
    if f == nil then G.anim = nil; return end
    local k = f[1]
    G.anim = { f = f, t0 = now(), dur = DUR[k] or 0.2 }

    if k == 'place' then
        local side, x, y = f[2], tonumber(f[3]), tonumber(f[4])
        local c = card(f[5], f[6], f[7])
        c.side = side
        G.cells[key(x, y)] = c
        if side == 'blue' then
            if G.placedIndex then table.remove(G.hand, G.placedIndex); G.placedIndex = nil end
        else
            G.ohand = math.max(0, G.ohand - 1)
        end
        G.selected = nil
        playSound('put')
    elseif k == 'capture' or k == 'combo' then
        local c = G.cells[key(tonumber(f[2]), tonumber(f[3]))]
        if c then c.side = f[4] end
        G.anim.x, G.anim.y = tonumber(f[2]), tonumber(f[3])
        if k == 'combo' then playSound('combo_woosh') else playSound('flip_card') end
    elseif k == 'battle' then
        playSound('card_battle')
    elseif k == 'upgrade' then
        local c = G.cells[key(tonumber(f[2]), tonumber(f[3]))]
        if c then
            c.code = c.code:sub(1, 1) .. f[4] .. c.code:sub(3)
            note(string.format('%s moved up to class %s!', NAMES and NAMES[c.id] or 'A card', f[4]))
        end
    elseif k == 'turn' then
        G.turn = f[2]
        if f[2] == 'blue' then G.busy = false end
    elseif k == 'choose' then
        G.choose = {}
        for xy in f[2]:gmatch('[^;]+') do
            local x, y = xy:match('(%d),(%d)')
            G.choose[#G.choose + 1] = { x = tonumber(x), y = tonumber(y) }
        end
        G.busy = false
    elseif k == 'end' then
        local b, r, winner, perfect, gil = tonumber(f[2]), tonumber(f[3]), f[4], f[5] == '1', tonumber(f[6]) or 0
        G.result = { b = b, r = r, winner = winner, perfect = perfect, gil = gil }
        G.phase, G.busy = 'over', false
        if winner == 'draw' then playSound('tie_game')
        elseif winner == 'blue' then playSound(perfect and 'perfect_game' or 'win_game')
        else playSound('lose_game') end
    end
end

local function updateQueue()
    if G.phase == 'coin' then
        if now() - G.started < 1.6 then return end
        G.phase = 'play'
    end
    if G.anim and now() - G.anim.t0 < G.anim.dur then return end
    if G.anim and G.anim.f[1] == 'battle' then
        -- the loser's card flips in the capture line that follows
        local f = G.anim.f
        playSound(f[10] == '1' and 'win_card' or 'lose_card')
    end
    startNext()
end

------------------------------------------------------------------------------
-- Clicks
------------------------------------------------------------------------------
local function myTurn()
    return G.phase == 'play' and G.turn == 'blue' and not G.busy and G.anim == nil and #G.queue == 0
end

local function clickCell(x, y)
    if not myTurn() then return end
    if G.choose then
        for i, o in ipairs(G.choose) do
            if o.x == x and o.y == y then
                G.choose, G.busy = nil, true
                send('pick ' .. i)
                return
            end
        end
        return
    end
    if G.selected and G.cells[key(x, y)] == nil then
        G.placedIndex, G.busy = G.selected, true
        send(string.format('move %d %d %d', G.selected, x, y))
        playSound('choose_card')
    end
end

local function clickHand(i)
    if not myTurn() or G.choose then return end
    G.selected = (G.selected == i) and nil or i
    playSound('cursor')
end

-- Ashita's imgui gives a position as two numbers (x, y); a table { x, y } is accepted too
local function vec2(a, b)
    if type(a) == 'table' then
        return tonumber(a[1] or a.x) or 0, tonumber(a[2] or a.y) or 0
    end
    return tonumber(a) or 0, tonumber(b) or 0
end

local function hit(x, y, w, h)
    local s = S.scale
    local ok, a, b = pcall(imgui.GetMousePos)
    if not ok then return false end
    local px, py = vec2(a, b)
    local mx, my = px - ox, py - oy
    return mx >= x * s and mx < (x + w) * s and my >= y * s and my < (y + h) * s
end

------------------------------------------------------------------------------
-- The window
------------------------------------------------------------------------------
local GOLD = { 0.89, 0.74, 0.40, 1.0 }
local WHITE = { 1, 1, 1, 1 }

local function textAt(x, y, text, color)
    imgui.SetCursorScreenPos({ ox + x * S.scale, oy + y * S.scale })
    imgui.TextColored(color or WHITE, text)
end

local function drawBoard()
    sheet(Q.background, 0, 0)
    sheet(Q.grid, 48, 0)

    local a = G.anim
    local battle = a and a.f[1] == 'battle' and a.f or nil

    for x = 1, 4 do
        for y = 1, 4 do
            local c = G.cells[key(x, y)]
            local px, py = cellPos(x, y)
            if c and c.block then
                sheet(c.block == 2 and Q.block2 or Q.block1, px, py)
            elseif c then
                local tint = nil
                if a and (a.f[1] == 'capture' or a.f[1] == 'combo') and a.x == x and a.y == y then
                    local t = (now() - a.t0) / a.dur
                    local glow = 0.55 + 0.45 * math.abs(math.cos(t * math.pi * 2))
                    tint = { glow, glow, glow, 1 }
                end
                drawCard(c, px, py, c.side, false, tint)
            end
        end
    end

    -- battle numbers and the explosion
    if battle then
        local t = (now() - a.t0) / a.dur
        local ax, ay = cellPos(tonumber(battle[2]), tonumber(battle[3]))
        local dx, dy = cellPos(tonumber(battle[4]), tonumber(battle[5]))
        local ap, dp, af, df = tonumber(battle[6]), tonumber(battle[7]), tonumber(battle[8]), tonumber(battle[9])
        local k = math.min(1, math.max(0, (t - 0.25) / 0.5))
        local showA = math.floor(ap - (ap - af) * k + 0.5)
        local showD = math.floor(dp - (dp - df) * k + 0.5)
        textAt(ax + 10, ay + 18, tostring(showA), GOLD)
        textAt(dx + 10, dy + 18, tostring(showD), GOLD)
        if t > 0.2 and t < 0.6 and tex.boom[1] then
            local fr = tex.boom[math.min(8, math.floor((t - 0.2) / 0.05) + 1)]
            if fr then
                local cx, cy = (ax + dx) / 2 + 21 - fr.w / 2, (ay + dy) / 2 + 26 - fr.h / 2
                image(fr, cx, cy, fr.w, fr.h, 0, 0, fr.w, fr.h)
            end
        end
    end

    -- which battle to fight
    if G.choose and myTurn() then
        for _, o in ipairs(G.choose) do
            local px, py = cellPos(o.x, o.y)
            textAt(px + 12, py + 18, 'Fight?', GOLD)
        end
    end

    -- your hand on the right
    local small = #G.hand == 5
    local step = small and 42 or 51
    for i, c in ipairs(G.hand) do
        local hx = 260 - ((G.selected == i) and 8 or 0)
        local tint = (G.selected and G.selected ~= i) and { 0.55, 0.55, 0.55, 1 } or nil
        drawCard(c, hx, 8 + (i - 1) * step, 'blue', small, tint)
    end

    -- the computer's hand, face down on the left
    for i = 1, G.ohand do
        sheet(Q.cardBack, 16, 28 + (i - 1) * 10, 42 / 51)
    end

    -- score
    local b, r = 0, 0
    for _, c in pairs(G.cells) do
        if c.side == 'blue' then b = b + 1 elseif c.side == 'red' then r = r + 1 end
    end
    sheet(Q.divider, 16, 185)
    local rq, bq = Q.score.red[math.min(r + 1, 11)], Q.score.blue[math.min(b + 1, 11)]
    if rq then sheet(rq, 25, 170) end
    if bq then sheet(bq, 38, 203) end

    -- coin toss: who goes first
    if G.phase == 'coin' then
        local t = now() - G.started
        local fr = tex.coin[(math.floor(t / 0.08) % 8) + 1]
        if t < 1.0 and fr then
            image(fr, 160 - fr.w / 2, 100, fr.w, fr.h, 0, 0, fr.w, fr.h)
        else
            textAt(110, 110, G.turn == 'blue' and 'You go first' or 'Opponent goes first', GOLD)
        end
    end

    if G.phase == 'over' and G.result then
        local res = G.result
        local label = res.winner == 'draw' and 'DRAW' or (res.winner == 'blue' and (res.perfect and 'PERFECT' or 'WIN') or 'LOSE')
        textAt(140, 100, label, GOLD)
        if res.gil > 0 then textAt(130, 114, string.format('+%d gil', res.gil), GOLD) end
    end

    -- clicks (the board is drawn with images, so clicks are checked by position)
    if imgui.IsWindowHovered() and imgui.IsMouseClicked(0) then
        for x = 1, 4 do
            for y = 1, 4 do
                local px, py = cellPos(x, y)
                if hit(px, py, 42, 52) then clickCell(x, y) end
            end
        end
        for i = 1, #G.hand do
            if hit(260 - 8, 8 + (i - 1) * step, small and 43 or 50, step) then clickHand(i) end
        end
    end
    if imgui.IsWindowHovered() and imgui.IsMouseClicked(1) then G.selected = nil end
end

-- a card picture in a list (no arrows): 42x51 times scale
local function inlineCard(id, scale)
    local pic = cardTexture(id)
    if pic then
        imgui.Image(pic.ptr, { 42 * scale, 51 * scale }, { 0, 0 }, { pic.w / pic.tw, pic.h / pic.th })
    else
        imgui.Dummy({ 42 * scale, 51 * scale })
    end
end

local function cardLabel(c)
    return string.format('%s  %s', c.code, NAMES and NAMES[c.id] or ('card ' .. c.id))
end

local function drawShop()
    local sh = G.shop
    imgui.TextColored(GOLD, sh.name or 'Card Trader')
    imgui.SameLine()
    imgui.Text(string.format('   Your gil: %s', G.gil and tostring(G.gil) or '?'))
    imgui.SameLine()
    if imgui.Button('Leave shop') then G.shop = nil; return end
    imgui.TextWrapped('Every card you buy gets its own arrows and hidden numbers, so two of the same card can play differently.')
    imgui.Separator()

    if imgui.BeginTabBar and imgui.BeginTabBar('##tmshop') then
        if imgui.BeginTabItem('Buy') then
            for i, st in ipairs(sh.stock) do
                inlineCard(st.id, 0.75)
                imgui.SameLine()
                imgui.BeginGroup()
                imgui.TextColored(TIER_COLORS[st.tier] or WHITE, cardLabel(st))
                imgui.Text(string.format('%d gil   %s', st.price, TIER_NAMES[st.tier] or ''))
                if imgui.Button('Buy##b' .. i) then send('buy ' .. i) end
                imgui.EndGroup()
                if i % 3 ~= 0 then imgui.SameLine(i % 3 == 1 and 190 or 380) end
            end
            imgui.EndTabItem()
        end
        if imgui.BeginTabItem('Sell') then
            if not G.cards then
                imgui.Text('Loading your cards...')
            else
                imgui.Text(string.format('Your cards: %d / %d', #G.cards, G.maxCards))
                for _, c in ipairs(G.cards) do
                    local price = G.sellPrices and G.sellPrices[c.tier] or 0
                    imgui.TextColored(TIER_COLORS[c.tier] or WHITE, string.format('#%d  %s%s', c.uid, cardLabel(c), c.inDeck and '  (deck)' or ''))
                    imgui.SameLine(330)
                    if imgui.Button(string.format('Sell %d gil##s%d', price, c.uid)) then send('sell ' .. c.uid) end
                end
            end
            imgui.EndTabItem()
        end
        imgui.EndTabBar()
    end
end

local function drawMenu()
    if G.shop then
        drawShop()
        return
    end
    imgui.TextColored(GOLD, 'Tetra Master')
    imgui.Text('Play the computer. Winning pays gil. Buy cards from tavern card traders, find more on monsters and in caskets.')
    imgui.Separator()
    for _, lv in ipairs({ 'easy', 'normal', 'hard' }) do
        if imgui.RadioButton(lv:sub(1, 1):upper() .. lv:sub(2) .. '##lv', S.level == lv) then S.level = lv; saveSettings() end
        imgui.SameLine()
    end
    if imgui.Button('Play') then send('play ' .. S.level) end
    imgui.SameLine()
    if imgui.Button(G.cards and 'Refresh my cards' or 'My cards') then send('cards') end

    if G.cards then
        imgui.Separator()
        local picked = 0
        for _ in pairs(G.deckPick) do picked = picked + 1 end
        imgui.Text(string.format('Your cards (%d / %d). Tick 5 for your deck (%d ticked):', #G.cards, G.maxCards, picked))
        if #G.cards < 5 then
            imgui.TextWrapped('You need 5 cards to play. Card traders in the taverns sell starter cards; monsters and treasure caskets drop more.')
        end
        local n = 0
        for _, c in ipairs(G.cards) do
            local box = { G.deckPick[c.uid] == true }
            imgui.PushStyleColor(ImGuiCol_Text, TIER_COLORS[c.tier] or WHITE)
            local changed = imgui.Checkbox(string.format('#%d  %s##c%d', c.uid, cardLabel(c), c.uid), box)
            imgui.PopStyleColor()
            if changed then
                G.deckPick[c.uid] = box[1] or nil
            end
            n = n + 1
            if n % 2 == 1 then imgui.SameLine(260) end
        end
        if picked == 5 and imgui.Button('Save deck') then
            local list = {}
            for uid in pairs(G.deckPick) do list[#list + 1] = uid end
            table.sort(list)
            send('deck ' .. table.concat(list, ' '))
        end
    end
end

local function render()
    if not G.open[1] then return end
    local s = S.scale
    local inGame = (G.phase ~= 'menu')
    if inGame then
        imgui.SetNextWindowSize({ 320 * s + 16, 240 * s + 70 }, ImGuiCond_Always)
    else
        imgui.SetNextWindowSize({ 560, 420 }, ImGuiCond_FirstUseEver)
    end
    local flags = inGame and bit.bor(ImGuiWindowFlags_NoResize, ImGuiWindowFlags_NoScrollbar,
        ImGuiWindowFlags_NoScrollWithMouse) or 0
    G.inWindow = true
    if imgui.Begin('Tetra Master', G.open, flags) then
        if inGame then
            ox, oy = vec2(imgui.GetCursorScreenPos())
            drawBoard()
            imgui.SetCursorScreenPos({ ox, oy + 240 * s + 6 })
            if G.phase == 'over' then
                if imgui.Button('Play again') then send('play ' .. (G.level or S.level)) end
                imgui.SameLine()
                if imgui.Button('Back') then G.phase = 'menu'; music(false) end
            else
                if imgui.Button('Give up') then send('quit') end
                imgui.SameLine()
                local status
                if G.choose and myTurn() then status = 'Choose which card to fight.'
                elseif myTurn() then status = G.selected and 'Now click a free square.' or 'Your turn: click a card in your hand.'
                else status = 'Opponent (' .. tostring(G.level) .. ')...' end
                imgui.Text(status)
            end
        else
            drawMenu()
        end
        if G.note ~= '' and now() < G.noteUntil then imgui.TextColored({ 1, 0.5, 0.5, 1 }, G.note) end
    end
    imgui.End()
    G.inWindow = false
end

------------------------------------------------------------------------------
-- Events
------------------------------------------------------------------------------
ashita.events.register('load', 'tm_load', function()
    loadSettings()
    loadAll()
    local okNames, names = pcall(dofile, HERE .. 'cardnames.lua')
    if okNames and type(names) == 'table' then NAMES = names end
end)

ashita.events.register('unload', 'tm_unload', function()
    music(false)
end)

ashita.events.register('command', 'tm_command', function(e)
    local args = e.command:args()
    if #args == 0 or (args[1]:lower() ~= '/tm' and args[1]:lower() ~= '/tetramaster') then return end
    e.blocked = true
    local sub = (args[2] or ''):lower()
    if sub == '' then
        G.open[1] = not G.open[1]
        if G.open[1] then send('state') end
    elseif sub == 'play' then
        local lv = (args[3] or S.level):lower()
        if lv ~= 'easy' and lv ~= 'normal' and lv ~= 'hard' then lv = 'normal' end
        S.level = lv
        G.open[1] = true
        send('play ' .. lv)
    elseif sub == 'quit' then
        send('quit')
    elseif sub == 'scale' then
        S.scale = math.max(1, math.min(4, tonumber(args[3] or '') or 2))
        saveSettings()
    elseif sub == 'music' then
        S.music = not S.music
        music(S.music and G.phase ~= 'menu')
        saveSettings()
        say('music ' .. (S.music and 'on' or 'off'))
    elseif sub == 'sound' then
        S.sound = not S.sound
        saveSettings()
        say('sound ' .. (S.sound and 'on' or 'off'))
    elseif sub == 'volume' then
        local v = tonumber(args[3])
        if v then
            S.volume = math.max(0, math.min(100, math.floor(v)))
            saveSettings()
            if musicOpen and okWinmm then
                pcall(function() winmm.mciSendStringA('setaudio tm_music volume to ' .. tostring(S.volume * 10), nil, 0, nil) end)
            end
        end
        say('volume ' .. tostring(S.volume) .. ' (/tm volume 0-100)')
    else
        say('/tm, /tm play [easy|normal|hard], /tm quit, /tm scale <1-4>, /tm music, /tm sound, /tm volume <0-100>')
    end
end)

ashita.events.register('text_in', 'tm_text_in', function(e)
    if e.blocked then return end
    local text = tostring(e.message_modified or e.message or ''):gsub('%z', ''):gsub('[\30\31].', '')
    local at = text:find('tetramaster:', 1, true)
    if at then
        e.blocked = true
        local body = text:sub(at + 12):gsub('%s+$', '')
        pcall(onLine, body)
        return
    end
    if now() < G.hideUntil and text:find('!tm ', 1, true) then e.blocked = true end -- the echo of our own commands
end)

ashita.events.register('d3d_present', 'tm_present', function()
    pump()
    if G.phase ~= 'menu' then updateQueue() end
    local ok, err = pcall(render)
    if not ok then
        if G.inWindow then pcall(imgui.End); G.inWindow = false end
        if now() > (G.lastErr or 0) + 5 then G.lastErr = now(); say('draw error: ' .. tostring(err)) end
    end
end)
