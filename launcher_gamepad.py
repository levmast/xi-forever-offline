"""Controller setup from the launcher (2026-11-22), instead of FFXI's own FFXiPadConfig.exe.

The game keeps its controller settings in two registry values, which Ashita applies from the boot file's
[ffxi.registry] section at every start:
- padmode000: six switches: gamepad on, vibration, sliders, hat switches (D-pad), works in the background, XInput.
- padsin000: 27 slots, one per game action, each holding the button or stick axis that does it (-1 = nothing).
  Up/down share one axis and left/right another; a negative axis number reverses it.
-1 in either value means "leave the game's own" (what FFXiPadConfig.exe saved).

Ported from LocalXI (seamuswilkie31-dev/LocalXI, GPL-3.0, src/LocalXI.Core/Game/Gamepad.cs). The Xbox (XInput) layout
matches retail's own "Alternate Setup E" value slot for slot. The PlayStation (DirectInput) numbers come from LocalXI and
Ashita's docs and have not been tried on a real pad here yet.

Saved in gamepad.json next to the launcher. Nothing here touches the boot file unless "managed" is on (or was on the
last time, to put the game's own settings back)."""
import json
import os
import re
import shutil

SLOTS = 27
NONE = -1
REGISTRY = "ffxi.registry"
INPUT = "ashita.input"

# (id, name shown, XInput?)  Nintendo pads have no usable Windows driver: Steam Input or BetterJoy make them XInput.
CONTROLLERS = (("xbox", "Xbox (or any XInput pad)"), ("ps4", "PlayStation 4"), ("ps5", "PlayStation 5"),
               ("switch", "Nintendo Switch Pro"), ("switch2", "Nintendo Switch 2 Pro"))
CONTROLLER_NAMES = dict(CONTROLLERS)

# the actions a button can be given: (padsin slot, what it does). Slots 13-24 are the sticks and D-pad, set from the layout.
ACTIONS = ((7, "Confirm / open the action menu"), (5, "Cancel"), (6, "Main menu"), (8, "Switch the active window"),
           (0, "Auto-run"), (1, "Ctrl macro bar"), (3, "Alt macro bar"), (4, "Heal / lock target"),
           (2, "First / third person camera"), (9, "Show or hide windows"), (12, "Log out window"),
           (25, "Screenshot (windows hidden)"), (10, "Hold: left stick moves in menus"),
           (11, "Hold: left stick moves the camera"), (26, "Switch movement / menu / camera"))
ACTION_SLOTS = {slot for slot, _ in ACTIONS}

# XInput ids: B 0, X 1, Y 2, A 3, D-pad R/L/U/D 4-7, LB 8, LT 9, L3 10, RB 11, RT 12, R3 13, Start 14, Back 15
XINPUT = dict(bottom=3, right=0, left=1, top=2, l1=8, r1=11, l2=9, r2=12, l3=10, r3=13, start=14, select=15,
              move_x=32, move_y=-33, cam_x=35, cam_y=-36, up=6, down=7, menu_left=5, menu_right=4)
# DirectInput ids for PlayStation pads: Square 0, Cross 1, Circle 2, Triangle 3, L1 4, R1 5, L2 6, R2 7, Share 8,
# Options 9, L3 10, R3 11, PS 12, touchpad 13; sticks 32/33 and 34/37, D-pad hat 40/41
DINPUT = dict(bottom=1, right=2, left=0, top=3, l1=4, r1=5, l2=6, r2=7, l3=10, r3=11, start=9, select=8,
              move_x=32, move_y=33, cam_x=34, cam_y=37, up=41, down=41, menu_left=40, menu_right=40)
