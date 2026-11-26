--[[
    VanaSync bridge for XI: Forever Offline (Ashita v4)

    Sends the game's music-relevant state (combat, group size, alliance, zone,
    cutscene) to the local VanaSync player, which plays JØ's battle mixes
    (Solo / Party / Alliance). While VanaSync really is playing one of its own
    tracks, the game's music is faded out with the client's own music-volume
    command (packet 0x060); sound effects and voices are untouched. If the
    player stops answering, crashes or closes, the game's music comes straight
    back.

    Off by default: switch it on at OPTIONS > Addons. While it is on and the
    world runs, the launcher starts the VanaSync player window
    (launcher_vanasync.py); the add-on only talks to it over loopback UDP.

    Commands: /vanasync [status|restore|fade <time>|debug]
    (restore toggles: keep the game's own music on no matter what)
]]

addon.name    = 'vanasync'
addon.author  = 'XI: Forever Offline (VanaSync by JØ × NOX)'
addon.version = '0.1.0'
addon.desc    = 'Plays VanaSync battle music and hands the game music back when it stops.'
addon.link    = 'https://xiforever.com'

require('common')
local socket = require('socket')

local HOST, GAME_PORT = '127.0.0.1', 8766
local SEND_EVERY = 0.25    -- seconds between snapshots
local OWNER_TIMEOUT = 1.5  -- no reply this long: give the music back to the game
local FULL, SILENT = 127, 0

local settings = {
    fade = 30,         -- 0x060 fade time (client units; tune on the PC)
    debug = false,
}

local udp = nil
local last_send, last_reply = 0, 0
local own = false          -- VanaSync says it is playing its own track
local volume = nil         -- last volume we asked the client for (nil = untouched)
local hold = false         -- /vanasync restore: keep the game's music on until asked again

local function msg(text)
    print(('\30\81[VanaSync]\30\01 %s'):format(text))
end

-- 0x060 GP_SERV_COMMAND_MUSICVOLUME: header (id 9 bits | size 7 bits, sync), time, volume.
local function set_music_volume(level, time)
    if volume == level then return end
    volume = level
    local t = math.max(0, math.min(0xFFFF, time or settings.fade))
    local header = 0x060 + bit.lshift(0x08 / 4, 9)
    local bytes = {
        bit.band(header, 0xFF), bit.rshift(header, 8), 0, 0,
        bit.band(t, 0xFF), bit.rshift(t, 8),
        bit.band(level, 0xFF), 0,
    }
    AshitaCore:GetPacketManager():AddIncomingPacket(0x060, bytes)
    if settings.debug then msg(('game music volume -> %d'):format(level)) end
end

local function give_back(time)
    own = false
    if volume ~= nil and volume ~= FULL then set_music_volume(FULL, time) end
end

local function snapshot()
    local mm = AshitaCore:GetMemoryManager()
    local party = mm:GetParty()
    local members, alliance = 0, false
    for i = 0, 17 do
        if party:GetMemberIsActive(i) == 1 then
            members = members + 1
            if i >= 6 then alliance = true end
        end
    end
    local player = GetPlayerEntity()
    local status = player and player.Status or 0
    return {
        v = 1,
        engaged = status == 1,
        cutscene = status == 4,
        members = math.max(1, members),
        alliance = alliance,
        zone = party:GetMemberZone(0) or 0,
    }
end

local function encode(t)
    return ('{"v":1,"engaged":%s,"cutscene":%s,"members":%d,"alliance":%s,"zone":%d}'):format(
        tostring(t.engaged), tostring(t.cutscene), t.members, tostring(t.alliance), t.zone)
end

ashita.events.register('load', 'vanasync_load', function()
    udp = socket.udp()
    udp:settimeout(0)
    udp:setpeername(HOST, GAME_PORT)
end)

ashita.events.register('unload', 'vanasync_unload', function()
    give_back(0)
    if udp then udp:close() end
end)

ashita.events.register('d3d_present', 'vanasync_tick', function()
    if not udp then return end
    local now = socket.gettime()

    -- Read every reply waiting: {"own":true|false}
    while true do
        local data = udp:receive()
        if not data then break end
        last_reply = now
        own = data:find('"own":%s*true') ~= nil
    end

    if now - last_send >= SEND_EVERY then
        last_send = now
        local ok, state = pcall(snapshot)
        if ok then udp:send(encode(state)) end
    end

    if own and not hold and now - last_reply < OWNER_TIMEOUT then
        set_music_volume(SILENT)
    else
        give_back()
    end
end)

-- After zoning the client restarts its music; ask again for the level we want.
ashita.events.register('packet_in', 'vanasync_zone', function(e)
    if e.id == 0x000A then volume = nil end
end)

ashita.events.register('command', 'vanasync_command', function(e)
    local args = e.command:args()
    if #args == 0 or args[1]:lower() ~= '/vanasync' then return end
    e.blocked = true
    local sub = (args[2] or 'status'):lower()
    if sub == 'restore' then
        hold = not hold
        if hold then
            give_back(0)
            msg('Game music kept on. /vanasync restore again lets VanaSync take over.')
        else
            msg('VanaSync may take over the music again.')
        end
    elseif sub == 'fade' and tonumber(args[3]) then
        settings.fade = tonumber(args[3])
        msg(('Fade time %d.'):format(settings.fade))
    elseif sub == 'debug' then
        settings.debug = not settings.debug
        msg('Debug ' .. (settings.debug and 'on' or 'off') .. '.')
    else
        local connected = socket.gettime() - last_reply < OWNER_TIMEOUT
        msg(('Player %s; %s.'):format(connected and 'connected' or 'not connected',
            own and 'VanaSync is playing (game music faded)' or 'game music playing'))
    end
end)
