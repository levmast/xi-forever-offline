"""The job-rules editor's brains (no screen code here, so it can be tested on its own).

A squad mate's behaviour is a list of rules per job (see squad.lua, "Editable job rules"). The built-in rules, written out as data, are in
squad-data/squad_rules_default.json. What you change is kept in squad_rules_user.json, and from it this module writes
modules/custom/lua/squad_rules_data.lua, which the server reads when it starts.

A rule is a dict like
  {"on": true, "target": "PARTY", "cond": ["HPP_LT", 25], "cond2": ["MPP_GTE", 10], "action": ["family", "CURE"], "retry": 60, "level": 5}
"""
import copy
import json
import os
import re

JOB_ORDER = ["WAR", "MNK", "WHM", "BLM", "RDM", "THF", "PLD", "DRK", "BST", "BRD", "RNG", "SAM", "NIN", "DRG", "SMN",
             "BLU", "COR", "PUP", "DNC", "SCH"]   # (BLU/COR/PUP: the Aht Urhgan jobs, 2026-11-17; DNC/SCH: Wings of the Goddess, 2026-11-22)
PARTS = ["ja", "magic"]
PART_LABELS = {"ja": "Job abilities", "magic": "Spells and ranged attacks"}
MARKER = "-- Written by the XI: Forever Offline launcher (Squad tab > Edit job rules). It is rewritten when you save there."

TARGETS = ["SELF", "PARTY", "MASTER", "TARGET", "TRIGGER_SELF_ACTION_TARGET"]
TARGET_LABELS = {"SELF": "itself", "PARTY": "a party member", "MASTER": "you", "TARGET": "the enemy",
                 "TRIGGER_SELF_ACTION_TARGET": "its own enemy (Drain)"}

# name: (how it reads, what the argument is)   argument: None, "number", "effect", "flag", "ecosystem"
CONDITIONS = {
    "ALWAYS": ("always", None),
    "HPP_LT": ("HP below {}%", "number"),
    "MPP_LT": ("MP below {}%", "number"),
    "MPP_GTE": ("MP at least {}%", "number"),
    "TP_LT": ("TP below {}", "number"),
    "STATUS": ("has {}", "effect"),
    "NOT_STATUS": ("is missing {}", "effect"),
    "STATUS_FLAG": ("has an effect flagged {}", "flag"),
    "HAS_TOP_ENMITY": ("has the enemy's attention", None),
    "NOT_HAS_TOP_ENMITY": ("does not have the enemy's attention", None),
    "IS_ECOSYSTEM": ("the enemy is a {}", "ecosystem"),
    "MB_AVAILABLE": ("a magic burst is available", None),
    "NOT_SC_AVAILABLE": ("there is no skillchain to burst", None),
}
ACTIONS = {
    "family": "the best learned spell of a family",
    "spell": "one specific spell",
    "ja": "a job ability",
    "ranged": "a ranged attack",
    "nuke": "the strongest nuke it knows",
    "burst": "a magic burst",
    "waltz": "the best Curing Waltz (DNC)",
    "samba": "the best samba (DNC)",
    "storm": "the storm of the day (SCH)",
    "helix": "the helix of the day (SCH)",
}
NAME = re.compile(r"^[A-Z][A-Z0-9_]*$")
RULE_FIELDS = ["on", "target", "cond", "cond2", "action", "retry", "level"]


# ---------------------------------------------------------------- names and text
def normalize_name(text):
    """'Third Eye' -> 'THIRD_EYE'"""
    return re.sub(r"[^A-Z0-9_]", "", str(text or "").strip().upper().replace(" ", "_").replace("-", "_"))


def pretty_name(name):
    return str(name).replace("_", " ").title()


def _arg_text(arg):
    if isinstance(arg, dict):
        if "flag" in arg:
            return pretty_name(arg["flag"])
        if "ecosystem" in arg:
            return pretty_name(arg["ecosystem"])
        if "main" in arg or "sub" in arg:
            return f"{arg.get('main', 0)} ({arg.get('sub', 0)} as a sub job)"
    if isinstance(arg, str):
        return pretty_name(arg)
    return str(arg)


def condition_text(cond):
    if not cond:
        return ""
    template, kind = CONDITIONS.get(cond[0], (cond[0], None))
    return template.format(_arg_text(cond[1])) if kind else template


def action_text(action):
    kind = action[0] if action else ""
    if kind == "family":
        return f"{pretty_name(action[1])} (best learned)"
    if kind in ("spell", "ja"):
        return pretty_name(action[1])
    return {"ranged": "Ranged attack", "nuke": "Strongest nuke", "burst": "Magic burst", "waltz": "Best Curing Waltz",
            "samba": "Best samba", "storm": "Storm of the day", "helix": "Helix of the day"}.get(kind, kind)


