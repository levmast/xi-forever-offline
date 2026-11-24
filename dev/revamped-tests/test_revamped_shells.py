"""Tests for the Revamped shell addons (addons-src/GambitsRevamped, addons-src/SquadsRevamped) and rv_switch.lua.
Run: python test_revamped_shells.py   (needs lupa; pure LuaJIT with a fake Ashita, nothing touches a real game folder)
Proves: shells load silently (no print, no command, no draw), the switch file parses, the question appears only when a
package marker exists and nothing was answered, Yes writes use_revamped=1 and unloads the old addons, No changes nothing else,
a saved Yes unloads the old addons once, a saved No never does, a saved Yes with only shells installed never unloads.
"""
import os
import tempfile
import unittest

import lupa

KIT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ADDONS = os.path.join(KIT, "addons-src")

BOOT = """
rv = { printed = {}, commands = {}, events = {}, registered_cmds = 0, calls = {} }
function print(...) table.insert(rv.printed, table.concat({...}, ' ')) end
addon = {}
package.path = ADDON_DIR .. '/?.lua;' .. package.path
package.loaded['common'] = true
package.loaded['imgui'] = setmetatable({}, { __index = function(t, k)
    return function(...) table.insert(rv.calls, k) if k == 'Begin' then return true end return false end
end })
ashita = { events = { register = function(ev, name, fn)
                rv.events[ev] = fn
                if ev == 'command' then rv.registered_cmds = rv.registered_cmds + 1 end
            end },
           fs = { exists = function(p) return FS_EXISTS(p) end, create_dir = function(p) MKDIR(p) end } }
AshitaCore = { GetInstallPath = function() return INSTALL end,
               GetChatManager = function() return { QueueCommand = function(_, m, c) table.insert(rv.commands, c) end } end }
"""


