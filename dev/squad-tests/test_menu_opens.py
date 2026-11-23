"""(Hasuko, 2026-11-22, right after v0.3.0) "Uhh @Hurami": a red box "MESSAGE FROM DEAR IMGUI ... Missing
PopStyleColor()" (13 times) and "Missing PopStyleVar()" (6 times), and no Squads menu.

servermenu 1.26g added the menu's background opacity. The menu window called opacityOf(), but that helper stood
BELOW the menu window in the file. In Lua a local function does not exist above the line that defines it, so the
call failed on every frame, after the window's 13 colours and 6 style values were pushed and before they were
taken back: the menu never opened. 1.26i moves the helper above the menu.

This test loads the whole add-on with a stand-in Ashita and a stand-in ImGui that has EVERY function, opens the
menu, walks through every tab and checks that the window is drawn, nothing is left pushed and no problem is
reported. It also reads the add-ons' source for any other local function that is called above its definition.

Run: python test_menu_opens.py      (needs lupa; reads addons-src/servermenu and addons-src/squadpanel)
"""
import os
import re
import sys
import tempfile
from lupa import luajit21 as lupa

KIT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MENU = os.path.join(KIT, "addons-src", "servermenu", "servermenu.lua")
PANEL = os.path.join(KIT, "addons-src", "squadpanel", "squadpanel.lua")
passed = failed = 0


def check(name, ok):
    global passed, failed
    if ok:
        passed += 1
    else:
        failed += 1
        print("FAIL:", name)


# ---------------------------------------------------------------- 1. nothing is called above its own definition
def called_too_early(path):
    """Top-level 'local function name' / 'local name' that is called on a line above it (strings and comments are
    left out). Returns [(name, line of the call, line of the definition)]."""
    lines = open(path, encoding="utf-8", errors="replace").read().split("\n")
    code, in_block = [], False
    for line in lines:
        if in_block:
            if "]]" in line:
                in_block = False
            code.append("")
            continue
        s = re.sub(r"'(?:\\.|[^'\\])*'|\"(?:\\.|[^\"\\])*\"", "''", line)
        if "--[[" in s and "]]" not in s.split("--[[", 1)[1]:
            in_block = True
        code.append(s.split("--")[0])
    first = {}
    for i, s in enumerate(code):
        m = re.match(r"local function ([A-Za-z_]\w*)", s)
        if m:
            first.setdefault(m.group(1), i)
            continue
        m = re.match(r"local ([A-Za-z_][\w, ]*?)\s*(=|;|$)", s)
        if m:
            for n in m.group(1).split(","):
                first.setdefault(n.strip(), i)
            continue
        m = re.match(r"(?:function )?([A-Za-z_]\w*)\s*=\s*function", s)
        if m:
            first.setdefault(m.group(1), -1)
    out = []
    for name, at in first.items():
        if at <= 0 or len(name) < 3:
            continue
        pat = re.compile(r"(?<![\w.:])" + re.escape(name) + r"\s*\(")
        for i in range(at):
            if pat.search(code[i]):
                out.append((name, i + 1, at + 1))
                break
    return out


for path in (MENU, PANEL):
    early = called_too_early(path)
    check(f"{os.path.basename(path)}: no local function is called above the line that defines it {early}", early == [])

src = open(MENU, encoding="utf-8").read()
check("opacityOf stands above the menu window", src.index("local function opacityOf(") < src.index("local function menuWindow("))
check("and it is defined once", src.count("local function opacityOf(") == 1)
check("the checker itself finds the old mistake", called_too_early.__doc__ is not None and (lambda p: (
    open(p, "w", encoding="utf-8").write("local function a()\n    return helper(1);\nend\nlocal function helper(x) return x; end\n"),
    called_too_early(p))[1])(os.path.join(tempfile.mkdtemp(), "x.lua")) == [("helper", 2, 4)])

