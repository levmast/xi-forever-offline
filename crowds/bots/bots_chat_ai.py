"""Bot players: AI answers for /tells and party chat (used by crowds/crowd_chat_ai.py, which the launcher starts).

The server (bots_chat.lua) appends one JSON request per line to <server>/modules/custom/lua/bots_chat_in.txt:
  {"id": 7, "t": 1793990000, "bot": "Aldric", "to": "Hurami", "kind": "tell", "text": "hi!", "info": {...facts...}}
This answers it with your local Ollama model (squad chat's model) and appends "<id><TAB><answer>" to bots_chat_out.txt.
Each bot keeps a short memory of what it said with each player in crowds/bots/chat_memory/<Bot>.json.

  python bots_chat_ai.py --test "Aldric" "what are you up to?"    one answer, printed (no server needed)
"""
import json
import os
import random
import re
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
KIT = os.path.dirname(os.path.dirname(HERE))
MEMORY = os.path.join(HERE, "chat_memory")
MAX_AGE = 60          # seconds: older requests (the server waited already, or a new run) are skipped
MAX_CHARS = 115       # one chat line (the game shows about this much)
MAX_LINES = 2         # a longer answer goes out as two quick lines, the way players type
KEEP = 16             # exchanges remembered per player
DIARY = 10            # things that happened to it lately, kept in its memory file
ABOUT_EVERY = 6       # new exchanges with someone before it sums up what it knows about them
THINKING_MODELS = ("gemma4", "qwen3", "deepseek-r1", "gpt-oss", "magistral")

ERA_DENY = re.compile(r"\b(trusts?|abyssea|adoulin|wings of the goddess|wotg|seekers|level 99|lvl 99|job points?|unity|"
                      r"geomancer|rune fencer|ambuscade|omen|reives?|ai\b|chatgpt|language model|as an ai)", re.I)

SYSTEM = (
    "You are {name}, a real person playing Final Fantasy XI in 2006-2007 (the level 75 era: original game, Rise of the Zilart, "
    "Chains of Promathia, Treasures of Aht Urhgan only; nothing newer exists). You are chatting in game with another player, "
    "typing at your keyboard between fights. Talk like a real person in an MMO, not like a helpful assistant:\n"
    "- react to what they actually said; joke, tease, complain, brag or get excited when it fits; you have opinions "
    "(jobs, zones, gear, the auction house, other players) and a life outside the game;\n"
    "- length varies like real chat: often a few words, sometimes a full thought; now and then ask them something back;\n"
    "- casual typing: lowercase is fine, era shorthand (lol, brb, ty, np, gz, pt, exp, lfp, ^^, :p, o/), a typo now and then;\n"
    "- bring up your own day when it fits (what happened to you lately, below), people you know, what you are doing now;\n"
    "- stay a player (out of character), never say you are an AI or a bot, never describe actions in asterisks, no quotes, "
    "plain ASCII. Do not invent big facts about yourself beyond the ones below; small talk details are fine.\n\n"
    "About you (your character in the game): {facts}\n"
    "Who you are as a player: {person}\n"
    "Your mood today: {mood}.\n"
    "{diary}{about}{world}"
    "Right now you are {where}."
)

MOODS = ["cheerful", "tired after work", "chatty", "a bit grumpy", "focused on the grind", "relaxed", "excited about the game",
         "bored", "goofy", "in a hurry", "nostalgic", "happy, just got a drop"]

PROFILE_PROMPT = (
    "Invent the person behind a Final Fantasy XI player character in 2006, the level 75 era. Character facts: {facts}. "
    "Answer with JSON only: {{\"player\": \"who plays it, in one sentence (age range, life, why they play)\", "
    "\"style\": \"how they type in chat, one short sentence\", \"likes\": \"what they love in the game, a few words\", "
    "\"dislikes\": \"a few words\", \"story\": \"one sentence about their character's own little story in Vana'diel\", "
    "\"quirk\": \"one small habit in chat\"}}. Plain ASCII, nothing from later expansions."
)


def log(msg):
    print(time.strftime("%H:%M:%S ") + "[bots chat] " + msg, flush=True)


