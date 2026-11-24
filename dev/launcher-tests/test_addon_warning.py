"""(Unleashable 11-20, PikaFox and Bigbadbill 11-22, Neet 11-22: "First letter of the bot chatter is getting cutoff")
Ashita's chatfix add-on is for servers that send chat in the old layout. On this server it cuts the first letter off
every chat line and the Squads menu and Gambits stop reading the server. It sits in the launcher's add-on list like any
other Ashita add-on (PikaFox: "at least have a warning on it that says Do not use").

The Addons page now shows a red warning on it and asks before it is switched on. Switching it off is never asked.
Run: python test_addon_warning.py      (the page itself needs a screen; its code is read here)
"""
import os
import sys

KIT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, KIT)
import launcher_core as core

passed = failed = 0


def check(name, ok):
    global passed, failed
    if ok:
        passed += 1
    else:
        failed += 1
        print("FAIL:", name)


w = core.addon_warning("addon", "chatfix")
check("chatfix has a warning", bool(w))
check("it says not to use it here, and what it does", w and "Do not use here" in w and "first letter" in w and "Squads menu" in w)
check("the name is matched in any spelling of capitals", core.addon_warning("addon", "ChatFix") == w)
check("a plugin of that name is not meant", core.addon_warning("plugin", "chatfix") is None)
for name in ("servermenu", "Gambits", "xiui", "timestamps", "fps", ""):
    check(f"no warning on {name or 'an empty name'}", core.addon_warning("addon", name) is None)
check("none of our own add-ons is warned about", not (set(core.ADDON_WARNINGS) & core.OWN_ADDONS))

gui = open(os.path.join(KIT, "launcher_gui.pyw"), encoding="utf-8").read()
page = gui[gui.index("        for n in names:\n            info = core.addon_info(ashita, n)"):gui.index("    def remove(self, name, origin):")]
check("the row shows the warning in place of the description, in red",
      'warning = core.addon_warning(self.kind, n)' in page and 'text=warning or info["desc"]' in page and "fg=RED if warning else DIM" in page)
toggle = page[page.index("    def toggle(self, name, var):"):]
check("switching a warned add-on ON is asked first, No by default",
      "if warning and var.get() and not messagebox.askyesno(" in toggle and 'default="no"' in toggle)
check("a No leaves it off and writes nothing", toggle.index("var.set(False)") < toggle.index("self.scripts.set(self.kind, name, var.get())")
      and "return" in toggle[toggle.index("var.set(False)"):toggle.index("self.scripts.set(")])
check("switching it OFF is never asked (the question needs var.get())", "warning and var.get()" in toggle)
print(f"{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