# ---------------------------------------------------------------- 2. the real add-on, opened
HARNESS = r'''
W = { handlers = {}, clock = 100, printed = {}, clicks = {}, buttons = {}, begins = {}, alpha = {},
      balance = 0, colors = 0, vars = 0, childs = 0, sent = {} }
local chat = {}
function chat:QueueCommand(mode, command) W.sent[#W.sent + 1] = command end
function chat:IsInputOpen() return false end
addon = {}
ashita = { events = { register = function(name, id, fn) W.handlers[name] = fn end },
           time = { get_tick64 = function() return W.clock * 1000 end },
           fs = { create_directory = function(path) os.execute('mkdir -p "' .. path .. '"') end } }
AshitaCore = { GetChatManager = function() return chat end, GetInstallPath = function() return WORK_DIR end }
function string.args(s) local t = {} for w in s:gmatch('%S+') do t[#t + 1] = w end return t end
package.loaded['common'] = true
package.preload['imgui'] = function()
    -- every ImGui function exists here (as the real one does): what the add-on asks for with has() is all there
    local im = setmetatable({}, { __index = function(_, name) return function() end end })
    function im.Begin(title) W.begins[#W.begins + 1] = title; W.balance = W.balance + 1 return true end
    function im.End() W.balance = W.balance - 1 end
    function im.BeginChild() W.childs = W.childs + 1 return true end
    function im.EndChild() W.childs = W.childs - 1 end
    function im.PushStyleColor() W.colors = W.colors + 1 end
    function im.PopStyleColor(n) W.colors = W.colors - (n or 1) end
    function im.PushStyleVar() W.vars = W.vars + 1 end
    function im.PopStyleVar(n) W.vars = W.vars - (n or 1) end
    function im.SetNextWindowBgAlpha(a) W.alpha[#W.alpha + 1] = a end
    function im.Button(l) W.buttons[#W.buttons + 1] = l
        if W.clicks[l] then W.clicks[l] = nil return true end return false end
    function im.BeginCombo() return false end
    function im.BeginPopupContextItem() return false end
    function im.BeginPopup() return false end
    function im.BeginTooltip() return false end
    function im.BeginTable() return false end
    function im.BeginTabBar() return false end
    function im.CollapsingHeader() return false end
    function im.IsItemHovered() return false end
    function im.IsItemActive() return false end
    function im.IsMouseDragging() return false end
    function im.Checkbox() return false end
    function im.Selectable() return false end
    function im.InputText() return false end
    function im.MenuItem() return false end
    function im.GetWindowWidth() return 620 end
    function im.GetFontSize() return 13 end
    function im.GetWindowPos() return 18, 240 end
    function im.GetMouseDragDelta() return { 0, 0 } end
    function im.CalcTextSize(t) return { #tostring(t or '') * 7, 13 } end
    function im.GetContentRegionAvail() return { 600, 400 } end
    function im.GetCursorScreenPos() return { 0, 0 } end
    function im.GetCursorPos() return { 0, 0 } end
    return im
end
for name, v in pairs({ ImGuiCol_Button = 21, ImGuiCol_ButtonHovered = 22, ImGuiCol_ButtonActive = 23, ImGuiCol_Text = 0, ImGuiCol_WindowBg = 2,
                       ImGuiCol_ChildBg = 3, ImGuiCol_Border = 5, ImGuiCol_FrameBg = 7, ImGuiCol_FrameBgHovered = 8, ImGuiCol_CheckMark = 18,
                       ImGuiCol_Header = 24, ImGuiCol_HeaderHovered = 25, ImGuiCol_Separator = 27, ImGuiCol_PlotHistogram = 40,
                       ImGuiCol_TitleBg = 10, ImGuiCol_TitleBgActive = 11,
                       ImGuiStyleVar_WindowRounding = 3, ImGuiStyleVar_ChildRounding = 7, ImGuiStyleVar_FrameRounding = 12,
                       ImGuiStyleVar_WindowPadding = 2, ImGuiStyleVar_ItemSpacing = 14, ImGuiStyleVar_FramePadding = 11, ImGuiStyleVar_Alpha = 0,
                       ImGuiCond_FirstUseEver = 4, ImGuiCond_Always = 1, ImGuiWindowFlags_NoTitleBar = 1, ImGuiWindowFlags_NoCollapse = 32,
                       ImGuiWindowFlags_NoMove = 4 }) do rawset(_G, name, v) end
print = function(...) local parts = {} for i = 1, select('#', ...) do parts[#parts + 1] = tostring((select(i, ...))) end
    W.printed[#W.printed + 1] = table.concat(parts, ' ') end
assert(loadfile(MENU_PATH))()
-- from here on, reading a global that does not exist is an error, as "attempt to call a nil value" is in the game
setmetatable(_G, { __index = function(_, k) error('undefined global ' .. tostring(k), 2) end })
if W.handlers.load then W.handlers.load() end
function W.frame() W.clock = W.clock + 0.1; W.buttons = {}; W.begins = {}; W.handlers.d3d_present() end
function W.click(l) W.clicks[l] = true; W.frame(); W.frame() end
function W.command(text) local e = { command = text, blocked = false } W.handlers.command(e) return e end
function W.drew(part) for _, t in ipairs(W.begins) do if t:find(part, 1, true) then return true end end return false end
function W.hasButton(part) for _, b in ipairs(W.buttons) do if b:find(part, 1, true) then return b end end return nil end
function W.problem() for _, t in ipairs(W.printed) do if t:find('hit a problem', 1, true) then return t end end return nil end
function W.clean() return W.balance == 0 and W.colors == 0 and W.vars == 0 and W.childs == 0 end
function W.state() return table.concat({ W.balance, W.colors, W.vars, W.childs }, ',') end
'''


def boot(path):
    """Loads the add-on file at path with the stand-in Ashita and ImGui. Returns (lua, eval)."""
    rt = lupa.LuaRuntime(unpack_returned_tuples=True)
    rt.globals().MENU_PATH = path
    rt.globals().WORK_DIR = tempfile.mkdtemp().replace('\\', '/') + '/'
    rt.execute(HARNESS)
    return rt, rt.eval


