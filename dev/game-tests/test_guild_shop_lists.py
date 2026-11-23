"""(Yumainai, Meli, 2026-11-22) The Goldsmiths' Guild list had blank first and last pages: the "full refill every day"
house rule also refilled the lines a guild only resells after a player sold them to it, so every line was on the shelf
from the second game day (at once with "Guild shops never run out"): 124 at the Goldsmiths', more than the game's guild
window can show. Only what a guild stocks itself is refilled now.

Run with: python test_guild_shop_lists.py [server folder]      (needs lupa; default C:\\ffxi-local\\server)
"""
import os
import sys
from lupa import luajit21 as lupa
SERVER = sys.argv[1] if len(sys.argv) > 1 else os.environ.get('XIFO_SERVER', r'C:\ffxi-local\server')
passed = failed = 0


def check(name, ok):
    global passed, failed
    if ok:
        passed += 1
    else:
        failed += 1
        print('FAIL:', name)


lua = lupa.LuaRuntime(unpack_returned_tuples=True)
lua.execute('''
day = 100
function VanadielUniqueDay() return day end
function VanadielDayOfTheWeek() return 0 end
function VanadielHour() return 12 end
function GetReadOnlyItem(id) return { getBasePrice = function() return 100 end } end
local n = 1000
xi = { settings = { main = { GUILD_SHOPS_ALWAYS_STOCKED = 0, GUILD_SHOP_HOLIDAYS = false, GUILD_SHOPS_ALWAYS_OPEN = 0 } },
       item = setmetatable({}, { __index = function(t, k) n = n + 1; rawset(t, k, n); return n end }),
       day = setmetatable({}, { __index = function() return 1 end }), caskets = {}, shop = {} }
overrides = {}
Module = { new = function() return { addOverride = function(_, name, fn) overrides[name] = fn end } end }
require = function(name) return {} end
print = function() end
''')
for parts in (('scripts', 'data', 'guild_shops.lua'), ('scripts', 'globals', 'guild_shops.lua'),
              ('modules', 'custom', 'late', 'shop_house_rules.lua'), ('modules', 'custom', 'late', 'comforts.lua')):
    lua.globals().SRC = open(os.path.join(SERVER, *parts), encoding='utf-8').read()
    result = lua.eval("(function() local fn, e = loadstring(SRC); if not fn then return e end; local ok, e2 = pcall(fn); return ok and 'ok' or e2 end)()")
    check('loads: ' + parts[-1] + ' ' + str(result), result == 'ok')
lua.execute('''
function npc(name) return { getName = function() return name end } end
function list(name, stocked)
    xi.settings.main.GUILD_SHOPS_ALWAYS_STOCKED = stocked and 1 or 0
    super = xi.guildShops.onBuyList
    return overrides['xi.guildShops.onBuyList']({}, npc(name))
end
function count(name, stocked, d) xi.guildShops.state = {}; day = 100; local a = #list(name, stocked); day = 100 + d; return a, #list(name, stocked) end
function stocksItself(name) local n = 0; for _, c in ipairs(xi.data.guildShops[name].stock) do if c.initial > 0 or c.restockRate > 0 then n = n + 1 end end; return n end
function worst(stocked) local w = 0
    for k, shop in pairs(xi.data.guildShops) do if shop.stock then local _, n = count(k, stocked, 3); if n > w then w = n end end end
    return w end
function fullNextDay(name) xi.guildShops.state = {}; day = 100; list(name, false); day = 101
    for _, cfg in ipairs(xi.data.guildShops[name].stock) do
        if cfg.initial > 0 and cfg.targetStock > 0 then
            local found
            for _, it in ipairs(list(name, false)) do if it.id == cfg.id then found = it end end
            if not found or found.count < cfg.targetStock then return false end
        end
    end
    return true end
''')
ev = lua.eval
own = ev("stocksItself('Visala')")
check("the Goldsmiths' Guild stocks some lines itself and resells many more", 0 < own < 40 and ev("#xi.data.guildShops['Visala'].stock") > 100)
check('day one, switch off: only its own lines', ev("(count('Visala', false, 1))") == own)
check('the next game day: still only its own lines', ev("select(2, count('Visala', false, 1))") == own)
check('a week later: the same', ev("select(2, count('Visala', false, 7))") == own)
check('"Guild shops never run out": its own lines, no more', ev("(count('Visala', true, 1))") == own and ev("select(2, count('Visala', true, 1))") == own)
check('what it stocks is full again the next day (the house rule still holds)', ev("fullNextDay('Visala')"))
check('with the switch every one of its lines is full at once',
      ev("(function() xi.guildShops.state = {}; day = 100; for _, it in ipairs(list('Visala', true)) do if it.count < 15 then return false end end; return true end)()"))
check('no guild list is longer than 60 lines, switch off', ev('worst(false)') <= 60)
check('no guild list is longer than 60 lines, switch on', ev('worst(true)') <= 60)
check('no count or maximum over 255 (one byte each in the packet)',
      ev("(function() for k, shop in pairs(xi.data.guildShops) do for _, c in ipairs(shop.stock or {}) do if c.maxStock > 255 or c.targetStock > 255 then return false end end end return true end)()"))
print(f'{passed} passed, {failed} failed')
sys.exit(1 if failed else 0)
