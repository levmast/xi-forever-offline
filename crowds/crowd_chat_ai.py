"""Ambient crowds: AI chatter helper. Keeps a pool of short, era-safe small-talk lines for the town bots, written by
your local Ollama model (the same one squad chat uses), in <server>/modules/custom/lua/crowds_chat_ai.lua.
The server reads that file every few minutes and mixes the lines with its own templates.

  python crowd_chat_ai.py            run (the launcher starts it with the servers when "AI chatter" is on)
  python crowd_chat_ai.py --once     make one batch and exit (a quick test)
  python crowd_chat_ai.py --status   show how many lines the pool has
  python crowd_chat_ai.py --stub     no Ollama: fill the pool with test lines (for checking the wiring)

It is gentle with your PC: one small request at a time, a pause between requests, nothing at all while squad chat
was busy in the last minute (so your squad's answers never wait on it), and it stops asking once the pool is full
(it then swaps a few old lines for new ones now and then). If Ollama is not running it just waits and tries later.
"""
import argparse
import json
import os
import random
import re
import sys
import time
import urllib.error
import urllib.request

try:  # the bot players' tells and party chat (crowds/bots/bots_chat_ai.py): answered between pool rounds, first
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "bots"))
    import bots_chat_ai
except Exception:  # (no bot players installed)
    bots_chat_ai = None

HERE = os.path.dirname(os.path.abspath(__file__))
KIT = os.path.dirname(HERE)

TARGET = {"say": 160, "pairs": 80, "outpost": 80, "react": 40, "shout": 60, "ls": 120}
BOTS_ONLY = ("ls",)         # with the crowds off (--bots-only): only the bots' linkshell chatter is kept filled
BATCH = 12
PAUSE = 40                 # seconds between requests while filling
FULL_PAUSE = 15 * 60       # once full: swap a few lines this often
SQUAD_QUIET = 60           # skip while squad chat has been busy this recently (seconds)
MAX_CHARS = 90

ERA_DENY = re.compile(
    r"abyssea|adoulin|wings of the goddess|\bwotg\b|campaign|voidwatch|\bgeas\b|\breives?\b|\bunity\b|ambuscade|odyssey|"
    r"\bsortie\b|escha|reisenjima|vagary|domain invasion|\bdelve\b|skirmish|\btrusts\b|trust (magic|npc|cipher)|"
    r"records of eminence|\broe\b|job points?|\bjp\b|master level|item level|\bilvl|\bi\.?lv|level 99|lv\.? ?99|\b99\b|"
    r"monstrosity|\bdnc\b|dancer|\bsch\b|scholar|\bgeo\b|geomancer|rune fencer|\brun\b(?= ?\d)|\bultima\b|mog garden|"
    r"\bsoa\b|rhapsod|gobbie|mystery box|"
    r"discord|twitch|youtube|reddit|google|internet|\bphone|http|www|\.com|ffxiv|final fantasy xiv|horizonxi|"
    r"\bai\b|chatgpt|language model|as an ai", re.I)
NAME_LIKE = re.compile(r"\b(Hurami|Kurami)\b")
# Words the model invents that no era player would type, or things that are not in this game at all.
# Keeping them out here means a pruned pool cannot quietly refill with the same nonsense.
JUNK = re.compile(
    r"\b(materia|colosseum|merijin|meracid|mpg|gmfg|gmba|w1n|tahat|kuholz|mtg|sps|vdh|kz|jn|ahu|mnd|t1|samson|"
    r"kageno|quetzalcoatl|obsidian)\b|si'jhin|\bnashmau port\b|\brabao flight\b|\bxp share\b|\btp pots?\b|"
    r"\bmerit book\b|\bblue pots\b|\bmoo shop\b|\bWT\b|/rune\b", re.I)

