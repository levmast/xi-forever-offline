"""Bot chat through Google's Gemma 4 on the Gemini API's free tier, for a world that runs on a server with no AI of its own
(the hub). Players' own worlds never use this: without the file ai-cloud.json in the kit, nothing here is switched on and
the bots talk through the player's local Ollama exactly as before.

    python crowds/ai_cloud.py key       paste the API key (from Google AI Studio); it is kept in ai-cloud-key.txt, readable
                                        by this user only, and one small request checks it
    python crowds/ai_cloud.py test      one request with the saved key, and what it answered
    python crowds/ai_cloud.py status    on or off, the models, today's use and limits
    python crowds/ai_cloud.py off       stop using it (the key stays); 'on' starts again
  From the packaged launcher: XI-Forever-Offline --run crowds/ai_cloud.py <command>
  Restart the world afterwards (systemctl restart xifo-world) so its chat helper starts or stops.

How it spends the free tier: Google does not publish the free tier's numbers, so the world keeps its own limits
(ai-cloud.json: per_minute, per_day) and gives the bots' answers to real players first. Background work (the town small
talk pool, a bot's first profile, its notes about a player) may use only a share of them. When a limit is reached, or
Google answers "too many requests", the bots go back to their dialogue-pack lines until there is room again. Google's
daily quotas start again at midnight Pacific time, and so does the world's own count.

On the free tier Google may use what is sent to improve its products, so players are told on the CO-OP page that bot
chat in this world goes to Google. The key is sent in a request header, never in an address, and never written to a log.
Standard library only (the packaged launcher has no other packages).
"""
import datetime
import getpass
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
KIT = os.path.dirname(HERE)
CONFIG_FILE = "ai-cloud.json"                    # in the kit (never in a release: the kit's .gitignore leaves it out)
KEY_FILE = "ai-cloud-key.txt"
STATE_FILE = os.path.join("logs", "ai-cloud-state.json")
API = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
DEFAULTS = {
    "provider": "google",
    "enabled": True,
    # the larger model first; the second has a quota of its own and takes over while the first is used up
    "models": ["gemma-4-31b-it", "gemma-4-26b-a4b-it"],
    "per_minute": 20,                            # requests a minute, all models together
    "per_day": 2500,                             # requests a Pacific day, all models together
    "background_share": 0.3,                     # the most of either limit that background work may use
    "timeout": 30,
}
KINDS = ("reply", "background")
BUSY_REST = 120                                  # seconds a model rests after Google says it is busy


class CloudBusy(OSError):
    """No request was sent: a limit is reached or every model is resting. The bots use their own lines meanwhile."""


class CloudError(OSError):
    """Google answered with an error (the text never holds the key)."""


# ----- settings and the key -----
def config_path(kit=KIT):
    return os.path.join(kit, CONFIG_FILE)


def load_config(kit=KIT):
    """ai-cloud.json merged over the defaults, or None when the file is not there (a player's own world)."""
    try:
        with open(config_path(kit), encoding="utf-8-sig") as handle:
            given = json.load(handle)
    except (OSError, ValueError):
        return None
    if not isinstance(given, dict):
        return None
    out = dict(DEFAULTS)
    out.update({k: v for k, v in given.items() if k in DEFAULTS})
    models = [m for m in (out.get("models") or []) if isinstance(m, str) and re.fullmatch(r"[a-z0-9][a-z0-9.\-]{1,60}", m)]
    out["models"] = models or list(DEFAULTS["models"])
    for key, low, high in (("per_minute", 1, 1000), ("per_day", 1, 1000000), ("timeout", 5, 120)):
        try:
            out[key] = max(low, min(high, int(out[key])))
        except (TypeError, ValueError):
            out[key] = DEFAULTS[key]
    try:
        out["background_share"] = max(0.0, min(1.0, float(out["background_share"])))
    except (TypeError, ValueError):
        out["background_share"] = DEFAULTS["background_share"]
    out["enabled"] = out.get("enabled") is not False and out.get("provider") == "google"
    return out


def save_config(cfg, kit=KIT):
    path = config_path(kit)
    keep = {k: cfg[k] for k in DEFAULTS if k in cfg}
    with open(path + ".part", "w", encoding="utf-8", newline="\n") as handle:
        json.dump(keep, handle, indent=1)
    os.replace(path + ".part", path)


