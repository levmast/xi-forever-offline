"""Squad food choice (squad_meals.lua + squad_food.lua): the menu, the one-time unlock for the auction house price,
and what a mate that is out is told to eat. Altair's suggestion, the user's rule (2026-11-22).

Run with: python test_squad_meals.py [server folder]      (needs lupa; default C:\\ffxi-local\\server)
"""
import os
import sys

from lupa import luajit21 as lupa

SERVER = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("XIFO_SERVER", r"C:\ffxi-local\server")
LUA = os.path.join(SERVER, "modules", "custom", "lua")
lua = lupa.LuaRuntime(unpack_returned_tuples=True)
lua.execute("""
xi = { settings = { main = { AH_PRICE_RATE = 1 } }, effect = { FOOD = 251 } }
said = {}
function newPlayer(gil)
    local p = { gil = gil, vars = {}, menus = {}, frozen = false }
    function p:getCharVar(n) return self.vars[n] or 0 end
    function p:setCharVar(n, v) self.vars[n] = v end
    function p:getGil() return self.gil end
    function p:delGil(n) self.gil = self.gil - n end
    function p:setFreezeFlag(f) self.frozen = f end
    function p:timer(ms, fn) fn(self) end                    -- "a moment later" happens at once here
    function p:customMenu(m) self.menus[#self.menus + 1] = m end
    return p
end
function newTrust(mateId)
    local t = { vars = { SQUAD_ID = mateId }, effects = { [251] = true } }
    function t:getLocalVar(n) return self.vars[n] or 0 end
    function t:setLocalVar(n, v) self.vars[n] = v end
    function t:delStatusEffect(e) self.effects[e] = nil end
    return t
end
-- picks the option whose label starts with the text, in the newest menu; returns false when it is not on that page
function pick(p, text)
    local m = p.menus[#p.menus]
    for _, o in ipairs(m.options) do
        if o[1]:sub(1, #text) == text then o[2](p) return true end
    end
    return false
end
-- pages through "More..." until the option is there
function find(p, text)
    for _ = 1, 20 do
        if pick(p, text) then return true end
        if not pick(p, 'More...') then return false end
    end
    return false
end
function labels(p) local m = p.menus[#p.menus]; local out = {} for _, o in ipairs(m.options) do out[#out + 1] = o[1] end return table.concat(out, ' | ') end
""")
lua.globals().FOODSRC = open(os.path.join(LUA, "squad_food.lua"), encoding="utf-8").read()
lua.globals().MEALSRC = open(os.path.join(LUA, "squad_meals.lua"), encoding="utf-8").read()
lua.execute("""
food = loadstring(FOODSRC)()
M = loadstring(MEALSRC)()
deps = function(trusts) return { food = food, say = function(p, msg) said[#said + 1] = msg end, trusts = trusts or {} } end
mate = { id = 7, slot = 2, name = 'Kasumi', mjob = 1 }
""")
results = []


def check(name, cond):
    results.append(bool(cond))
    print(("ok   " if cond else "FAIL ") + name)


ev = lua.eval
# the data
check("every food has a kind the menu knows, a price, an id and a length",
      ev("(function() local kinds = {} for _, k in ipairs(food.kinds) do kinds[k] = true end local n = 0 for key, m in pairs(food.foods) do n = n + 1 if not (kinds[m.kind] and m.price > 0 and m.id > 0 and m.duration > 0) then return false end end return n >= 30 end)()"))
check("no item id twice", ev("(function() local seen = {} for _, m in pairs(food.foods) do if seen[m.id] then return false end seen[m.id] = true end return true end)()"))
check("every food the mates pick themselves is still in the list",
      ev("(function() for _, t in ipairs(food.tiers) do for _, key in pairs(t.foods) do if food.foods[key] == nil then return false end end end return true end)()"))
check("a kind's foods come cheapest first", ev("(function() local l = M.ofKind(food, 'attack') for i = 2, #l do if l[i].price < l[i - 1].price then return false end end return #l >= 5 end)()"))