CATEGORY_PROMPTS = {
    "say": "short things a player says out loud while standing in a town, to nobody in particular or to friends nearby "
           "(waiting for a party, shopping, joking, complaining about lag, asking where something is)",
    "pairs": "two-line exchanges between two players standing next to each other in town: the first asks or remarks, the second "
             "answers briefly",
    "outpost": "short things players say while camping monsters near a field outpost (pulling, resting, asking for heals, "
               "joking about a monster, tired of waiting for a party)",
    "react": "short replies a player gives when a stranger walks up and targets them in town (friendly, curious, a bit busy)",
    "shout": "short /shout lines in a town that are not party or sales requests: asking where to find a monster or NPC, "
             "looking for a crafter, asking for directions, a friendly hello to everyone",
    "ls": "short things a player types in their linkshell chat to the friends in it, between other things: small talk, "
          "plans for later, a joke, asking for advice, grumbling about inventory space or travel time. Never claim a "
          "specific drop, level up, win or price, and never name anyone",
}

# Example lines from the dialogue packs (C:\FFXISOLO\dialogue\dialogue_lines.json): the model writes new lines in their
# style. Without the file the prompts work as before.
def load_seeds():
    path = os.path.join(KIT, "dialogue", "dialogue_lines.json")
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return {}
    seeds = {"ls": [], "pairs": [], "say": [], "outpost": [], "react": [], "shout": []}
    for line in data.get("lines", []):
        tags = line.get("tags", [])
        if "ls" in tags and "{" not in line.get("casual", ""):
            seeds["ls"].append(line["casual"])
        if "pair" in tags and line.get("answer"):
            seeds["pairs"].append(line["casual"] + " / " + line["answer"])
    # the crowd section (town chatter): same categories as this pool
    crowd = data.get("crowd") or {}
    to_pool = {"say_town": "say", "outpost": "outpost", "react": "react", "shout_misc": "shout"}
    for line in crowd.get("lines", []):
        cat = to_pool.get(line.get("cat"))
        if cat and "{" not in line.get("casual", ""):
            seeds[cat].append(line["casual"])
    for pair in crowd.get("pairs", []):
        if "{" not in pair.get("a", "") + pair.get("b", ""):
            seeds["pairs"].append(pair["a"] + " / " + pair["b"])
    return {k: v for k, v in seeds.items() if v}


SEEDS = load_seeds()

SYSTEM = (
    "You write lines of in-game chat for background players in Final Fantasy XI as it was in 2006-2007, the level 75 era: the "
    "original game, Rise of the Zilart, Chains of Promathia and Treasures of Aht Urhgan ONLY. Never mention anything newer "
    "(no Wings of the Goddess, Abyssea, Adoulin, Trusts, level 99, job points). Jobs that exist: WAR MNK WHM BLM RDM THF PLD DRK "
    "BST BRD RNG SAM NIN DRG SMN BLU COR PUP. Real places: San d'Oria, Bastok, Windurst, Jeuno, Selbina, Mhaura, Kazham, Norg, "
    "Rabao, Tavnazian Safehold, Aht Urhgan Whitegate, Al Zahbi, Nashmau, Valkurm Dunes, Qufim Island, Jugner Forest, Crawlers' "
    "Nest, Garlaige Citadel, Kuftal Tunnel, Boyahda Tree, Bhaflau Thickets, Wajaom Woodlands, Mount Zhayolm. "
    "Write like real players typing quickly: casual, short, lowercase is fine, common MMO shorthand (lol, brb, ty, np, gz, k, "
    "afk, pt, exp, TP, MP, pull, inc). Out of character, not role-play. No names of people. No quotes around lines. "
    "Plain ASCII only. Each line at most 80 characters."
)


def log(msg):
    print(time.strftime("%H:%M:%S ") + msg, flush=True)


def server_dir():
    try:
        with open(os.path.join(KIT, "config.json"), encoding="utf-8-sig") as f:
            return json.load(f).get("server_dir") or r"C:\ffxi-local\server"
    except (OSError, ValueError):
        return r"C:\ffxi-local\server"


# models that think before they answer (their "think" switch is turned off: chat needs the answer, not the reasoning)
THINKING_MODELS = ("gemma4", "qwen3", "deepseek-r1", "gpt-oss", "magistral")
_installed = {"at": 0, "names": None}


def installed_models(url):
    """The models Ollama has pulled (asked at most every 5 minutes), or None when Ollama does not answer."""
    if time.time() - _installed["at"] < 300 and _installed["names"] is not None:
        return _installed["names"]
    try:
        with urllib.request.urlopen(url.rstrip("/") + "/api/tags", timeout=3) as resp:
            names = [m.get("name", "") for m in json.loads(resp.read().decode("utf-8")).get("models", [])]
    except Exception:
        names = None
    _installed.update(at=time.time(), names=names)
    return names