BUTTON_KEYS = ("bottom", "right", "left", "top", "l1", "r1", "l2", "r2", "l3", "r3", "start", "select")
BUTTON_LABELS = {
    "xbox":    ("A", "B", "X", "Y", "LB", "RB", "LT", "RT", "Left stick press", "Right stick press", "Start (Menu)", "Back (View)"),
    "ps4":     ("Cross", "Circle", "Square", "Triangle", "L1", "R1", "L2", "R2", "L3", "R3", "Options", "Share"),
    "ps5":     ("Cross", "Circle", "Square", "Triangle", "L1", "R1", "L2", "R2", "L3", "R3", "Options", "Create"),
    "switch":  ("B", "A", "Y", "X", "L", "R", "ZL", "ZR", "Left stick press", "Right stick press", "+ (Plus)", "- (Minus)"),
}
BUTTON_LABELS["switch2"] = BUTTON_LABELS["switch"]

DEFAULTS = {"managed": False, "enabled": True, "type": "xbox", "steam_input": False, "confirm_right": False,
            "vibration": True, "background": False, "invert_camera": False, "buttons": {}, "applied": False}


def uses_xinput(values):
    return values["type"] not in ("ps4", "ps5") or bool(values["steam_input"])


def layout(values):
    return XINPUT if uses_xinput(values) else DINPUT


def buttons(values):
    """[(id, name printed on the pad)] for the chosen controller, last (-1, "(nothing)")."""
    lay = layout(values)
    names = BUTTON_LABELS.get(values["type"], BUTTON_LABELS["xbox"])
    out = [(lay[k], n) for k, n in zip(BUTTON_KEYS, names)]
    if not uses_xinput(values):
        out += [(12, "PS button"), (13, "Touchpad press")]
    return out + [(NONE, "(nothing)")]


def default_buttons(values):
    """What each action gets before any change: the controller's usual layout."""
    lay = layout(values)
    confirm, cancel = (lay["right"], lay["bottom"]) if values["confirm_right"] else (lay["bottom"], lay["right"])
    return {7: confirm, 5: cancel, 6: lay["left"], 8: lay["top"], 0: lay["l1"], 1: lay["l2"], 3: lay["r2"],
            4: lay["l3"], 2: lay["r3"], 9: lay["select"], 12: lay["start"], 25: lay["r1"], 10: NONE, 11: NONE, 26: NONE}


def clean(values):
    out = dict(DEFAULTS)
    if isinstance(values, dict):
        for k in DEFAULTS:
            if k in values and k != "buttons":
                out[k] = values[k]
        raw = values.get("buttons") or {}
    else:
        raw = {}
    for k in ("managed", "enabled", "steam_input", "confirm_right", "vibration", "background", "invert_camera", "applied"):
        out[k] = bool(out[k])
    if out["type"] not in CONTROLLER_NAMES:
        out["type"] = "xbox"
    valid = {b for b, _ in buttons(out)}
    chosen = {}
    if isinstance(raw, dict):
        for slot, button in raw.items():
            try:
                slot, button = int(slot), int(button)
            except (TypeError, ValueError):
                continue
            if slot in ACTION_SLOTS and button in valid:
                chosen[slot] = button
    out["buttons"] = chosen
    return out


def pad_mode(values):
    """padmode000. XInput pads as retail writes them (sliders and hat switches off); DirectInput needs the hat for the D-pad."""
    if not values["enabled"]:
        return "0,0,0,0,0,0"
    x = uses_xinput(values)
    return ",".join(str(n) for n in (1, int(values["vibration"]), 0 if x else 1, 0 if x else 1, int(values["background"]), int(x)))


def pad_buttons(values):
    """padsin000: every slot, with the player's own button choices applied."""
    lay = layout(values)
    slots = [NONE] * SLOTS
    for slot, button in default_buttons(values).items():
        slots[slot] = button
    for slot, button in values["buttons"].items():
        slots[slot] = button
    cam_y = -lay["cam_y"] if values["invert_camera"] else lay["cam_y"]
    slots[13:17] = [lay["move_y"], lay["move_y"], lay["move_x"], lay["move_x"]]
    slots[17:21] = [cam_y, cam_y, lay["cam_x"], lay["cam_x"]]
    slots[21:25] = [lay["up"], lay["down"], lay["menu_left"], lay["menu_right"]]
    return ",".join(str(n) for n in slots)