# the menu: unlock, pay once, choose
lua.execute("p = newPlayer(5000); t = newTrust(7); t.vars.SQUAD_FOOD_ID = 4371; t.vars.SQUAD_FOOD_FX = 1; t.vars.SQUAD_FOOD_UNTIL = 999; d = deps({ t }); handled = M.command(p, { mate }, '2', nil, d)")
check("!squad food 2 opens the menu and holds the player still", ev("handled == true and #p.menus == 1 and p.frozen == true"))
check("the first page: its own pick, then the kind its job eats", ev("labels(p)").startswith("As it comes (by job and level) | Fighter food"))
check("the title says what it eats now", "Kasumi eats: as it comes" in ev("p.menus[1].title"))
lua.execute("ok1 = find(p, 'Fighter food'); ok2 = find(p, 'Meat Mithkabob')")
check("a locked food shows its price and asks first", ev("ok1 and ok2") and "Unlock Meat Mithkabob for 740 gil?" in ev("p.menus[#p.menus].title"))
lua.execute("pick(p, 'Yes')")
check("yes: 740 gil paid, unlocked, chosen", ev("p.gil == 4260 and p.vars.SQUAD_FOODU_4381 == 1 and p.vars.SQUAD_FOOD_7 == 4381"))
check("the mate that is out is told, and its present meal ends", ev("t.vars.SQUAD_FOOD_PICK == 4381 and t.vars.SQUAD_FOOD_UNTIL == 0 and t.effects[251] == nil"))
check("what a mate out eats now", ev("M.chosen(t, food).name == 'Meat Mithkabob'"))

# a second mate takes the same food: free
lua.execute("mate2 = { id = 9, slot = 3, name = 'Kyo', mjob = 1 }; M.command(p, { mate, mate2 }, '3', nil, d); find(p, 'Fighter food'); found = find(p, 'Meat Mithkabob (unlocked)')")
check("unlocked once: the next mate gets it free, no question", ev("found and p.gil == 4260 and p.vars.SQUAD_FOOD_9 == 4381"))

# not enough gil
lua.execute("poor = newPlayer(100); M.command(poor, { mate }, '2', nil, deps()); find(poor, 'Mage food'); find(poor, 'Vermillion Jelly'); pick(poor, 'Yes')")
check("too little gil: nothing paid, nothing unlocked, told why", ev("poor.gil == 100 and poor.vars.SQUAD_FOODU_5158 == nil and poor.vars.SQUAD_FOOD_7 == nil") and "costs 30,000 gil" in ev("said[#said]"))
# saying no
lua.execute("q = newPlayer(9000); M.command(q, { mate }, '2', nil, deps()); find(q, 'Tank food'); find(q, 'Boiled Crab'); pick(q, 'No.')")
check("no: nothing paid, back at the tank foods", ev("q.gil == 9000 and q.vars.SQUAD_FOODU_4456 == nil") and "Tank food" in ev("q.menus[#q.menus].title"))
# the auction house price rule moves the cost
lua.execute("xi.settings.main.AH_PRICE_RATE = 0.5; half = M.price(food.foods['meat_mithkabob']); xi.settings.main.AH_PRICE_RATE = 1")
check("auction house prices at 0.5x halve the unlock", ev("half == 370"))
# back to its own pick
lua.execute("M.command(p, { mate }, '2', 'auto', d)")
check("!squad food 2 auto: its own pick again", ev("p.vars.SQUAD_FOOD_7 == 0 and t.vars.SQUAD_FOOD_PICK == 0 and M.chosen(t, food) == nil"))
lua.execute("M.command(p, { mate }, '2', nil, d); pick(p, 'As it comes')")
check("the menu's first line does the same", ev("p.vars.SQUAD_FOOD_7 == 0"))
# a called mate remembers
lua.execute("p.vars.SQUAD_FOOD_7 = 4456; t2 = newTrust(7); M.onSpawn(p, t2, mate)")
check("a mate called later knows what it was told", ev("M.chosen(t2, food).name == 'Boiled Crab'"))
check("no mate in that slot", ev("M.command(p, { mate }, '5', nil, d) == true") and "no squad mate in slot 5" in ev("said[#said]"))
check("anything that is not a slot is left to the old command", ev("M.command(p, { mate }, 'list', nil, d) == false"))
lua.execute("""pages = 0; r = newPlayer(1); M.command(r, { mate }, '2', nil, deps()); find(r, 'Fighter food')
for _ = 1, 20 do pages = pages + 1; if #r.menus[#r.menus].options > 3 then pages = -100 end; if not pick(r, 'More...') then break end end
last = labels(r)""")
check("never more than three lines on a page, and the last page offers Back.", ev("pages > 1") and ev("last").endswith("Back."))
print("%d checks, %d failed" % (len(results), results.count(False)))
sys.exit(1 if False in results else 0)