def pick_model(wanted, fallback, url):
    """The wanted model if it is pulled, else the fallback (so a model you have not downloaded yet never breaks chat)."""
    names = installed_models(url)
    if not names:
        return wanted
    def has(m):
        return m in names or (":" not in m and m + ":latest" in names)
    if has(wanted) or not fallback or not has(fallback):
        return wanted
    return fallback


def model_extra(model):
    """Extra request fields for a model: thinking models answer straight away."""
    return {"think": False} if str(model).split(":")[0].lower().startswith(THINKING_MODELS) else {}


def model_options(model, base):
    """Sampling for a model family (Gemma 4 is made for temperature 1.0, top_p 0.95, top_k 64)."""
    opts = dict(base)
    if str(model).lower().startswith("gemma"):
        opts.update(temperature=max(opts.get("temperature", 1.0), 1.0), top_p=0.95, top_k=64)
    return opts


def squad_config():
    """Model and address from squad chat's own settings, so both use the model you already have.
    "model" is the one to use; "fallback_model" (mistral-nemo) is used until the new one is pulled."""
    cfg = {"model": "gemma4:12b", "ollama_url": "http://127.0.0.1:11434", "fallback_model": "mistral-nemo:latest"}
    try:
        with open(os.path.join(KIT, "squad-chat", "config.json"), encoding="utf-8-sig") as f:
            sc = json.load(f)
        cfg["model"] = sc.get("model", cfg["model"])
        cfg["ollama_url"] = sc.get("ollama_url", cfg["ollama_url"])
        cfg["fallback_model"] = sc.get("fallback_model", cfg["fallback_model"])
    except (OSError, ValueError):
        pass
    cfg["model"] = pick_model(cfg["model"], cfg["fallback_model"], cfg["ollama_url"])
    return cfg


def squad_busy():
    """True if squad chat had party-chat traffic in the last minute (its bridge file changed)."""
    for name in ("in.txt", "out.txt"):
        p = os.path.join(KIT, "squad-chat", name)
        try:
            if time.time() - os.path.getmtime(p) < SQUAD_QUIET:
                return True
        except OSError:
            pass
    return False


def clean_line(text):
    if not isinstance(text, str):
        return None
    text = text.strip().strip('"').strip("'").strip()
    text = re.sub(r"\s+", " ", text)
    text = text.replace("\u2019", "'").replace("\u2018", "'").replace("\u201c", "").replace("\u201d", "").replace("\u2026", "...")
    text = text.replace("\u2014", "-").replace("\u2013", "-")
    if not text or len(text) > MAX_CHARS:
        return None
    if any(ord(ch) < 32 or ord(ch) > 126 for ch in text):
        return None
    if ("{" in text or "}" in text or "\\" in text or ERA_DENY.search(text) or NAME_LIKE.search(text)
            or JUNK.search(text)):
        return None
    if text.lower().startswith(("sure", "here are", "okay", "certainly")):
        return None
    return text


def parse(category, content):
    """Model JSON -> list of lines (or [a, b] pairs). Anything unsafe or malformed is dropped."""
    try:
        data = json.loads(content)
    except (TypeError, ValueError):
        return []
    items = data.get("lines") if isinstance(data, dict) else data
    if not isinstance(items, list):
        return []
    out = []
    for item in items:
        if category == "pairs":
            if isinstance(item, dict):
                a, b = clean_line(item.get("a")), clean_line(item.get("b"))
            elif isinstance(item, list) and len(item) == 2:
                a, b = clean_line(item[0]), clean_line(item[1])
            else:
                continue
            if a and b:
                out.append([a, b])
        else:
            if isinstance(item, dict):
                item = item.get("text") or item.get("line")
            line = clean_line(item)
            if line:
                out.append(line)
    return out