def read_key(kit=KIT):
    """The API key: the environment's XIFO_GOOGLE_AI_KEY, else ai-cloud-key.txt. '' when there is none."""
    key = os.environ.get("XIFO_GOOGLE_AI_KEY", "").strip()
    if not key:
        try:
            with open(os.path.join(kit, KEY_FILE), encoding="utf-8-sig") as handle:
                key = handle.read().strip()
        except OSError:
            key = ""
    return key if re.fullmatch(r"[A-Za-z0-9_.\-]{20,200}", key) else ""


def save_key(key, kit=KIT):
    path = os.path.join(kit, KEY_FILE)
    fd = os.open(path + ".part", os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(key.strip() + "\n")
    os.replace(path + ".part", path)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def ready(kit=KIT):
    """True when this world's bots should chat through Google: switched on, and a key is saved."""
    cfg = load_config(kit)
    return bool(cfg and cfg["enabled"] and read_key(kit))


# ----- the Pacific day (Google's daily quotas start again at midnight Pacific time) -----
def pacific_day(now=None):
    """'YYYY-MM-DD' in US Pacific time, with daylight saving time (second Sunday of March to first Sunday of November,
    at 2 a.m.). Worked out by hand: the packaged launcher may have no time zone data."""
    utc = datetime.datetime.fromtimestamp(time.time() if now is None else now, datetime.timezone.utc).replace(tzinfo=None)

    def nth_sunday(year, month, n):
        first = datetime.datetime(year, month, 1)
        return first + datetime.timedelta(days=(6 - first.weekday()) % 7 + 7 * (n - 1))

    year = utc.year
    dst_start = nth_sunday(year, 3, 2) + datetime.timedelta(hours=10)      # 2 a.m. PST = 10:00 UTC
    dst_end = nth_sunday(year, 11, 1) + datetime.timedelta(hours=9)        # 2 a.m. PDT = 09:00 UTC
    offset = -7 if dst_start <= utc < dst_end else -8
    return (utc + datetime.timedelta(hours=offset)).strftime("%Y-%m-%d")


def next_pacific_midnight(now=None):
    """The time (seconds) of the next midnight Pacific."""
    now = time.time() if now is None else now
    day = pacific_day(now)
    step = now - now % 1800 + 1800
    while pacific_day(step) == day:              # (half-hour steps: midnight always falls on one)
        step += 1800
    return step


# ----- what has been spent today -----
class Meter:
    """Today's count of requests (kept in logs/ai-cloud-state.json across restarts), the last minute's requests, and
    the models that are resting after Google said they are used up."""

    def __init__(self, kit=KIT, clock=time.time):
        self.kit, self.clock = kit, clock
        self.path = os.path.join(kit, STATE_FILE)
        self.minute = []
        self.state = {"day": pacific_day(self.clock()), "used": {k: 0 for k in KINDS}, "resting": {}, "answers": 0, "errors": 0}
        try:
            with open(self.path, encoding="utf-8") as handle:
                saved = json.load(handle)
            if isinstance(saved, dict) and isinstance(saved.get("used"), dict):
                self.state.update({k: saved[k] for k in ("day", "used", "resting", "answers", "errors") if k in saved})
        except (OSError, ValueError):
            pass
        self.roll()

    def roll(self):
        today = pacific_day(self.clock())
        if self.state.get("day") != today:
            self.state.update(day=today, used={k: 0 for k in KINDS}, answers=0, errors=0)
        now = self.clock()
        self.state["resting"] = {m: t for m, t in (self.state.get("resting") or {}).items() if isinstance(t, (int, float)) and t > now}
        self.minute = [t for t in self.minute if now - t < 60]

    def total(self):
        return sum(int(self.state["used"].get(k, 0)) for k in KINDS)

    def room(self, cfg, kind):
        """None when a request of this kind may go out now, else why not."""
        self.roll()
        if self.total() >= cfg["per_day"]:
            return "today's limit is used up"
        if len(self.minute) >= cfg["per_minute"]:
            return "this minute's limit is used up"
        if kind == "background":
            share = cfg["background_share"]
            if self.state["used"].get("background", 0) >= int(cfg["per_day"] * share):
                return "today's share for background work is used up"
            if len(self.minute) >= max(0, int(cfg["per_minute"] * share)):
                return "background work waits for a quieter minute"
        return None

    def spend(self, kind):
        self.minute.append(self.clock())
        self.state["used"][kind] = int(self.state["used"].get(kind, 0)) + 1
        self.save()

    def rest(self, model, until):
        self.state["resting"][model] = float(until)
        self.save()

    def resting(self, model):
        self.roll()
        return model in self.state["resting"]

    def note(self, ok):
        self.state["answers" if ok else "errors"] = int(self.state.get("answers" if ok else "errors", 0)) + 1
        self.save()

    def save(self):
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            with open(self.path + ".part", "w", encoding="utf-8") as handle:
                json.dump(self.state, handle)
            os.replace(self.path + ".part", self.path)
        except OSError:
            pass


_meters = {}


def meter(kit=KIT):
    if kit not in _meters:
        _meters[kit] = Meter(kit)
    return _meters[kit]


# ----- one request -----
def to_request(messages, options, fmt=None, plain=False):
    """An Ollama-style chat (system / user / assistant messages and Ollama options) as a generateContent body.
    plain=True: no system instruction (its text goes in front of the first user message), no thinking setting and no
    JSON mode, for a model that refuses those."""
    system = "\n\n".join(str(m.get("content", "")) for m in messages if m.get("role") == "system").strip()
    contents = []
    for m in messages:
        role = {"user": "user", "assistant": "model"}.get(m.get("role"))
        text = str(m.get("content", ""))
        if role is None or not text.strip():
            continue
        if contents and contents[-1]["role"] == role:          # (the API wants the two sides to take turns)
            contents[-1]["parts"][0]["text"] += "\n" + text
        else:
            contents.append({"role": role, "parts": [{"text": text}]})
    if not contents or contents[0]["role"] != "user":
        contents.insert(0, {"role": "user", "parts": [{"text": "(chat)"}]})
    options = options or {}
    gen = {"maxOutputTokens": int(options.get("num_predict", 200)) * 2 + 200}
    for ours, theirs in (("temperature", "temperature"), ("top_p", "topP"), ("top_k", "topK")):
        if options.get(ours) is not None:
            gen[theirs] = options[ours]
    body = {"contents": contents, "generationConfig": gen}
    if plain:
        if system:
            contents[0]["parts"][0]["text"] = system + "\n\n" + contents[0]["parts"][0]["text"]
    else:
        if system:
            body["systemInstruction"] = {"parts": [{"text": system}]}
        gen["thinkingConfig"] = {"thinkingLevel": "minimal"}        # chat needs the answer, not the reasoning
        if fmt == "json":
            gen["responseMimeType"] = "application/json"
    return body


def from_response(data, fmt=None):
    """The answer's text (thoughts left out), or '' when there is none."""
    try:
        parts = data["candidates"][0]["content"]["parts"]
    except (KeyError, IndexError, TypeError):
        return ""
    text = "".join(str(p.get("text", "")) for p in parts if isinstance(p, dict) and not p.get("thought"))
    text = re.sub(r"(?is)<(think|thought|thinking)>.*?</\1>", "", text).strip()
    if fmt == "json":
        fenced = re.fullmatch(r"(?s)\s*```(?:json)?\s*(.*?)\s*```\s*", text)
        if fenced:
            text = fenced.group(1)
    return text


def retry_after(error_body, now):
    """When a model that was refused with 429 may be asked again: midnight Pacific for a daily quota, else the delay
    Google gave (one minute when it gave none)."""
    try:
        details = json.loads(error_body).get("error", {}).get("details", [])
    except (ValueError, AttributeError):
        details = []
    wait, daily = 60.0, False
    for d in details if isinstance(details, list) else []:
        if not isinstance(d, dict):
            continue
        if "RetryInfo" in str(d.get("@type", "")):
            m = re.fullmatch(r"(\d+(?:\.\d+)?)s", str(d.get("retryDelay", "")))
            if m:
                wait = max(5.0, float(m.group(1)))
        for v in d.get("violations", []) if isinstance(d.get("violations"), list) else []:
            if "perday" in str(v.get("quotaId", "")).lower().replace("_", "") or "day" in str(v.get("quotaMetric", "")).lower():
                daily = True
    return next_pacific_midnight(now) if daily else now + wait


def _post(url, key, body, timeout):
    request = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), method="POST",
                                     headers={"Content-Type": "application/json", "x-goog-api-key": key})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