def rule_columns(rule):
    """The words shown in each column of the rule list."""
    return {
        "on": "on" if rule.get("on", True) else "off",
        "target": TARGET_LABELS.get(rule.get("target"), rule.get("target", "")),
        "when": condition_text(rule.get("cond")),
        "and": condition_text(rule.get("cond2")) if rule.get("cond2") else "",
        "do": action_text(rule.get("action")),
        "retry": str(rule["retry"]) if rule.get("retry") else "",
        "level": str(rule["level"]) if rule.get("level") else "",
    }


# ---------------------------------------------------------------- building and checking a rule
def _parse_condition(name, text):
    """(condition, problem) from the choice and the typed argument."""
    if name not in CONDITIONS:
        return None, f"unknown condition {name!r}"
    kind = CONDITIONS[name][1]
    text = str(text or "").strip()
    if kind is None:
        return [name, 0], None
    if kind == "number":
        try:
            value = float(text)
        except ValueError:
            return None, f"{name}: the number must be a number (you typed {text!r})"
        if value < 0 or value > 3000:
            return None, f"{name}: the number must be between 0 and 3000"
        return [name, int(value) if value == int(value) else value], None
    cleaned = normalize_name(text)
    if not NAME.match(cleaned):
        return None, f"{name}: type a name like HASTE (letters, digits and underscores)"
    if kind == "effect":
        return [name, cleaned], None
    return [name, {kind: cleaned}], None


def build_rule(on, target, cond_name, cond_text, cond2_name, cond2_text, action_kind, action_name, retry_text, level_text):
    """Turns what the dialog holds into a rule. Returns (rule, problems); rule is None when there is a problem."""
    problems = []
    if target not in TARGETS:
        problems.append(f"choose who it is for ({', '.join(TARGETS)})")
    cond, problem = _parse_condition(cond_name, cond_text)
    if problem:
        problems.append(problem)
    cond2 = None
    if cond2_name and cond2_name != "(none)":
        cond2, problem = _parse_condition(cond2_name, cond2_text)
        if problem:
            problems.append("and: " + problem)
    if action_kind not in ACTIONS:
        problems.append("choose what it does")
        action = None
    elif action_kind in ("family", "spell", "ja"):
        cleaned = normalize_name(action_name)
        if not NAME.match(cleaned):
            problems.append("type the name of the spell, family or ability (like CURE or PROVOKE)")
            action = None
        else:
            action = [action_kind, cleaned]
    else:
        action = [action_kind]
    retry = level = None
    for label, text in (("retry", retry_text), ("level", level_text)):
        text = str(text or "").strip()
        if not text:
            continue
        try:
            number = int(float(text))
        except ValueError:
            problems.append(f"{label} must be a whole number")
            continue
        if label == "retry" and not 0 <= number <= 3600:
            problems.append("retry must be between 0 and 3600 seconds")
        elif label == "level" and not 0 <= number <= 75:
            problems.append("level must be between 0 and 75")
        elif number > 0:
            retry, level = (number, level) if label == "retry" else (retry, number)
    if problems:
        return None, problems
    rule = {"on": bool(on), "target": target, "cond": cond}
    if cond2:
        rule["cond2"] = cond2
    rule["action"] = action
    if retry:
        rule["retry"] = retry
    if level:
        rule["level"] = level
    return rule, []


def validate_rule(rule):
    """Problems with a rule as stored (used before saving, so a bad file never reaches the server)."""
    if not isinstance(rule, dict):
        return ["not a rule"]
    problems = []
    if rule.get("target") not in TARGETS:
        problems.append(f"unknown target {rule.get('target')!r}")
    for key in ("cond", "cond2"):
        cond = rule.get(key)
        if cond is None and key == "cond2":
            continue
        if not (isinstance(cond, list) and len(cond) == 2 and cond[0] in CONDITIONS):
            problems.append(f"{key}: not a known condition")
    action = rule.get("action")
    if not (isinstance(action, list) and action and action[0] in ACTIONS):
        problems.append("action: not a known action")
    elif action[0] in ("family", "spell", "ja") and not (len(action) == 2 and isinstance(action[1], str) and NAME.match(action[1])):
        problems.append("action: the name is missing or not valid")
    for key, top in (("retry", 3600), ("level", 75)):
        if key in rule and not (isinstance(rule[key], (int, float)) and 0 <= rule[key] <= top):
            problems.append(f"{key}: out of range")
    return problems