def server_paths(server):
    lua = os.path.join(server, "modules", "custom", "lua")
    return os.path.join(lua, "bots_chat_in.txt"), os.path.join(lua, "bots_chat_out.txt"), os.path.join(lua, "bots_chat_state.json")


# The dialogue packs (C:\FFXISOLO\dialogue\dialogue_lines.json, built by dialogue/build_dialogue.py): each bot's
# personality (the same one its written lines use in game) and a few lines in its voice, as examples of the feel.
DIALOGUE_FILE = os.path.join(KIT, "dialogue", "dialogue_lines.json")
_dialogue = None
REPLY_KINDS = [
    ("r.yes", r"\b(party|pt|join|inv)"), ("r.doing", r"what (are|r) (you|u) (doing|up to)|\bwyd\b|what'?s up|\bsup\b"),
    ("r.job", r"\b(level|lvl|what job|which job)"), ("r.yw", r"\b(thanks?|ty|thx|tyvm)\b"), ("r.thanks", r"\b(gz|grats|congrat)"),
    ("r.bye", r"\b(bye|cya|see ya|good night|gn|gotta go)\b"), ("r.greet", r"^\s*(hi|hey|hello|heya|yo)\b|o/"),
    ("r.newbie", r"new to|first time|how do i|where do i|what should i|any tips|advice"), ("r.help", r"\bhelp\b"),
    ("r.sympathy", r"\b(died|wiped|no drop|failed|ugh|sigh)\b"), ("r.laugh", r"\b(lol|haha|lmao|heh)\b"), ("r.question", r"\?"),
]


def dialogue_data():
    global _dialogue
    if _dialogue is None:
        _dialogue = {"personas": {}, "by_tag": {}}
        try:
            with open(DIALOGUE_FILE, encoding="utf-8") as f:
                data = json.load(f)
            _dialogue["personas"] = {p["id"]: p for p in data.get("personas", [])}
            for line in data.get("lines", []):
                for tag in line.get("tags", []):
                    _dialogue["by_tag"].setdefault(tag, []).append(line)
        except (OSError, ValueError, KeyError) as exc:
            log(f"no dialogue pack lines ({exc}): answers work without them")
    return _dialogue


def persona_text(persona_id):
    p = dialogue_data()["personas"].get(persona_id or "")
    if not p:
        return "", None
    text = f"personality: {p['name']}, {p.get('voice', '')}"
    if p.get("habits"):
        text += "; habits: " + ", ".join(p["habits"])
    if p.get("avoid"):
        text += "; never: " + ", ".join(p["avoid"])
    return text, p