_plain = set()                                   # models that refused the full request once (asked plainly from then on)


def chat(messages, options=None, kind="reply", fmt=None, kit=KIT, post=None):
    """One answer through Google. kind 'reply' (a bot answering a real player) or 'background'. Raises CloudBusy when
    nothing was sent, CloudError (an OSError) when Google refused, so the callers' own fallbacks take over."""
    cfg = load_config(kit)
    key = read_key(kit)
    if not cfg or not cfg["enabled"] or not key:
        raise CloudBusy("cloud chat is not set up")
    post = post or _post
    m = meter(kit)
    why = m.room(cfg, kind if kind in KINDS else "background")
    if why:
        raise CloudBusy(why)
    last = "every model is resting"
    for model in cfg["models"]:
        if m.resting(model):
            continue
        for plain in ((True,) if model in _plain else (False, True)):
            body = to_request(messages, options, fmt=fmt, plain=plain)
            m.spend(kind if kind in KINDS else "background")
            try:
                data = post(API.format(model=model), key, body, cfg["timeout"])
            except urllib.error.HTTPError as e:
                text = ""
                try:
                    text = e.read().decode("utf-8", "replace")
                except Exception:
                    pass
                if e.code == 429:
                    m.rest(model, retry_after(text, m.clock()))
                    last = f"{model} is used up for now"
                    break                                    # the next model
                if e.code in (500, 502, 503, 504):           # busy at Google ("high demand"): rest it a little, ask the next
                    m.rest(model, m.clock() + BUSY_REST)
                    last = f"{model} is busy at Google right now"
                    break
                if e.code == 400 and not plain:
                    _plain.add(model)
                    continue                                 # the same model, asked plainly
                m.note(False)
                raise CloudError(f"Google answered {e.code} for {model}: " + _short(text))
            except (urllib.error.URLError, TimeoutError, OSError) as e:
                m.note(False)
                raise CloudError(f"Google could not be reached ({getattr(e, 'reason', e)})")
            answer = from_response(data, fmt)
            m.note(bool(answer))
            return answer
    raise CloudBusy(last)