def condition_to_fields(cond):
    """(name, argument text) to fill the dialog."""
    if not cond:
        return "(none)", ""
    name, arg = cond[0], cond[1]
    kind = CONDITIONS.get(name, (None, None))[1]
    if kind is None:
        return name, ""
    if isinstance(arg, dict):
        if "flag" in arg:
            return name, arg["flag"]
        if "ecosystem" in arg:
            return name, arg["ecosystem"]
        return name, str(arg.get("main", 0))
    return name, str(arg)


def keep_original_conditions(original, rule, fields):
    """A condition like HP-at-least { main = 0, sub = 60 } has two numbers but the dialog shows one. If you did not change that condition,
    the original (both numbers) is kept. fields: {"cond": (name, text), "cond2": (name, text)} as the dialog held them."""
    if not original:
        return rule
    for key in ("cond", "cond2"):
        before = original.get(key)
        if before and isinstance(before[1], dict) and ("main" in before[1] or "sub" in before[1]) and fields.get(key) == condition_to_fields(before):
            rule[key] = copy.deepcopy(before)
    return rule


# ---------------------------------------------------------------- the rule sets
def known_names(defaults):
    """Names the built-in rules use, for the dialog's lists. (The server decides what is really valid; unknown names are skipped and logged.)"""
    names = {"effect": set(), "flag": set(), "ecosystem": set(), "family": set(), "spell": set(), "ja": set()}
    for job in (defaults or {}).get("jobs", {}).values():
        for rules in job.values():
            if not isinstance(rules, list):
                continue
            for rule in rules:
                for key in ("cond", "cond2"):
                    cond = rule.get(key)
                    if cond and isinstance(cond[1], str):
                        names["effect"].add(cond[1])
                    elif cond and isinstance(cond[1], dict):
                        for kind in ("flag", "ecosystem"):
                            if kind in cond[1]:
                                names[kind].add(cond[1][kind])
                action = rule.get("action") or []
                if len(action) == 2 and action[0] in ("family", "spell", "ja"):
                    names[action[0]].add(action[1])
    return {kind: sorted(values) for kind, values in names.items()}


def load_json(path, default=None):
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else default
    except (OSError, ValueError):
        return default


class RuleSet:
    """The built-in rules plus the ones you edited. Only the parts of a job you edited are saved; everything else stays built in."""

    def __init__(self, defaults, user=None):
        self.defaults = (defaults or {}).get("jobs", {})
        self.user = copy.deepcopy((user or {}).get("jobs", {})) if isinstance((user or {}).get("jobs", {}), dict) else {}

    def has_part(self, job, part):
        """Whether the job has anything for this part, built in or edited."""
        return part in self.user.get(job, {}) or part in self.defaults.get(job, {})

    def is_custom(self, job):
        return job in self.user

    def part_is_custom(self, job, part):
        return part in self.user.get(job, {})

    def enabled(self, job):
        return job in self.user and self.user[job].get("enabled", True) is not False

    def rules(self, job, part):
        if part in self.user.get(job, {}):
            return copy.deepcopy(self.user[job][part])
        return copy.deepcopy(self.defaults.get(job, {}).get(part, []))

    def set_rules(self, job, part, rules):
        entry = self.user.setdefault(job, {"enabled": True})
        entry[part] = copy.deepcopy(rules)

    def set_enabled(self, job, flag):
        if job in self.user:
            self.user[job]["enabled"] = bool(flag)

    def reset(self, job):
        self.user.pop(job, None)

    def reset_part(self, job, part):
        if job in self.user:
            self.user[job].pop(part, None)
            if not any(p in self.user[job] for p in PARTS):
                del self.user[job]

    def problems(self):
        out = []
        for job, entry in self.user.items():
            if job not in JOB_ORDER:
                out.append(f"{job}: not a job")
            for part in PARTS:
                for i, rule in enumerate(entry.get(part, []), 1):
                    for problem in validate_rule(rule):
                        out.append(f"{job} {PART_LABELS[part].lower()} rule {i}: {problem}")
        return out

    def to_data(self):
        jobs = {}
        for job in JOB_ORDER:
            if job in self.user and any(part in self.user[job] for part in PARTS):
                jobs[job] = copy.deepcopy(self.user[job])
        return {"version": 1, "jobs": jobs}


# ---------------------------------------------------------------- list helpers
def move_rule(rules, index, delta):
    """Moves a rule up (-1) or down (+1). Returns the rule's new index."""
    target = index + delta
    if not (0 <= index < len(rules) and 0 <= target < len(rules)):
        return index
    rules[index], rules[target] = rules[target], rules[index]
    return target


# ---------------------------------------------------------------- writing the Lua data file the server reads
_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _lua_string(value):
    out = ["'"]
    for ch in value:
        if ch in ("\\", "'"):
            out.append("\\" + ch)
        elif ord(ch) < 32:
            out.append("\\%d" % ord(ch))
        else:
            out.append(ch)
    out.append("'")
    return "".join(out)


