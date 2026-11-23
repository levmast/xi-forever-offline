"""(Hasuko, FalconX51, Yenkei, 2026-11-22) The camp's pull window is counted from the lowest of you and your living
squad mates, and every chat line about it says so (they showed your own level, so a party with lower mates looked stuck).

Run with: python test_squad_camp_base.py [server folder]      (needs lupa; default C:\\ffxi-local\\server)
"""
import os
import re, sys
from lupa import luajit21 as lupa
SERVER = sys.argv[1] if len(sys.argv) > 1 else os.environ.get('XIFO_SERVER', r'C:\ffxi-local\server')
src = open(os.path.join(SERVER, 'modules', 'custom', 'lua', 'squad.lua'), encoding='utf-8').read()
a = src.index("function squadCampBase(player)"); b = src.index("local function campPick(player, c)")
lua = lupa.LuaRuntime(unpack_returned_tuples=True)
lua.execute('''
function mk(name, lvl, alive) return { getMainLvl = function() return lvl end, getName = function() return name end, getPacketName = function() return name end, isAlive = function() return alive ~= false end } end
mates = {}
local function squadTrusts(player) return mates end
function squadCampLevels(player) return LOW or -6, HIGH or 2, false end
''' + "\n" + src[a:b].replace("squadTrusts(player)", "mates_of(player)") + '''
''')
lua.execute("function mates_of(p) return mates end")
ev = lua.eval
ok = True
def check(name, cond):
    global ok
    print(("ok   " if cond else "FAIL ") + name); ok = ok and bool(cond)
lua.execute("you = mk('Hasuko', 30)")
check("alone: your own level", ev("select(1, squadCampBase(you)) == 30 and select(2, squadCampBase(you)) == 'Hasuko'"))
check("alone: window text has no 'counted from'", ev("squadCampWindowText(you) == 'level 24-32'"))
lua.execute("mates = { mk('Aster', 18), mk('Bob', 25), mk('Dead', 5, false), mk('Zero', 0) }")
check("lowest living mate sets the base", ev("select(1, squadCampBase(you)) == 18 and select(2, squadCampBase(you)) == 'Aster'"))
check("the text says whose level it is", ev("squadCampWindowText(you) == 'level 12-20 (counted from Aster, the lowest in your party at 18)'"))
check("a chosen window is shown as given", ev("squadCampWindowText(you, -20, 20) == 'level 1-38 (counted from Aster, the lowest in your party at 18)'"))
lua.execute("mates = { mk('High', 60) }")
check("a higher mate does not raise it", ev("select(1, squadCampBase(you)) == 30"))
check("campPick uses the same base", "local lvl = squadCampBase(player)" in src)
check("the helper sits after squadTrusts (it is a local)", src.index("local function squadTrusts(player)") < src.index("function squadCampBase(player)"))
check("no chat line builds the window from your own level any more", "player:getMainLvl() + CAMP_LEVELS" not in src)
sys.exit(0 if ok else 1)
