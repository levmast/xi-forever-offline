"""Squad mates on your linkshell (squad_shell.lua): who is a member, where the lines go, written answers, answers
through the chat AI for members that are out, the now-and-then lines of members that are not, hello at log in.

Run with: python test_squad_shell.py [server folder]      (needs lupa; default C:\\ffxi-local\\server)
"""
import os
import sys

from lupa import luajit21 as lupa

SERVER = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("XIFO_SERVER", r"C:\ffxi-local\server")
lua = lupa.LuaRuntime(unpack_returned_tuples=True)
lua.globals().SRC = open(os.path.join(SERVER, "modules", "custom", "lua", "squad_shell.lua"), encoding="utf-8").read()
lua.execute("""
clock = 1000
os.time = function() return clock end
squad = { { id = 7, slot = 1, name = 'Kasumi', mjob = 1, nation = 1 }, { id = 9, slot = 2, name = 'Kyo', mjob = 4, nation = 2 },
          { id = 11, slot = 3, name = 'Momo', mjob = 3, nation = 0 } }
GetSquad = function() return squad end
out = {}                                   -- mate ids out with you
sentToAI = {}
aiOn = false
xi = { squad = { outIds = function() return out end,
                 shellToAI = function(p, text) if aiOn and next(out) then sentToAI[#sentToAI + 1] = text return true end return false end } }
said = {}
function newPlayer(link1, link2)
    local p = { vars = {}, lvars = {}, heard = {}, timers = {}, link = { [16] = link1, [17] = link2 } }
    function p:getID() return 1 end
    function p:getName() return 'Hurami' end
    function p:getCharVar(n) return self.vars[n] or 0 end
    function p:setCharVar(n, v) self.vars[n] = v end
    function p:getLocalVar(n) return self.lvars[n] or 0 end
    function p:setLocalVar(n, v) self.lvars[n] = v end
    function p:getEquippedItem(slot) return self.link[slot] end
    function p:printToPlayer(text, channel, name) self.heard[#self.heard + 1] = { text = text, channel = channel, name = name } end
    function p:timer(ms, fn) self.timers[#self.timers + 1] = { ms = ms, fn = fn } end
    return p
end
-- runs the timers waiting now (not the ones they start); the clock moves on by the longest of them
function run(p)
    local now = p.timers; p.timers = {}
    local longest = 0
    for _, t in ipairs(now) do longest = math.max(longest, t.ms) end
    clock = clock + math.ceil(longest / 1000)
    for _, t in ipairs(now) do t.fn(p) end
    return #now
end
say = function(p, msg) said[#said + 1] = msg end
S = loadstring(SRC)()
""")
ev = lua.eval
results = []


def check(name, cond):
    results.append(bool(cond))
    print(("ok   " if cond else "FAIL ") + name)


# membership
lua.execute("p = newPlayer({}, nil); S.command(p, say, nil, nil)")
check("nobody on the linkshell at first, and the command says how", "None of your squad mates" in ev("said[#said]"))
lua.execute("S.command(p, say, '1', 'on'); S.command(p, say, '2', 'on')")
check("!squad ls 1 on / 2 on: two members", ev("#S.members(p) == 2 and p.vars.SQUAD_SHELL_7 == 1 and p.vars.SQUAD_SHELL_9 == 1 and p.vars.SQUAD_SHELL_11 == nil"))
check("lockstyle's SQUAD_LS_ names are not used", ev("(function() for k in pairs(p.vars) do if k:sub(1, 9) == 'SQUAD_LS_' then return false end end return true end)()"))
lua.execute("S.command(p, say, nil, nil)")
check("the list names them", "Kasumi, Kyo" in ev("said[#said]"))
lua.execute("S.command(p, say, '5', 'on')")
check("no mate in that slot", "no squad mate in slot 5" in ev("said[#said]"))
lua.execute("S.command(p, say, '1', 'maybe')")
check("anything but on / off shows the help", "on | off" in ev("said[#said]"))

# where the lines go
check("first linkshell worn: its chat", ev("S.channel(newPlayer({}, nil)) == 5"))
check("only the second worn: that one", ev("S.channel(newPlayer(nil, {})) == 27"))
check("none worn: nowhere", ev("S.channel(newPlayer(nil, nil)) == nil"))
lua.execute("bare = newPlayer(nil, nil); S.command(bare, say, 'all', 'on')")
check("joining without a linkshell says to equip one", "not wearing a linkshell" in ev("said[#said]"))