def _is_array(value):
    return isinstance(value, list)


def _key_order(key):
    return (RULE_FIELDS.index(key), "") if key in RULE_FIELDS else (len(RULE_FIELDS), key)


def lua_value(value, indent=""):
    inner = indent + "    "
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return repr(int(value)) if value == int(value) else repr(value)
    if isinstance(value, str):
        return _lua_string(value)
    if isinstance(value, list):
        if not value:
            return "{}"
        parts = [lua_value(v, inner) for v in value]
        flat = "{ " + ", ".join(parts) + " }"
        if len(flat) <= 100 and "\n" not in flat:
            return flat
        return "{\n" + inner + (",\n" + inner).join(parts) + ",\n" + indent + "}"
    if isinstance(value, dict):
        items = [(k, v) for k, v in value.items() if v is not None]
        for key, _ in items:
            if not _IDENT.match(str(key)):
                raise ValueError(f"{key!r} cannot be a Lua name")
        items.sort(key=lambda kv: _key_order(kv[0]))
        parts = [f"{k} = {lua_value(v, inner)}" for k, v in items]
        flat = "{ " + ", ".join(parts) + " }"
        if len(flat) <= 100 and "\n" not in flat:
            return flat
        return "{\n" + inner + (",\n" + inner).join(parts) + ",\n" + indent + "}"
    raise ValueError(f"cannot write {value!r} as Lua")


def to_lua(data, marker=MARKER):
    return marker + "\nreturn " + lua_value(data) + "\n"


def write_lua(path, data, marker=MARKER):
    """Writes the server's data file. A file that was not written by this launcher is kept once as .before-launcher."""
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8-sig", errors="replace") as f:
            first = f.readline()
        backup = path + ".before-launcher"
        if not first.startswith(marker[:40]) and not os.path.exists(backup):
            with open(path, "rb") as src, open(backup, "wb") as dst:
                dst.write(src.read())
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(to_lua(data, marker))


# ---------------------------------------------------------------- what the editor window does (kept free of screen code)
class EditorState:
    """One job and one part (abilities or spells) being edited. Every change goes straight into the rule set; Save writes the files."""

    def __init__(self, ruleset, user_path, lua_path, job="WHM", part="magic"):
        self.rs = ruleset
        self.user_path = user_path
        self.lua_path = lua_path
        self.job, self.part = job, part
        self.dirty = False
        self.rules = self.rs.rules(job, part)

    def pick(self, job, part):
        self.job, self.part = job, part
        self.rules = self.rs.rules(job, part)

    def rows(self):
        return [rule_columns(rule) for rule in self.rules]

    def status(self):
        if self.rs.part_is_custom(self.job, self.part):
            return "edited" + ("" if self.rs.enabled(self.job) else " (switched off: the built-in rules are used)")
        return "built in"

    def _changed(self):
        self.rs.set_rules(self.job, self.part, self.rules)
        self.dirty = True

    def add(self, rule, index=None):
        self.rules.insert(len(self.rules) if index is None else index, rule)
        self._changed()

    def update(self, index, rule):
        self.rules[index] = rule
        self._changed()

    def delete(self, index):
        del self.rules[index]
        self._changed()

    def move(self, index, delta):
        new = move_rule(self.rules, index, delta)
        if new != index:
            self._changed()
        return new

    def toggle(self, index):
        self.rules[index] = dict(self.rules[index], on=not self.rules[index].get("on", True))
        self._changed()

    def set_enabled(self, flag):
        if self.rs.is_custom(self.job):
            self.rs.set_enabled(self.job, flag)
            self.dirty = True

    def reset_list(self):
        self.rs.reset_part(self.job, self.part)
        self.rules = self.rs.rules(self.job, self.part)
        self.dirty = True

    def reset_job(self):
        self.rs.reset(self.job)
        self.rules = self.rs.rules(self.job, self.part)
        self.dirty = True

    def save(self):
        """Writes squad_rules_user.json (what you edited) and the Lua file the server reads. Returns a message, or raises ValueError with the problems."""
        problems = self.rs.problems()
        if problems:
            raise ValueError("Not saved. Fix these first:\n" + "\n".join(problems[:8]))
        data = self.rs.to_data()
        os.makedirs(os.path.dirname(self.user_path), exist_ok=True)
        with open(self.user_path, "w", encoding="utf-8", newline="\n") as f:
            json.dump(data, f, indent=2)
        write_lua(self.lua_path, data)
        self.dirty = False
        count = len(data["jobs"])
        return (f"Saved. {count} job{'s' if count != 1 else ''} use your rules; the others stay built in. "
                "The server reads the rules when it starts, so press PLAY (or restart the servers), then call your mates.")