lua, ev = boot(MENU)

lua.execute("W.frame()")
check("closed: only the small button is drawn", ev("#W.begins == 1 and not W.drew('Offline##servermenu')"))
check("closed: nothing is left pushed " + ev("W.state()"), ev("W.clean()"))
open_button = ev("W.hasButton('##sm_open')")
check("the Squads button is there", open_button is not None)

lua.execute("W.click(%r)" % (open_button or "Squads##sm_open"))
check("a click on the Squads button draws the menu window", ev("W.drew('XI: Forever Offline##servermenu')"))
check("no 'the menu hit a problem' line: " + str(ev("W.problem()")), ev("W.problem() == nil"))
check("open: every colour and style value pushed is taken back " + ev("W.state()"), ev("W.clean()"))
check("at 100% the background is left alone", ev("#W.alpha == 0"))

tabs = re.search(r"local TABS\s*=\s*\{([^}]*)\}", src)
names = re.findall(r"'([^']+)'", tabs.group(1)) if tabs else []
check("the tabs are read from the add-on", len(names) >= 3)
for name in names:
    lua.execute("W.click(%r)" % f"{name}##tab{name}")
    check(f"tab {name}: the menu is still drawn", ev("W.drew('Offline##servermenu')"))
    check(f"tab {name}: nothing left pushed " + ev("W.state()"), ev("W.clean()"))
    check(f"tab {name}: no problem reported: " + str(ev("W.problem()")), ev("W.problem() == nil"))

# (1.26j, Hasuko) Attack my target / Stop on the Squad tab
lua.execute("W.click('Squad##tabSquad')")
check("the Squad tab has Attack my target and Stop", ev("W.hasButton('Attack my target##sqattack') ~= nil and W.hasButton('Stop##sqstop') ~= nil"))
lua.execute("W.sent = {}; W.click('Attack my target##sqattack'); for i = 1, 60 do W.frame() end")
check("a click on Attack my target says !squad attack: " + str(list(ev("W.sent").values())),
      ev("(function() for _, c in ipairs(W.sent) do if c == '/say !squad attack' then return true end end return false end)()"))
lua.execute("W.sent = {}; W.click('Stop##sqstop'); for i = 1, 60 do W.frame() end")
check("a click on Stop says !squad stop",
      ev("(function() for _, c in ipairs(W.sent) do if c == '/say !squad stop' then return true end end return false end)()"))
check("and the menu is still clean " + ev("W.state()"), ev("W.drew('Offline##servermenu') and W.clean() and W.problem() == nil"))

lua.execute("W.command('/menu opacity menu 50'); W.alpha = {}; W.frame()")
check("/menu opacity menu 50 hands 0.5 to the window", ev("#W.alpha == 1 and math.abs(W.alpha[1] - 0.5) < 0.001"))
check("and the menu is still drawn and clean " + ev("W.state()"), ev("W.drew('Offline##servermenu') and W.clean() and W.problem() == nil"))
lua.execute("W.command('/menu opacity menu 100'); W.alpha = {}; W.frame()")
check("back at 100 the background is left alone again", ev("#W.alpha == 0"))

lua.execute("W.command('/menu'); W.frame()")
check("/menu closes it", ev("not W.drew('Offline##servermenu') and W.clean()"))
lua.execute("W.command('/menu'); W.frame()")
check("/menu opens it again", ev("W.drew('Offline##servermenu') and W.clean() and W.problem() == nil"))

# the same harness must FAIL on the order v0.3.0 was published with: the test is worth something only if it catches it
block_at = src.index("local function opacityOf(")
block_end = src.index("end", src.index("return math.max(10", block_at)) + len("end")
block = src[block_at:block_end]
moved = src[:block_at] + src[block_end:]
button_at = moved.index("local function buttonWindow()")
old = moved[:button_at] + block + "\n\n" + moved[button_at:]
check("the old order is rebuilt: the helper below the menu window",
      old.index("local function opacityOf(") > old.index("local function menuWindow("))
bad = os.path.join(tempfile.mkdtemp(), "servermenu_old.lua")
open(bad, "w", encoding="utf-8").write(old)
lua2, ev2 = boot(bad)
lua2.execute("W.frame(); W.click(W.hasButton('##sm_open') or 'Squads##sm_open')")
check("old order: the menu window is NOT drawn", not ev2("W.drew('Offline##servermenu')"))
check("old order: the add-on reports the problem: " + str(ev2("W.problem()")), "opacityOf" in str(ev2("W.problem()")))
lua2.execute("W.command('/menu'); W.frame(); W.frame()")
check("old order: opened again, 13 colours and 6 style values stay pushed on every frame (Hasuko's red box) " + ev2("W.state()"),
      ev2("W.colors >= 13 and W.vars >= 6"))

check("the version note says so", "(1.26i) the menu opens again" in src)
print(f"{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