# you speak, nobody out, no AI: one written answer, on the linkshell, by a member, a moment later
lua.execute("p.timers = {}; p.heard = {}; S.onPlayerChat(p, 'hello everyone')")
check("nothing is said at once", ev("#p.heard == 0 and #p.timers == 1 and p.timers[1].ms >= 2000 and p.timers[1].ms <= 5000"))
lua.execute("run(p)")
check("a member answers on the linkshell", ev("#p.heard == 1 and p.heard[1].channel == 5 and (p.heard[1].name == 'Kasumi' or p.heard[1].name == 'Kyo')"))
check("a greeting gets a greeting", ev("(function() for _, l in ipairs(S.lines.greet) do if (l:gsub('{master}', 'Hurami')) == p.heard[1].text then return true end end return false end)()"))
check("what you said, sorted", ev("S.kindOf('where are you guys?') == 'where' and S.kindOf('thanks!') == 'thanks' and S.kindOf('good night all') == 'bye' and S.kindOf('that NM was rough') == 'other' and S.kindOf('Hey') == 'greet' and S.kindOf('what are you up to') == 'where'"))
check("a line names the mate's home town and you", ev("S.written(p, squad[2], 'where'):find('Windurst') ~= nil") and "{" not in ev("S.written(p, squad[1], 'upTo') .. S.written(p, squad[1], 'hello')"))

# a mate that is not a member never talks there
lua.execute("names = {}; for i = 1, 40 do p.heard = {}; p.timers = {}; S.onPlayerChat(p, 'hi'); run(p); if p.heard[1] then names[p.heard[1].name] = true end end")
check("only members answer (Momo is not one)", ev("names.Momo == nil and (names.Kasumi or names.Kyo)"))

# a member out with you + the chat AI: your line goes to the helper, its answer goes to the linkshell
lua.execute("out = { [7] = true }; aiOn = true; p.heard = {}; p.timers = {}; S.onPlayerChat(p, 'how is everyone')")
check("the line goes to the chat helper", ev("#sentToAI == 1 and sentToAI[1] == 'how is everyone'"))
check("for a while the member's AI answer goes to the linkshell", ev("S.channelForReply(p, 'Kasumi') == 5"))
check("a mate that is not a member still answers in party chat", ev("S.channelForReply(p, 'Momo') == nil"))
lua.execute("clock = clock + 41")
check("later, AI lines are party chat again", ev("S.channelForReply(p, 'Kasumi') == nil"))
lua.execute("away = {}; for i = 1, 60 do p.heard = {}; p.timers = {}; S.onPlayerChat(p, 'hi'); run(p); if p.heard[1] then away[p.heard[1].name] = true end end")
check("with the AI answering for the one out, a written answer comes only from the member that is not out", ev("away.Kyo == true and away.Kasumi == nil"))
lua.execute("aiOn = false; both = {}; for i = 1, 60 do p.heard = {}; p.timers = {}; S.onPlayerChat(p, 'hi'); run(p); if p.heard[1] then both[p.heard[1].name] = true end end")
check("AI off: written answers from members out and not out alike", ev("both.Kyo == true and both.Kasumi == true"))

# now and then: only members that are not out, never right after you spoke, and it keeps going
lua.execute("out = { [7] = true }; q = newPlayer({}, nil); q.vars.SQUAD_SHELL_7 = 1; q.vars.SQUAD_SHELL_9 = 1; clock = clock + 100; S.onGameIn(q, true)")
check("crossing a zone line starts the round again, without a hello", ev("#q.timers == 1 and q.timers[1].ms >= 480000 and q.timers[1].ms <= 960000"))
lua.execute("run(q)")
check("after 8 to 16 minutes a member that is not out says what it is up to", ev("#q.heard == 1 and q.heard[1].name == 'Kyo' and q.heard[1].channel == 5") and "Windurst" in ev("q.heard[1].text"))
check("and the next one is waiting", ev("#q.timers == 1"))
lua.execute("q.heard = {}; q.lvars.SQUAD_SHELL_LAST = clock + 990; run(q)")
check("not right after you spoke", ev("#q.heard == 0 and #q.timers == 1"))
lua.execute("old = q.timers[1]; q.timers = {}; S.onGameIn(q, true); q.heard = {}; old.fn(q)")
check("an older round stops when a new one starts (no doubled lines after zoning)", ev("#q.heard == 0 and #q.timers == 1"))
lua.execute("r = newPlayer({}, nil); r.vars.SQUAD_SHELL_11 = 1; S.onGameIn(r, false); n = #r.timers; run(r)")
check("logging in: a hello from a member", ev("n == 2") and ev("(function() for _, h in ipairs(r.heard) do if h.name == 'Momo' and h.channel == 5 then return true end end return false end)()"))
lua.execute("e = newPlayer({}, nil); S.onGameIn(e, false)")
check("no members: nothing runs", ev("#e.timers == 0"))
lua.execute("p.heard = {}; p.timers = {}; S.command(p, say, 'all', 'off'); S.onPlayerChat(p, 'hi'); run(p)")
check("!squad ls all off: quiet again", ev("#S.members(p) == 0 and #p.heard == 0"))
check("every kind of job has lines", ev("(function() for _, k in ipairs({ 'fighter', 'mage', 'healer', 'rogue', 'ranger', 'bard' }) do if #S.lines.upTo[k] < 4 then return false end end return true end)()"))
print("%d checks, %d failed" % (len(results), results.count(False)))
sys.exit(1 if False in results else 0)