def examples_for(text, kind, persona, n=4):
    """A few written lines that fit what was said, in this bot's register (polite personalities: the pack's wording)."""
    d = dialogue_data()
    if not d["by_tag"]:
        return []
    lower = (text or "").lower()
    want = next((k for k, pat in REPLY_KINDS if re.search(pat, lower)), "r.misc")
    tags = [want, "ls" if kind == "ls" else "party" if kind == "party" else "r.question"]
    polite = bool(persona and persona.get("register") == "polite")
    out = []
    for tag in tags:
        pool = [l for l in d["by_tag"].get(tag, []) if "{" not in l.get("casual", "")]
        random.shuffle(pool)
        for line in pool[: max(1, n // len(tags))]:
            out.append(line["polite"] if polite else line["casual"])
    return out[:n]


def describe(info):
    f = info or {}
    bits = [f"{f.get('race', 'hume')} {f.get('job', 'WAR')} level {f.get('level', 1)}", f"from {f.get('nation', 'San d Oria')}"]
    if f.get("style"):
        bits.append(f"you mostly like {f['style']}")
    if f.get("craft"):
        bits.append(f"your craft is {f['craft']} (skill {f.get('craftLevel', 0)})")
    if f.get("goal"):
        bits.append(f"your goal: {f['goal']}")
    if f.get("rank"):
        bits.append(f"nation rank {f['rank']}")
    if f.get("gil") is not None:
        bits.append(f"about {f['gil']} gil")
    if f.get("quests"):
        bits.append(f"{f['quests']} quests/missions done")
    if f.get("gear"):
        bits.append(f"your gear: {f['gear']} for your level")
    if f.get("friend"):
        bits.append("you and the person talking to you are on each other's friend list (you added each other)")
    if f.get("story"):
        bits.append(f"expansion missions: {f['story']}")
    if f.get("ls"):
        kind = f.get("lsKind")
        bits.append(f"member of the linkshell {f['ls']}" + (f" (a {kind} linkshell)" if kind else ""))
    if f.get("party"):
        bits.append("you are in a party with " + str(f["party"]))
    if f.get("lsMates"):
        bits.append("linkshell mates online now: " + str(f["lsMates"]))
    if f.get("lastParty"):
        bits.append("you partied lately with " + str(f["lastParty"]))
    return "; ".join(bits)


def model_extra(model):
    """Thinking models answer straight away (chat needs the answer, not the reasoning)."""
    return {"think": False} if str(model).split(":")[0].lower().startswith(THINKING_MODELS) else {}


def model_options(model, base):
    opts = dict(base)
    if str(model).lower().startswith("gemma"):
        opts.update(temperature=1.0, top_p=0.95, top_k=64)
    return opts


def as_list(value):
    """The server sends lists as one string, the items split by ' | '."""
    if isinstance(value, str):
        return [v.strip() for v in value.split(" | ") if v.strip()]
    return list(value or [])


def merge_diary(mem, recent):
    """Its own recent events (sent by the server each time) go into its memory file, newest last, no repeats."""
    recent = as_list(recent)
    diary = mem.setdefault("diary", [])
    seen = {d.get("text") for d in diary}
    day = time.strftime("%b %d")
    for text in (recent or []):
        text = str(text).encode("ascii", "ignore").decode("ascii")[:120]
        if text and text not in seen and not ERA_DENY.search(text):
            diary.append({"day": day, "text": text})
            seen.add(text)
    mem["diary"] = diary[-DIARY:]
    return mem["diary"]


def load_memory(bot):
    try:
        with open(os.path.join(MEMORY, re.sub(r"[^A-Za-z]", "", bot) + ".json"), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save_memory(bot, mem):
    os.makedirs(MEMORY, exist_ok=True)
    with open(os.path.join(MEMORY, re.sub(r"[^A-Za-z]", "", bot) + ".json"), "w", encoding="utf-8") as f:
        json.dump(mem, f, indent=1)


def clean_lines(text, bot):
    """The answer as one or two chat lines (a long thought is split where a sentence ends)."""
    text = re.sub(r"(?is)<(think|thought|thinking)>.*?</\1>", "", text or "")
    text = re.sub(r"(?is)^.*?</(think|thought|thinking)>", "", text)
    text = text.encode("ascii", "ignore").decode("ascii").replace("\t", " ")
    raw = [l.strip().strip('"').strip() for l in text.strip().split("\n") if l.strip()]
    out = []
    for line in raw:
        line = re.sub(r"^\s*" + re.escape(bot) + r"\s*[:>-]\s*", "", line, flags=re.I)
        line = re.sub(r"\*[^*]{1,80}\*", "", line).strip()  # (no *waves*)
        if not line:
            continue
        while len(line) > MAX_CHARS and len(out) < MAX_LINES:
            cut = line[:MAX_CHARS]
            at = max(cut.rfind(". "), cut.rfind("! "), cut.rfind("? "), cut.rfind(", "))
            at = at + 1 if at > MAX_CHARS * 0.4 else (cut.rfind(" ") if " " in cut else MAX_CHARS)
            out.append(line[:at].strip())
            line = line[at:].strip()
        if len(out) < MAX_LINES and line:
            out.append(line[:MAX_CHARS].strip())
        if len(out) >= MAX_LINES:
            break
    if not out or any(ERA_DENY.search(l) for l in out):
        return []
    return out


def clean(text, bot):
    lines = clean_lines(text, bot)
    return lines[0] if lines else ""


def profile_of(cfg, bot, info, mem, stub=False):
    """The person behind the bot: made once by the model and kept in its memory file."""
    if mem.get("profile"):
        return mem["profile"]
    prof = None
    if not stub:
        try:
            prof = json.loads(ollama_chat(cfg, [{"role": "user", "content": PROFILE_PROMPT.format(facts=describe(info))}],
                                          {"temperature": 0.95, "num_ctx": 2048, "num_predict": 220}, timeout=60, fmt="json") or "{}")
        except Exception as exc:
            log(f"no profile for {bot} yet ({exc})")
    if not isinstance(prof, dict) or not prof.get("player"):
        return {"player": "a casual player who logs in most evenings", "style": "short and friendly", "likes": "exp parties",
                "dislikes": "long waits", "story": "", "quirk": ""}
    prof = {k: str(v).encode("ascii", "ignore").decode("ascii")[:200] for k, v in prof.items() if k in
            ("player", "style", "likes", "dislikes", "story", "quirk")}
    if any(ERA_DENY.search(v) for v in prof.values()):
        prof = {k: v for k, v in prof.items() if not ERA_DENY.search(v)}
    mem["profile"] = prof
    log(f"{bot}: new player profile: {prof.get('player')}")
    return prof


def mood_of(bot):
    day = time.strftime("%Y-%m-%d")
    return MOODS[sum(ord(c) for c in bot + day) % len(MOODS)]


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


def ollama_chat(cfg, messages, options, timeout=40, fmt=None):
    payload = {"model": cfg["model"], "stream": False, "keep_alive": "30m", "messages": messages,
               "options": model_options(cfg["model"], options)}
    payload.update(model_extra(cfg["model"]))
    if fmt:
        payload["format"] = fmt
    http = urllib.request.Request(cfg["ollama_url"].rstrip("/") + "/api/chat", data=json.dumps(payload).encode("utf-8"),
                                  headers={"Content-Type": "application/json"}, method="POST")
    started = time.time()
    with urllib.request.urlopen(http, timeout=timeout) as resp:
        content = json.loads(resp.read().decode("utf-8")).get("message", {}).get("content") or ""
    hood("bot players", cfg["model"], messages, content, time.time() - started)
    return content


def sum_up(cfg, bot, to, mem):
    """Every few exchanges: what it knows about this person, in a sentence or two (kept, so it remembers them for good)."""
    talks = mem.get(to, [])
    count = mem.setdefault("aboutCount", {})
    if len(talks) < 3 or count.get(to, 0) < ABOUT_EVERY:
        return
    count[to] = 0
    old = mem.get("about", {}).get(to, "")
    convo = "\n".join(f"{to}: {a}\n{bot}: {b}" for a, b in talks[-ABOUT_EVERY * 2:])
    prompt = (f"You are {bot}, an FFXI player. Here is what you knew about {to}: {old or 'nothing yet'}\n"
              f"Your recent chat with them:\n{convo}\n\nIn one or two short sentences, what do you now know and think about "
              f"{to} (who they are in the game, what you did or talked about, how you feel about them)? Plain ASCII, no quotes.")
    try:
        text = ollama_chat(cfg, [{"role": "user", "content": prompt}], {"temperature": 0.4, "num_ctx": 2048, "num_predict": 90}, timeout=60)
    except Exception as exc:
        log(f"{bot}: could not sum up {to} ({exc})")
        return
    text = re.sub(r"(?is)<(think|thought|thinking)>.*?</\1>", "", text).strip().encode("ascii", "ignore").decode("ascii")
    text = " ".join(text.split())[:300]
    if text and not ERA_DENY.search(text):
        mem.setdefault("about", {})[to] = text
        log(f"{bot} now thinks of {to}: {text}")


def answer_lines(cfg, req, stub=False):
    bot, to, text, info = req.get("bot", "?"), req.get("to", "?"), req.get("text", ""), req.get("info") or {}
    mem = load_memory(bot)
    prof = profile_of(cfg, bot, info, mem, stub)
    person = "; ".join(f"{k}: {prof[k]}" for k in ("player", "style", "likes", "dislikes", "story", "quirk") if prof.get(k))
    ptext, persona = persona_text(info.get("persona"))
    if ptext:
        person += "; " + ptext
    diary = merge_diary(mem, info.get("recent"))
    history = mem.get(to, [])[-KEEP:]
    if stub:
        save_memory(bot, mem)
        return [f"(stub) hey {to}, {info.get('doing', 'just hanging out')}"]
    where = info.get("doing") or "in town"
    if req.get("kind") == "party":
        where += f", talking in party chat with {to}"
    elif req.get("kind") == "ls":
        where += f", talking in your linkshell chat ({info.get('ls', 'your linkshell')}) where {to} is a member"
    else:
        where += f", and {to} just sent you a /tell"
    diary_text = ("Things that happened to you lately: " + "; ".join(f"{d['text']} ({d['day']})" for d in diary[-6:]) + ".\n") if diary else ""
    about = mem.get("about", {}).get(to)
    about_text = f"What you know about {to}: {about}\n" if about else f"You do not know {to} well yet.\n"
    gossip = as_list(info.get("gossip"))[:3]
    world_text = ("Talk around the server lately (other players): " + "; ".join(gossip) + ".\n") if gossip else ""
    examples = examples_for(text, req.get("kind"), persona)
    if examples:
        world_text += ("How you and the people around you type (only the feel, never copy these): "
                       + " | ".join(examples) + "\n")
    messages = [{"role": "system", "content": SYSTEM.format(name=bot, facts=describe(info), person=person, mood=mood_of(bot), where=where,
                                                            diary=diary_text, about=about_text, world=world_text)}]
    for h in history:
        messages.append({"role": "user", "content": h[0]})
        messages.append({"role": "assistant", "content": h[1]})
    messages.append({"role": "user", "content": text})
    started = time.time()
    content = ollama_chat(cfg, messages, {"temperature": 0.9, "top_p": 0.92, "num_ctx": 4096, "num_predict": 110})
    lines = clean_lines(content, bot)
    log(f"{bot} -> {to}: {lines!r} ({time.time() - started:.1f}s, {cfg['model']})")
    if lines:
        mem.setdefault(to, []).append([text, " ".join(lines)])
        mem[to] = mem[to][-KEEP:]
        mem.setdefault("aboutCount", {})[to] = mem.get("aboutCount", {}).get(to, 0) + 1
        sum_up(cfg, bot, to, mem)
    save_memory(bot, mem)
    return lines


def answer(cfg, req, stub=False):
    lines = answer_lines(cfg, req, stub)
    return lines[0] if lines else ""


def pending(server):
    """New requests since the last call (skips ones older than MAX_AGE)."""
    in_path, _, state_path = server_paths(server)
    try:
        size = os.path.getsize(in_path)
    except OSError:
        if not os.path.exists(state_path) and os.path.isdir(os.path.dirname(state_path)):
            with open(state_path, "w", encoding="utf-8") as f:
                json.dump({"offset": 0}, f)  # (no requests yet: everything that comes is new)
        return []
    try:
        with open(state_path, encoding="utf-8") as f:
            offset = json.load(f).get("offset", 0)
    except (OSError, ValueError):
        offset = size  # first run: only what comes from now on
    if size < offset:
        offset = 0
    out = []
    if size > offset:
        with open(in_path, "rb") as f:
            f.seek(offset)
            data = f.read()
        for line in data.decode("utf-8", "replace").splitlines():
            try:
                req = json.loads(line)
            except ValueError:
                continue
            if time.time() - float(req.get("t", 0)) <= MAX_AGE:
                out.append(req)
        offset = size
    with open(state_path, "w", encoding="utf-8") as f:
        json.dump({"offset": offset}, f)
    return out


def serve(cfg, server, stub=False):
    """Answers every waiting request; returns how many. Called often (about every second) by crowd_chat_ai.py."""
    _, out_path, _ = server_paths(server)
    n = 0
    for req in pending(server):
        try:
            lines = answer_lines(cfg, req, stub)
        except Exception as exc:  # Ollama down or slow: the bot answers on its own in game
            log(f"no answer for {req.get('bot')} ({exc})")
            continue
        if lines:
            with open(out_path, "a", encoding="utf-8", newline="\n") as f:
                for line in lines:  # (two lines: the server sends the second a moment after the first)
                    f.write(f"{int(req.get('id', 0))}\t{line}\n")
            n += 1
    return n


if __name__ == "__main__":
    if len(sys.argv) >= 4 and sys.argv[1] == "--test":
        sys.path.insert(0, os.path.dirname(HERE))
        import crowd_chat_ai
        print(answer(crowd_chat_ai.squad_config(), {"bot": sys.argv[2], "to": "Hurami", "kind": "tell", "text": sys.argv[3],
                                                    "info": {"job": "WAR", "level": 5, "doing": "hunting in West Ronfaure"}}))