def hood(source, model, messages, reply, seconds):
    """(Sunie, 2026-11-22) "Peek under the AI hood". While the switch file ai-hood.on is in the kit folder, every
    prompt goes to logs/ai-hood.log in full, with the model's reply. No such file (everyone else): nothing happens."""
    try:
        import os
        kit = KIT
        if not os.path.exists(os.path.join(kit, "ai-hood.on")):
            return
        path = os.path.join(kit, "logs", "ai-hood.log")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        if os.path.exists(path) and os.path.getsize(path) > 4_000_000:      # one older file is kept
            os.replace(path, path + ".1")
        parts = [f"===== {time.strftime('%H:%M:%S')}  {source}  |  model {model}  |  {seconds:.1f}s ====="]
        for message in messages:
            parts.append(f"--- {message.get('role', '?')} ---")
            parts.append(str(message.get("content", "")).rstrip())
        parts.append("--- reply ---")
        parts.append(str(reply if reply is not None else "(no reply)").rstrip())
        with open(path, "a", encoding="utf-8") as handle:
            handle.write("\n".join(parts) + "\n\n")
    except Exception:
        pass


def ask_model(cfg, category, avoid):
    shape = ('{"lines": [{"a": "...", "b": "..."}, ...]}' if category == "pairs" else '{"lines": ["...", "..."]}')
    sample = "; ".join(random.sample(avoid, min(5, len(avoid)))) if avoid else ""
    seeds = SEEDS.get(category) or []
    style = "; ".join(random.sample(seeds, min(6, len(seeds)))) if seeds else ""
    user = (f"Write {BATCH} different {CATEGORY_PROMPTS[category]}. Answer with JSON only, shaped like {shape}."
            + (f" Lines in this spirit (examples only: write new ones, never copy them): {style}." if style else "")
            + (f" Do not repeat these: {sample}" if sample else ""))
    payload = {
        "model": cfg["model"], "stream": False, "format": "json", "keep_alive": "30m",
        "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}],
        "options": model_options(cfg["model"], {"temperature": 0.95, "top_p": 0.9, "num_ctx": 2048, "num_predict": 700}),
    }
    payload.update(model_extra(cfg["model"]))
    req = urllib.request.Request(cfg["ollama_url"].rstrip("/") + "/api/chat", data=json.dumps(payload).encode("utf-8"),
                                 headers={"Content-Type": "application/json"}, method="POST")
    started = time.time()
    with urllib.request.urlopen(req, timeout=180) as resp:
        body = json.loads(resp.read().decode("utf-8"))
    content = body.get("message", {}).get("content")
    log(f"ollama {category}: {time.time() - started:.1f}s")
    hood(f"town crowd lines ({category})", cfg["model"], payload["messages"], content, time.time() - started)
    return content


def lua_str(s):
    return "'" + s.replace("\\", "\\\\").replace("'", "\\'") + "'"


def pool_path(server):
    return os.path.join(server, "modules", "custom", "lua", "crowds_chat_ai.lua")


def json_path(server):
    return os.path.join(server, "modules", "custom", "lua", "crowds_chat_ai.json")


def load_pool(server):
    try:
        with open(json_path(server), encoding="utf-8") as f:
            pool = json.load(f)
    except (OSError, ValueError):
        pool = {}
    for k in TARGET:
        pool.setdefault(k, [])
    return pool


def save_pool(server, pool):
    """JSON for this helper, Lua for the server. Both written to a temp file first, then swapped in."""
    lines = ["-- Written by C:\\FFXISOLO\\crowds\\crowd_chat_ai.py (AI small talk for the crowds). Safe to delete: it is refilled.",
             "return {"]
    for k in TARGET:
        lines.append("    %s = {" % k)
        for item in pool[k]:
            if k == "pairs":
                lines.append("        { %s, %s }," % (lua_str(item[0]), lua_str(item[1])))
            else:
                lines.append("        %s," % lua_str(item))
        lines.append("    },")
    lines.append("}")
    for path, text in ((pool_path(server), "\n".join(lines) + "\n"), (json_path(server), json.dumps(pool, indent=1))):
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        for attempt in range(5):   # the server may be reading the file this very moment (Windows locks it)
            try:
                os.replace(tmp, path)
                break
            except PermissionError:
                if attempt == 4:
                    raise
                time.sleep(0.5)