def wanted(values):
    """{section: {key: value}} this setup puts in the boot file."""
    if values["managed"]:
        return {REGISTRY: {"padmode000": pad_mode(values), "padsin000": pad_buttons(values)},
                INPUT: {"gamepad.allowbackground": "1" if values["enabled"] and values["background"] else "0",
                        # no controller: skipping the controller search avoids a known micro-stutter (Ashita docs)
                        "gamepad.disableenumeration": "0" if values["enabled"] else "1"}}
    return {REGISTRY: {"padmode000": "-1", "padsin000": "-1"},
            INPUT: {"gamepad.allowbackground": "0", "gamepad.disableenumeration": "0"}}


# ---------- the boot file ----------
def _set_keys(lines, section, keys):
    """Sets key = value lines inside [section] (adds missing keys at its end, adds the section at the end of the file
    if it is missing). Every other line stays as it was."""
    keys = dict(keys)
    start = end = None
    for i, line in enumerate(lines):
        m = re.match(r"^\s*\[(.+?)\]", line)
        if m:
            if start is not None:
                end = i
                break
            if m.group(1).strip().lower() == section:
                start = i
    if start is None:
        if lines and lines[-1].strip():
            lines.append("")
        lines.append(f"[{section}]")
        lines.extend(f"{k} = {v}" for k, v in keys.items())
        return lines
    if end is None:
        end = len(lines)
    for i in range(start + 1, end):
        m = re.match(r"^(\s*)([^=;#\s][^=]*?)(\s*=\s*)(.*)$", lines[i])
        if m and m.group(2).strip().lower() in keys:
            key = m.group(2).strip().lower()
            lines[i] = f"{m.group(1)}{m.group(2)}{m.group(3)}{keys.pop(key)}"
    insert_at = end
    while insert_at > start + 1 and not lines[insert_at - 1].strip():
        insert_at -= 1
    for k, v in keys.items():
        lines.insert(insert_at, f"{k} = {v}")
        insert_at += 1
    return lines


def apply(ini_path, values):
    """Writes the controller setup into a boot file. Returns (changed, values to save): with managed off, the file is
    only touched when the launcher wrote it last time (then the game's own settings are put back with -1).
    The file is saved once as <file>.before-gamepad first."""
    values = clean(values)
    if not values["managed"] and not values["applied"]:
        return False, values
    with open(ini_path, "r", encoding="utf-8-sig", newline="") as f:
        text = f.read()
    newline = "\r\n" if "\r\n" in text else "\n"
    lines = text.splitlines()
    for section, keys in wanted(values).items():
        lines = _set_keys(lines, section, keys)
    new = newline.join(lines) + newline
    changed = new != text
    if changed:
        backup = ini_path + ".before-gamepad"
        if not os.path.exists(backup):
            shutil.copy2(ini_path, backup)
        with open(ini_path, "w", encoding="utf-8", newline="") as f:
            f.write(new)
    values["applied"] = values["managed"]
    return changed, values


def read_boot(ini_path):
    """(padmode000, padsin000) as the boot file says now, for showing; None for a missing file or key."""
    found = {}
    try:
        with open(ini_path, "r", encoding="utf-8-sig") as f:
            for line in f:
                m = re.match(r"^\s*(padmode000|padsin000)\s*=\s*(.*?)\s*$", line, re.I)
                if m:
                    found[m.group(1).lower()] = m.group(2)
    except OSError:
        pass
    return found.get("padmode000"), found.get("padsin000")


# ---------- gamepad.json ----------
def path(here):
    return os.path.join(here, "gamepad.json")


def load(here):
    try:
        with open(path(here), "r", encoding="utf-8-sig") as f:
            return clean(json.load(f))
    except (OSError, ValueError):
        return clean({})


def save(here, values):
    values = clean(values)
    values["buttons"] = {str(k): v for k, v in values["buttons"].items()}
    with open(path(here), "w", encoding="utf-8") as f:
        json.dump(values, f, indent=2)
