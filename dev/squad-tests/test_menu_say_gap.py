"""(Dugahst, 2026-11-22) "All the buttons randomly do it": a click in the Squads window showed up in the chat log as
">> /say !squad camp start" and nothing happened. The game drops a chat line that follows another too closely. The
menu waited 2.2 s after a click, but only 0.6 s after one of its own refreshes, so a click right after a refresh was
lost. Now every chat line the menu sends waits 2.2 s after the last one it sent, and a click goes before a refresh.

Run: python test_menu_say_gap.py      (needs lupa; reads addons-src/servermenu/servermenu.lua)
"""
import os
import sys
from lupa import luajit21 as lupa

KIT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
src = open(os.path.join(KIT, "addons-src", "servermenu", "servermenu.lua"), encoding="utf-8").read()
passed = failed = 0


def check(name, ok):
    global passed, failed
    if ok:
        passed += 1
    else:
        failed += 1
        print("FAIL:", name)


lua = lupa.LuaRuntime(unpack_returned_tuples=True)
check("the whole add-on still loads", lua.eval('function(s) local f, e = loadstring(s) return f and "ok" or e end')(src) == "ok")
start = src.index("-- (1.26h) the menu's own refreshes")
end = src.index("-- squad.lua 1.13 added a tenth field")
lua.execute('''
sent = {}
S = { queue = {}, lastSend = -1000 }
function actionsWatchdog() end
function chatManager() return { QueueCommand = function(_, mode, c) sent[#sent + 1] = c end } end
function typing() return false end
''' + src[start:end] + '''
_G.pump = pump
function add(at, c) S.queue[#S.queue + 1] = { at = at, command = c } end
function fresh() sent = {}; S.queue = {}; S.lastSay = nil; S.lastSend = -1000 end
-- runs the clock and notes when each line goes out: { {time, line}, ... }
function play(from, to)
    local log, n = {}, #sent
    for i = 0, math.floor((to - from) * 10 + 0.5) do
        local t = from + i / 10
        pump(t)
        if #sent > n then log[#log + 1] = { t, sent[#sent] }; n = #sent end
    end
    return log
end
''')
ev = lua.eval

# the case from the report: a refresh went out, the player clicks Start 0.7 s later
lua.execute("fresh(); add(10, '/say !squad panel'); a = play(10, 10.5); add(10.7, '/say !squad camp start'); b = play(10.6, 14)")
check("the refresh goes out at once", ev("#a == 1 and a[1][1] == 10 and a[1][2] == '/say !squad panel'"))
check("the click is sent, once", ev("#b == 1 and b[1][2] == '/say !squad camp start'"))
check("and only 2.2 s after the refresh (before: 0.6 s, and the game dropped it)", ev("b[1][1] >= 12.2 - 0.001 and b[1][1] <= 12.3"))

# quick clicks with a refresh due at the same time: clicks first, 2.2 s apart, the refresh last
lua.execute("fresh(); add(20, '/say !squad panel'); add(20, '/say !squad call all'); add(20, '/say !squad camp here'); add(20.1, '/say !squad camp start'); c = play(20, 30)")
check("every line goes out", ev("#c == 4"))
check("the clicks in the order they were made, before the refresh",
      ev("c[1][2] == '/say !squad call all' and c[2][2] == '/say !squad camp here' and c[3][2] == '/say !squad camp start' and c[4][2] == '/say !squad panel'"))
check("each at least 2.2 s after the one before", ev("c[2][1] - c[1][1] >= 2.2 - 0.001 and c[3][1] - c[2][1] >= 2.2 - 0.001 and c[4][1] - c[3][1] >= 2.2 - 0.001"))

# a sheet refresh and the Actions check count as refreshes too
lua.execute("fresh(); add(40, '/say !squad sheet 2'); add(40, '/say !actions'); add(40, '/say !squad dismiss 1'); d = play(40, 48)")
check("a click goes before the sheet refresh and the Actions check", ev("d[1][2] == '/say !squad dismiss 1' and #d == 3"))

# what is not a chat line is not held back by the chat wait
lua.execute("fresh(); S.lastSay = 60; S.lastSend = 60; add(60.2, '/autobox off'); e = play(60.2, 61.5)")
check("a command that is not a chat line goes 0.6 s after the last send", ev("#e == 1 and e[1][1] <= 60.7"))

# nothing is sent while the player is typing, and nothing is lost by that
lua.execute("fresh(); typing = function() return true end; add(70, '/say !squad call 1'); f = play(70, 73); typing = function() return false end; g = play(73, 74)")
check("typing holds the line back and it goes afterwards", ev("#f == 0 and #g == 1"))

check("the old 0.6 s wait after a refresh is gone", "S.sendGap" not in src)
check("the version note says so", "(1.26h) a click right after a refresh is no longer dropped" in src)
print(f"{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