def add_lines(pool, category, new, swap=False):
    key = (lambda x: (x[0] + "|" + x[1]).lower()) if category == "pairs" else (lambda x: x.lower())
    have = {key(x) for x in pool[category]}
    added = 0
    for item in new:
        if key(item) in have:
            continue
        if len(pool[category]) >= TARGET[category]:
            if not swap:
                break
            pool[category].pop(random.randrange(len(pool[category])))
        pool[category].append(item)
        have.add(key(item))
        added += 1
    return added


STUB = {
    "say": ["anyone know a good spot for skillups?", "brb, getting food", "this zone is so laggy", "need gil so bad lol"],
    "pairs": [["you ready?", "one sec"], ["lfp?", "ya, still looking"]],
    "outpost": ["pulling", "resting, low mp", "one more"],
    "react": ["hi?", "need something?"],
    "shout": ["anyone know where to buy Echo Drops?", "hello everyone o/"],
    "ls": ["anyone up for something later?", "inventory full again lol", "brb food"],
}


def one_round(cfg, server, pool, stub=False, cats=None):
    cats = list(cats or TARGET)
    need = {k: max(0, TARGET[k] - len(pool[k])) for k in cats}
    full = sum(need.values()) == 0
    if full:
        category = random.choice(cats)
    else:
        # the emptier a category, the likelier it is asked for (so one that keeps failing never blocks the others)
        roll = random.random() * sum(need.values())
        for category in cats:
            roll -= need[category]
            if roll <= 0 and need[category] > 0:
                break
    if stub:
        new = [x for x in STUB[category]]
    else:
        avoid = [x if isinstance(x, str) else x[0] for x in pool[category]]
        content = ask_model(cfg, category, avoid)
        new = parse(category, content)
    added = add_lines(pool, category, new[:3] if full else new, swap=full)
    save_pool(server, pool)
    log(f"{category}: +{added} (pool: " + ", ".join(f"{k} {len(pool[k])}/{TARGET[k]}" for k in TARGET) + ")")
    return full


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--stub", action="store_true")
    ap.add_argument("--server", default=None)
    ap.add_argument("--bots-only", action="store_true", help="only answer the bot players (the crowds are off)")
    args = ap.parse_args()
    server = args.server or server_dir()
    pool = load_pool(server)
    if args.status:
        print("AI chatter pool (" + pool_path(server) + "):")
        for k in TARGET:
            print(f"  {k:<8} {len(pool[k])}/{TARGET[k]}")
        return 0
    if os.name == "nt":  # a background helper: lower priority than the game and the servers
        try:
            import ctypes
            ctypes.windll.kernel32.SetPriorityClass(ctypes.windll.kernel32.GetCurrentProcess(), 0x4000)  # BELOW_NORMAL
        except Exception:
            pass
    cfg = squad_config()
    log(f"crowd chat AI: model {cfg['model']} at {cfg['ollama_url']}" + (" (stub)" if args.stub else ""))
    while True:
        wait = PAUSE
        cfg = squad_config()  # (picks up a model pulled meanwhile, or a changed config.json)
        try:
            if args.bots_only and not args.stub and squad_busy():
                log("squad chat is busy - waiting")
                wait = 30
            elif args.bots_only:
                # no crowds: only the bots' linkshell chatter pool (and their tells, below)
                full = one_round(cfg, server, pool, stub=args.stub, cats=BOTS_ONLY)
                wait = FULL_PAUSE if full else PAUSE * 2
            elif not args.stub and squad_busy():
                log("squad chat is busy - waiting")
                wait = 30
            else:
                full = one_round(cfg, server, pool, stub=args.stub)
                wait = FULL_PAUSE if full else PAUSE
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            log(f"Ollama not reachable ({exc}) - trying again in 2 minutes")
            wait = 120
        except ValueError as exc:
            log(f"bad answer from the model ({exc})")
        if args.once:
            return 0
        # wait for the next pool round, answering the bots' tells as they come (about every second)
        until = time.time() + wait
        while time.time() < until:
            if bots_chat_ai is not None:
                try:
                    bots_chat_ai.serve(cfg, server, stub=args.stub)
                except Exception as exc:
                    log(f"bot chat: {exc}")
            time.sleep(1)


if __name__ == "__main__":
    sys.exit(main())