def _short(text):
    try:
        message = json.loads(text).get("error", {}).get("message", "")
    except (ValueError, AttributeError):
        message = text
    return " ".join(str(message).split())[:200]


# ----- by hand -----
def status_lines(kit=KIT):
    cfg = load_config(kit)
    if cfg is None:
        return ["Cloud bot chat is not set up on this world (no ai-cloud.json). 'key' sets it up."]
    m = meter(kit)
    m.roll()
    lines = [("On" if ready(kit) else "Off") + " - " + ("key saved" if read_key(kit) else "no key saved") +
             ("" if cfg["enabled"] else ", switched off"),
             "Models: " + ", ".join(cfg["models"]),
             f"Today ({m.state['day']}, Pacific): {m.total()} of {cfg['per_day']} requests "
             f"({m.state['used'].get('reply', 0)} answers to players, {m.state['used'].get('background', 0)} background), "
             f"{m.state.get('answers', 0)} answered, {m.state.get('errors', 0)} errors",
             f"Limits: {cfg['per_minute']} a minute, {cfg['per_day']} a day, background at most {int(cfg['background_share'] * 100)}%"]
    for model, until in sorted(m.state["resting"].items()):
        lines.append(f"{model} is resting until " + time.strftime("%Y-%m-%d %H:%M", time.localtime(until)))
    return lines


TEST_MESSAGES = [{"role": "system", "content": "You are a player in Final Fantasy XI in 2006. Answer in a few casual words."},
                 {"role": "user", "content": "hey, what job are you leveling?"}]


def main(argv, kit=KIT, say=print, ask=None, post=None):
    command = argv[0] if argv else "status"
    if command == "key":
        ask = ask or (lambda text: getpass.getpass(text))
        key = (ask("Paste the API key from Google AI Studio (it is not shown) and press Enter: ") or "").strip()
        if not re.fullmatch(r"[A-Za-z0-9_.\-]{20,200}", key):
            say("That does not look like an API key. Nothing was saved.")
            return 2
        save_key(key, kit)
        cfg = load_config(kit) or dict(DEFAULTS)
        cfg["enabled"] = True
        cfg["provider"] = "google"
        save_config(cfg, kit)
        say("Key saved. Checking it with one small request...")
        command = "test"
    if command == "test":
        try:
            answer = chat(TEST_MESSAGES, {"num_predict": 40, "temperature": 1.0}, kind="reply", kit=kit, post=post)
        except OSError as e:
            say(f"It did not work: {e}")
            return 1
        say(f"It works. The model answered: {answer!r}")
        say("Restart the world so its chat helper starts: systemctl restart xifo-world")
        return 0
    if command in ("on", "off"):
        cfg = load_config(kit) or dict(DEFAULTS)
        cfg["enabled"] = command == "on"
        save_config(cfg, kit)
        say(f"Cloud bot chat is {command}. Restart the world for it to take effect: systemctl restart xifo-world")
        return 0
    if command == "status":
        for line in status_lines(kit):
            say(line)
        return 0
    say(__doc__.split("\n\n")[1])
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
