"""Home Point #1 of the four port towns stands at its pre-2015 spot; a jump inside the zone is done by the game, to
today's spot. fast_travel.lua moves the player to the crystal after such a jump (notsensible, 2026-11-22).

Run with: python test_moved_homepoints.py [server folder]      (needs lupa; default C:\\ffxi-local\\server)
The module is loaded with stand-ins for the server, a pretend player and pretend timers.
"""
import os
import sys
from lupa import luajit21 as lupa
lua = lupa.LuaRuntime(unpack_returned_tuples=True)
SERVER = sys.argv[1] if len(sys.argv) > 1 else os.environ.get('XIFO_SERVER', r'C:\ffxi-local\server')
src = open(os.path.join(SERVER, 'modules', 'custom', 'late', 'fast_travel.lua'), encoding='utf-8').read()
lua.execute('''
overrides = {}
supers = 0
Module = { new = function(self, name) return { addOverride = function(_, target, fn) overrides[target] = fn end } end }
super = function(...) supers = supers + 1 end
xi = { zone = setmetatable({}, { __index = function(t, k) local v = rawget(t, '__n') or 100; rawset(t, '__n', v + 1); rawset(t, k, v); return v end }),
       settings = { main = { HOMEPOINT_TELEPORT = 1 } }, teleport = { type = {} }, keyItem = {}, survivalGuide = {}, homepoint = {} }
zones = setmetatable({}, { __index = function() return { text = {} } end })
local real_require = require
require = function(name)
    if name:find('survival_guide_map') then return setmetatable({}, { __index = function() return {} end }) end
    return {}
end
''')
ok = lua.execute('local f, err = loadstring(...) ; if not f then return err end; local ok, e = pcall(f); if not ok then return e end; return true', src)
print('load:', ok)
lua.execute('''
function newPlayer(zone, x, z)
    local p = { zone = zone, x = x, z = z, timers = {}, moved = nil }
    function p:getZoneID() return self.zone end
    function p:getXPos() return self.x end
    function p:getZPos() return self.z end
    function p:setPos(x, y, z, rot) self.x, self.z, self.moved = x, z, { x, y, z, rot } end
    function p:timer(ms, fn) self.timers[#self.timers + 1] = { ms, fn } end
    return p
end
-- runs the pending timers one by one; step(p, i) may move the player before look i
function run(p, step)
    local i = 0
    while #p.timers > 0 do
        i = i + 1
        local t = table.remove(p.timers, 1)
        if step then step(p, i) end
        t[2](p)
        if i > 40 then error('timers never end') end
    end
    return i
end
finish = overrides['xi.homepoint.onEventFinish']
''')
g = lua.globals()
PW = lua.eval('xi.zone.PORT_WINDURST'); PS = lua.eval('xi.zone.PORT_SAN_DORIA'); OTHER = lua.eval('xi.zone.WINDURST_WOODS')
results = []
def check(name, cond):
    results.append((name, bool(cond))); print(('ok   ' if cond else 'FAIL ') + name)

# 1. same-zone jump already done when the window closes (answer 3, no index in the upper bits)
lua.execute('p = newPlayer(%d, -188, 101); finish(p, 8700, 3, 8700); n = run(p)' % PW)
check('already at today\'s spot when the window closes: moved to the crystal', lua.eval('p.moved ~= nil and p.moved[1] == -67.980 and p.moved[3] == 110.675 and p.moved[4] == 192'))
check('  ... and the looking stops', lua.eval('n == 1'))

# 2. the game's own move comes 3 seconds after the window closes
lua.execute('p = newPlayer(%d, -207, 210); finish(p, 8700, 3, 8700); n = run(p, function(pl, i) if i == 4 then pl.x, pl.z = -186, 99 end end)' % PW)
check('the game moves you 3 s later: still moved to the crystal', lua.eval('p.moved ~= nil and p.moved[1] == -67.980'))

# 3. an answer with other upper bits and another choice code than 3
lua.execute('p = newPlayer(%d, -40, -60); finish(p, 8700, 0x00160003 + 0x40000000, 8700); run(p)' % PS)
check('any upper bits: Port San d\'Oria #1 corrected', lua.eval('p.moved ~= nil and p.moved[1] == -66.077'))

# 4. a jump to another crystal in the zone is left alone
lua.execute('p = newPlayer(%d, -68, 110); finish(p, 8700, 3, 8700); n = run(p, function(pl, i) if i == 2 then pl.x, pl.z = -207, 210 end end)' % PW)
check('a jump to crystal #2: not touched', lua.eval('p.moved == nil'))
check('  ... looked 12 times, then stopped', lua.eval('n == 12'))

# 5. closing the window at the Port San d'Oria crystal and running to today's spot (50 yalms off) is not a jump
lua.execute('''p = newPlayer(%d, -66, -105); finish(p, 8700, 0, 8700)
run(p, function(pl, i) pl.x = math.min(-38, pl.x + 4); pl.z = math.min(-63, pl.z + 6) end)''' % PS)
check('running from the crystal to today\'s spot: not touched', lua.eval('p.moved == nil and p.x == -38 and p.z == -63'))

# 6. setting the home point, a server teleport, another zone, the switch off, another event
lua.execute('p = newPlayer(%d, -188, 101); finish(p, 8700, 1, 8700)' % PW); check('set home point: no looking', lua.eval('#p.timers == 0'))
lua.execute('p = newPlayer(%d, -188, 101); finish(p, 8700, 2 + 22 * 65536, 8700)' % PW); check('server teleport: no looking', lua.eval('#p.timers == 0'))
lua.execute('p = newPlayer(%d, -188, 101); finish(p, 8700, 3, 8700)' % OTHER); check('a zone without a moved crystal: no looking', lua.eval('#p.timers == 0'))
lua.execute('xi.settings.main.HOMEPOINT_TELEPORT = 0; p = newPlayer(%d, -188, 101); finish(p, 8700, 3, 8700); xi.settings.main.HOMEPOINT_TELEPORT = 1' % PW); check('fast travel off: no looking', lua.eval('#p.timers == 0'))
lua.execute('p = newPlayer(%d, -188, 101); finish(p, 123, 3, 8700)' % PW); check('another event: no looking', lua.eval('#p.timers == 0'))

# 7. zoning away while it looks
lua.execute('p = newPlayer(%d, -68, 110); finish(p, 8700, 3, 8700); n = run(p, function(pl, i) if i == 2 then pl.zone = %d; pl.x, pl.z = -188, 101 end end)' % (PW, OTHER))
check('zoned away: stops, not touched', lua.eval('p.moved == nil and n == 2'))
check('the base handler ran every time', lua.eval('supers == 11'))
bad = [n for n, ok in results if not ok]
print('%d checks, %d failed' % (len(results), len(bad)))
sys.exit(1 if bad else 0)