def fresh(addon, files=()):
    """A Lua state with a fake Ashita whose install path is a temp folder holding the given marker files."""
    root = tempfile.mkdtemp(prefix="rvtest_")
    for rel in files:
        path = os.path.join(root, "addons", rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        open(path, "w").write("-- marker\n")
    lua = lupa.LuaRuntime(unpack_returned_tuples=True)
    g = lua.globals()
    g.ADDON_DIR = os.path.join(ADDONS, addon).replace("\\", "/")
    g.INSTALL = root + "\\"
    g.FS_EXISTS = lambda p: os.path.exists(p.replace("\\", os.sep))
    g.MKDIR = lambda p: os.makedirs(p.replace("\\", os.sep), exist_ok=True)
    lua.execute(BOOT)
    return lua, root


def choice_file(root):
    return os.path.join(root, "config", "addons", "revamped", "choice.txt")


def items(lua, expr):
    return list(lua.eval(expr).values())


class Shells(unittest.TestCase):
    def test_shell_is_silent_and_registers_no_command(self):
        for name in ("GambitsRevamped", "SquadsRevamped"):
            lua, root = fresh(name)
            lua.execute("dofile(ADDON_DIR .. '/%s.lua')" % name)
            for _ in range(600):
                lua.eval("rv.events['d3d_present']")()
            self.assertEqual(items(lua, "rv.printed"), [], name)
            self.assertEqual(lua.eval("rv.registered_cmds"), 0, name)
            self.assertEqual(items(lua, "rv.commands"), [], name)
            self.assertNotIn("Begin", items(lua, "rv.calls"), name)       # draws nothing
            self.assertFalse(os.path.exists(choice_file(root)), name)       # writes nothing

    def test_shell_names_and_files(self):
        for name in ("GambitsRevamped", "SquadsRevamped"):
            main = open(os.path.join(ADDONS, name, name + ".lua"), encoding="utf-8").read()
            self.assertIn("addon.name = '%s'" % name, main)
            self.assertTrue(os.path.isfile(os.path.join(ADDONS, name, "rv_switch.lua")))
        a = open(os.path.join(ADDONS, "GambitsRevamped", "rv_switch.lua"), "rb").read()
        b = open(os.path.join(ADDONS, "SquadsRevamped", "rv_switch.lua"), "rb").read()
        self.assertEqual(a, b)

    def ticks(self, lua, n=400):
        lua.execute("RV = require('rv_switch'); IM = package.loaded['imgui']")
        for _ in range(n):
            lua.execute("RV.tick(IM)")

    def test_parse(self):
        lua, _ = fresh("GambitsRevamped")
        lua.execute("RV = require('rv_switch')")
        p = lua.eval("function(t) local r = RV.parse(t) return tostring(r.asked) .. ':' .. tostring(r.use) end")
        self.assertEqual(p("asked=1\nuse_revamped=1\n"), "true:true")
        self.assertEqual(p("asked=1\r\nuse_revamped=0\r\n"), "true:false")
        self.assertEqual(p(""), "false:nil")
        self.assertEqual(p("garbage"), "false:nil")

    def test_no_question_for_shell_only(self):
        lua, root = fresh("GambitsRevamped", files=["GambitsRevamped/GambitsRevamped.lua", "SquadsRevamped/SquadsRevamped.lua"])
        self.ticks(lua)
        self.assertNotIn("Begin", items(lua, "rv.calls"))
        self.assertEqual(items(lua, "rv.commands"), [])

    def test_question_when_package_present_and_unanswered(self):
        lua, root = fresh("GambitsRevamped", files=["GambitsRevamped/gr_editor.lua"])
        self.ticks(lua)
        self.assertIn("Begin", items(lua, "rv.calls"))
        self.assertEqual(items(lua, "rv.commands"), [])               # asking changes nothing
        self.assertFalse(os.path.exists(choice_file(root)))

    def test_yes_saves_and_unloads_old(self):
        lua, root = fresh("SquadsRevamped", files=["SquadsRevamped/sr_window.lua"])
        lua.execute("RV = require('rv_switch')")
        self.assertTrue(lua.eval("RV.set(true)"))
        text = open(choice_file(root)).read()
        self.assertIn("use_revamped=1", text)
        self.assertIn("asked=1", text)
        self.assertEqual(items(lua, "rv.commands"), ["/addon unload squadpanel", "/addon unload Gambits"])
        self.assertTrue(lua.eval("RV.is_on()"))
        lua.execute("rv.calls = {}")
        self.ticks(lua)
        self.assertNotIn("Begin", items(lua, "rv.calls"))              # answered: never asked again

    def test_no_changes_nothing(self):
        lua, root = fresh("SquadsRevamped", files=["SquadsRevamped/sr_window.lua"])
        lua.execute("RV = require('rv_switch')")
        self.assertTrue(lua.eval("RV.set(false)"))
        self.assertIn("use_revamped=0", open(choice_file(root)).read())
        self.assertEqual(items(lua, "rv.commands"), [])
        self.ticks(lua)
        self.assertEqual(items(lua, "rv.commands"), [])
        self.assertFalse(lua.eval("RV.is_on()"))

    def saved(self, lua, root, text):
        os.makedirs(os.path.dirname(choice_file(root)))
        open(choice_file(root), "w").write(text)

    def test_saved_yes_unloads_old_once_per_load(self):
        lua, root = fresh("GambitsRevamped", files=["GambitsRevamped/gr_editor.lua"])
        self.saved(lua, root, "asked=1\nuse_revamped=1\n")
        self.ticks(lua, 800)
        self.assertEqual(items(lua, "rv.commands"), ["/addon unload squadpanel", "/addon unload Gambits"])

    def test_saved_yes_with_shell_only_does_not_unload(self):
        lua, root = fresh("GambitsRevamped")
        self.saved(lua, root, "asked=1\nuse_revamped=1\n")
        self.ticks(lua, 800)
        self.assertEqual(items(lua, "rv.commands"), [])

    def test_saved_no_never_unloads(self):
        lua, root = fresh("SquadsRevamped", files=["SquadsRevamped/sr_window.lua"])
        self.saved(lua, root, "asked=1\nuse_revamped=0\n")
        self.ticks(lua, 800)
        self.assertEqual(items(lua, "rv.commands"), [])


if __name__ == "__main__":
    unittest.main()
