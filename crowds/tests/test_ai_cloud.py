"""Tests for the hub's bot chat through Google's Gemma (crowds/ai_cloud.py and where it is used, 2026-11-23).
Google is never called: a stand-in answers instead. Run from the kit: python crowds/tests/test_ai_cloud.py"""
import calendar, io, json, os, shutil, stat, sys, tempfile, time, unittest, urllib.error

HERE = os.path.dirname(os.path.abspath(__file__))
KIT = os.path.dirname(os.path.dirname(HERE))
sys.path[:0] = [os.path.join(KIT, "crowds"), os.path.join(KIT, "crowds", "bots"), KIT]
import ai_cloud as ac          # noqa: E402
import bots_chat_ai as bc      # noqa: E402
import crowd_chat_ai as cc     # noqa: E402

KEY = "AIzaTESTKEY0123456789abcdefghij"
NEW_KEY = "AQ.Ab8RN6TESTkey0123456789abcdefghijklmnop"     # (the newer kind has a dot)


def utc(*parts):
    return calendar.timegm(time.struct_time(tuple(parts) + (0,) * (9 - len(parts))))


def answer(text, thought=None):
    parts = ([{"text": thought, "thought": True}] if thought else []) + [{"text": text}]
    return {"candidates": [{"content": {"role": "model", "parts": parts}}]}


def http_error(code, body):
    return urllib.error.HTTPError("https://x", code, "err", {}, io.BytesIO(json.dumps(body).encode()))


DAILY_429 = {"error": {"code": 429, "message": "Quota exceeded", "details": [
    {"@type": "type.googleapis.com/google.rpc.QuotaFailure",
     "violations": [{"quotaMetric": "generativelanguage.googleapis.com/generate_content_free_tier_requests",
                     "quotaId": "GenerateRequestsPerDayPerProjectPerModel-FreeTier"}]},
    {"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": "40s"}]}}
MINUTE_429 = {"error": {"code": 429, "message": "Quota exceeded", "details": [
    {"@type": "type.googleapis.com/google.rpc.QuotaFailure",
     "violations": [{"quotaId": "GenerateRequestsPerMinutePerProjectPerModel-FreeTier"}]},
    {"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": "17s"}]}}


class Google:
    """Stands in for the API: answers in turn from `replies` (dicts, or exceptions to raise) and keeps every call."""

    def __init__(self, *replies):
        self.replies, self.calls = list(replies), []

    def __call__(self, url, key, body, timeout):
        self.calls.append({"url": url, "key": key, "body": body})
        reply = self.replies.pop(0) if self.replies else answer("ok")
        if isinstance(reply, Exception):
            raise reply
        return reply


class Base(unittest.TestCase):
    def setUp(self):
        self.kit = tempfile.mkdtemp()
        ac._meters.clear()
        ac._plain.clear()
        os.environ.pop("XIFO_GOOGLE_AI_KEY", None)

    def tearDown(self):
        shutil.rmtree(self.kit, ignore_errors=True)
        ac._meters.clear()

    def set_up(self, **cfg):
        ac.save_key(KEY, self.kit)
        ac.save_config(dict(ac.DEFAULTS, **cfg), self.kit)


class PacificDay(unittest.TestCase):
    def test_the_day_turns_at_midnight_pacific(self):
        self.assertEqual(ac.pacific_day(utc(2026, 11, 23, 7, 59)), "2026-11-22")      # winter: UTC-8
        self.assertEqual(ac.pacific_day(utc(2026, 11, 23, 8, 0)), "2026-11-23")
        self.assertEqual(ac.pacific_day(utc(2026, 7, 1, 6, 59)), "2026-06-30")        # summer: UTC-7
        self.assertEqual(ac.pacific_day(utc(2026, 7, 1, 7, 0)), "2026-07-01")
        self.assertEqual(ac.pacific_day(utc(2026, 3, 8, 9, 59)), "2026-03-08")        # daylight saving starts 8 March 2026
        self.assertEqual(ac.pacific_day(utc(2026, 11, 1, 8, 30)), "2026-11-01")       # ...and ends 1 November 2026
        self.assertEqual(ac.pacific_day(utc(2026, 11, 2, 7, 30)), "2026-11-01")

    def test_next_midnight(self):
        self.assertEqual(ac.next_pacific_midnight(utc(2026, 11, 23, 22, 15)), utc(2026, 11, 24, 8, 0))
        self.assertEqual(ac.next_pacific_midnight(utc(2026, 7, 1, 1, 0)), utc(2026, 7, 1, 7, 0))


class Setup(Base):
    def test_a_players_world_is_never_switched_on(self):
        self.assertIsNone(ac.load_config(self.kit))
        self.assertFalse(ac.ready(self.kit))
        with self.assertRaises(ac.CloudBusy):
            ac.chat([{"role": "user", "content": "hi"}], kit=self.kit, post=Google())
        ac.save_config(dict(ac.DEFAULTS), self.kit)                    # settings but no key
        self.assertFalse(ac.ready(self.kit))
        ac.save_key(KEY, self.kit)
        self.assertTrue(ac.ready(self.kit))
        ac.save_config(dict(ac.DEFAULTS, enabled=False), self.kit)
        self.assertFalse(ac.ready(self.kit))
        ac.save_config(dict(ac.DEFAULTS, provider="someone-else"), self.kit)
        self.assertFalse(ac.ready(self.kit))

    def test_settings_out_of_range_are_brought_back(self):
        with open(ac.config_path(self.kit), "w") as handle:
            json.dump({"models": ["../../etc", 5], "per_minute": "lots", "per_day": -3, "background_share": 9, "other": 1}, handle)
        cfg = ac.load_config(self.kit)
        self.assertEqual(cfg["models"], ac.DEFAULTS["models"])
        self.assertEqual((cfg["per_minute"], cfg["per_day"], cfg["background_share"]), (ac.DEFAULTS["per_minute"], 1, 1.0))
        self.assertNotIn("other", cfg)

    def test_the_key_is_kept_private_and_checked(self):
        said = []
        google = Google(answer("leveling thf lol"))
        code = ac.main(["key"], kit=self.kit, say=said.append, ask=lambda _t: "  " + KEY + "\n", post=google)
        self.assertEqual(code, 0)
        path = os.path.join(self.kit, ac.KEY_FILE)
        if os.name != "nt":
            self.assertEqual(stat.S_IMODE(os.stat(path).st_mode), 0o600)
        self.assertEqual(ac.read_key(self.kit), KEY)
        self.assertTrue(ac.ready(self.kit))
        self.assertTrue(any("It works" in line for line in said))
        self.assertNotIn(KEY, " ".join(said))
        self.assertNotIn(KEY, google.calls[0]["url"])                 # the key goes in a header, never in the address
        self.assertEqual(google.calls[0]["key"], KEY)
        self.assertEqual(ac.main(["key"], kit=self.kit, say=said.append, ask=lambda _t: "not a key"), 2)
        self.assertEqual(ac.read_key(self.kit), KEY)                  # a bad paste changes nothing
        self.assertEqual(ac.main(["off"], kit=self.kit, say=said.append), 0)
        self.assertFalse(ac.ready(self.kit))
        self.assertEqual(ac.main(["on"], kit=self.kit, say=said.append), 0)
        self.assertTrue(ac.ready(self.kit))
        self.assertEqual(ac.main(["status"], kit=self.kit, say=said.append), 0)
        self.assertNotIn(KEY, " ".join(said))

    def test_both_kinds_of_key(self):
        ac.save_config(dict(ac.DEFAULTS), self.kit)
        for key in (KEY, NEW_KEY):
            ac.save_key(key, self.kit)
            self.assertEqual(ac.read_key(self.kit), key)
        self.assertEqual(ac.main(["key"], kit=self.kit, say=lambda _l: None, ask=lambda _t: NEW_KEY, post=Google(answer("hi"))), 0)
        self.assertEqual(ac.read_key(self.kit), NEW_KEY)

    def test_a_key_from_the_environment(self):
        ac.save_config(dict(ac.DEFAULTS), self.kit)
        os.environ["XIFO_GOOGLE_AI_KEY"] = KEY
        try:
            self.assertTrue(ac.ready(self.kit))
        finally:
            os.environ.pop("XIFO_GOOGLE_AI_KEY")

    def test_a_failed_check_says_why(self):
        said = []
        google = Google(http_error(400, {"error": {"message": "API key not valid. Please pass a valid API key."}}),
                        http_error(400, {"error": {"message": "API key not valid. Please pass a valid API key."}}))
        self.assertEqual(ac.main(["key"], kit=self.kit, say=said.append, ask=lambda _t: KEY, post=google), 1)
        self.assertTrue(any("API key not valid" in line for line in said))


class Requests(Base):
    def test_an_ollama_chat_becomes_a_gemini_request(self):
        messages = [{"role": "system", "content": "You are Aldric."}, {"role": "user", "content": "hi"},
                    {"role": "assistant", "content": "o/"}, {"role": "user", "content": "lfp?"}, {"role": "user", "content": "war 30"}]
        body = ac.to_request(messages, {"temperature": 0.9, "top_p": 0.92, "top_k": 64, "num_predict": 110, "num_ctx": 4096})
        self.assertEqual(body["systemInstruction"], {"parts": [{"text": "You are Aldric."}]})
        self.assertEqual([c["role"] for c in body["contents"]], ["user", "model", "user"])
        self.assertEqual(body["contents"][2]["parts"][0]["text"], "lfp?\nwar 30")
        gen = body["generationConfig"]
        self.assertEqual((gen["temperature"], gen["topP"], gen["topK"]), (0.9, 0.92, 64))
        self.assertGreaterEqual(gen["maxOutputTokens"], 110)
        self.assertEqual(gen["thinkingConfig"], {"thinkingLevel": "minimal"})
        self.assertNotIn("responseMimeType", gen)
        self.assertEqual(ac.to_request(messages, {}, fmt="json")["generationConfig"]["responseMimeType"], "application/json")
        plain = ac.to_request(messages, {}, fmt="json", plain=True)
        self.assertNotIn("systemInstruction", plain)
        self.assertNotIn("thinkingConfig", plain["generationConfig"])
        self.assertNotIn("responseMimeType", plain["generationConfig"])
        self.assertTrue(plain["contents"][0]["parts"][0]["text"].startswith("You are Aldric.\n\nhi"))
        only_model = ac.to_request([{"role": "assistant", "content": "x"}], {})
        self.assertEqual(only_model["contents"][0]["role"], "user")

    def test_answers_leave_thoughts_and_fences_out(self):
        self.assertEqual(ac.from_response(answer("sure thing", thought="The user greets me...")), "sure thing")
        self.assertEqual(ac.from_response(answer("<think>hmm</think>gz!")), "gz!")
        self.assertEqual(ac.from_response(answer('```json\n{"lines": ["a"]}\n```'), "json"), '{"lines": ["a"]}')
        self.assertEqual(ac.from_response({"candidates": [{"finishReason": "SAFETY"}]}), "")
        self.assertEqual(ac.from_response({}), "")

    def test_a_used_up_model_rests_and_the_next_takes_over(self):
        self.set_up()
        google = Google(http_error(429, DAILY_429), answer("hey o/"))
        self.assertEqual(ac.chat([{"role": "user", "content": "hi"}], kit=self.kit, post=google), "hey o/")
        self.assertEqual([c["url"].split("/models/")[1].split(":")[0] for c in google.calls], ac.DEFAULTS["models"])
        resting = ac.meter(self.kit).state["resting"]
        self.assertEqual(list(resting), [ac.DEFAULTS["models"][0]])
        self.assertEqual(resting[ac.DEFAULTS["models"][0]], ac.next_pacific_midnight())     # a daily quota: until midnight Pacific
        google2 = Google(answer("still here"))
        ac.chat([{"role": "user", "content": "hi"}], kit=self.kit, post=google2)
        self.assertIn(ac.DEFAULTS["models"][1], google2.calls[0]["url"])                # the first is not asked meanwhile
        google3 = Google(http_error(429, MINUTE_429))
        with self.assertRaises(ac.CloudBusy):
            ac.chat([{"role": "user", "content": "hi"}], kit=self.kit, post=google3)
        until = ac.meter(self.kit).state["resting"][ac.DEFAULTS["models"][1]]
        self.assertAlmostEqual(until - time.time(), 17, delta=3)                         # the delay Google gave
        with self.assertRaises(ac.CloudBusy):                                            # both resting: nothing is sent
            ac.chat([{"role": "user", "content": "hi"}], kit=self.kit, post=Google())
        self.assertTrue(any("resting until" in line for line in ac.status_lines(self.kit)))

    def test_a_busy_model_rests_briefly_and_the_next_answers(self):
        self.set_up()
        busy = {"error": {"code": 503, "message": "This model is currently experiencing high demand."}}
        google = Google(http_error(503, busy), answer("hey"))
        self.assertEqual(ac.chat([{"role": "user", "content": "hi"}], kit=self.kit, post=google), "hey")
        until = ac.meter(self.kit).state["resting"][ac.DEFAULTS["models"][0]]
        self.assertAlmostEqual(until - time.time(), ac.BUSY_REST, delta=3)
        with self.assertRaises(ac.CloudBusy):                         # both busy: the bots use their own lines
            ac.chat([{"role": "user", "content": "hi"}], kit=self.kit, post=Google(http_error(503, busy)))

    def test_a_model_that_refuses_the_full_request_is_asked_plainly(self):
        self.set_up()
        google = Google(http_error(400, {"error": {"message": "Developer instruction is not enabled"}}), answer("np"), answer("k"))
        self.assertEqual(ac.chat([{"role": "system", "content": "s"}, {"role": "user", "content": "ty"}], kit=self.kit, post=google), "np")
        self.assertIn("systemInstruction", google.calls[0]["body"])
        self.assertNotIn("systemInstruction", google.calls[1]["body"])
        ac.chat([{"role": "system", "content": "s"}, {"role": "user", "content": "ty"}], kit=self.kit, post=google)
        self.assertNotIn("systemInstruction", google.calls[2]["body"])                  # remembered

    def test_errors_are_oserrors_without_the_key(self):
        self.set_up()
        for problem in (http_error(401, {"error": {"message": "denied"}}), urllib.error.URLError("no route"), TimeoutError("slow")):
            with self.assertRaises(OSError) as raised:
                ac.chat([{"role": "user", "content": "hi"}], kit=self.kit, post=Google(problem))
            self.assertIsInstance(raised.exception, ac.CloudError)
            self.assertNotIn(KEY, str(raised.exception))

    def test_players_come_first(self):
        self.set_up(per_minute=100, per_day=10, background_share=0.3)   # (so only the day can say no)
        google = Google(*[answer("x")] * 50)
        for _ in range(3):
            ac.chat([{"role": "user", "content": "pool"}], kind="background", kit=self.kit, post=google)
        with self.assertRaises(ac.CloudBusy):                         # background has had its share of the day (3 of 10)
            ac.chat([{"role": "user", "content": "pool"}], kind="background", kit=self.kit, post=google)
        for _ in range(7):
            ac.chat([{"role": "user", "content": "tell"}], kind="reply", kit=self.kit, post=google)
        with self.assertRaises(ac.CloudBusy):                         # the day is used up
            ac.chat([{"role": "user", "content": "tell"}], kind="reply", kit=self.kit, post=google)
        self.assertEqual(len(google.calls), 10)
        used = ac.meter(self.kit).state["used"]
        self.assertEqual((used["reply"], used["background"]), (7, 3))

    def test_the_minute_limit_and_background_holding_back(self):
        self.set_up(per_minute=4, per_day=1000, background_share=0.5)
        google = Google(*[answer("x")] * 50)
        ac.chat([{"role": "user", "content": "a"}], kind="background", kit=self.kit, post=google)
        ac.chat([{"role": "user", "content": "b"}], kind="background", kit=self.kit, post=google)
        with self.assertRaises(ac.CloudBusy):                         # half the minute is for background at most
            ac.chat([{"role": "user", "content": "c"}], kind="background", kit=self.kit, post=google)
        ac.chat([{"role": "user", "content": "d"}], kind="reply", kit=self.kit, post=google)
        ac.chat([{"role": "user", "content": "e"}], kind="reply", kit=self.kit, post=google)
        with self.assertRaises(ac.CloudBusy):
            ac.chat([{"role": "user", "content": "f"}], kind="reply", kit=self.kit, post=google)
        m = ac.meter(self.kit)
        m.minute = [t - 61 for t in m.minute]                         # a minute later
        ac.chat([{"role": "user", "content": "g"}], kind="reply", kit=self.kit, post=google)

    def test_the_count_survives_a_restart_and_starts_again_each_day(self):
        self.set_up(per_day=2)
        clock = [utc(2026, 11, 23, 20, 0)]
        ac._meters[self.kit] = ac.Meter(self.kit, clock=lambda: clock[0])
        google = Google(*[answer("x")] * 10)
        ac.chat([{"role": "user", "content": "a"}], kit=self.kit, post=google)
        ac.chat([{"role": "user", "content": "b"}], kit=self.kit, post=google)
        ac._meters[self.kit] = ac.Meter(self.kit, clock=lambda: clock[0])                  # the helper started again
        with self.assertRaises(ac.CloudBusy):
            ac.chat([{"role": "user", "content": "c"}], kit=self.kit, post=google)
        clock[0] = utc(2026, 11, 24, 8, 1)                                                  # just after midnight Pacific
        self.assertEqual(ac.chat([{"role": "user", "content": "d"}], kit=self.kit, post=google), "x")
        self.assertEqual(ac.meter(self.kit).state["day"], "2026-11-24")


class Callers(Base):
    """The bots' chat and the town small talk use Google only on a world that is set up for it."""

    def setUp(self):
        super().setUp()
        self.kept = (cc.KIT, bc.KIT, ac.chat, bc.MEMORY)
        cc.KIT = bc.KIT = self.kit
        bc.MEMORY = os.path.join(self.kit, "chat_memory")
        os.makedirs(os.path.join(self.kit, "squad-chat"))
        with open(os.path.join(self.kit, "squad-chat", "config.json"), "w") as handle:
            json.dump({"model": "gemma4:12b", "ollama_url": "http://127.0.0.1:9"}, handle)
        self.sent = []

    def tearDown(self):
        cc.KIT, bc.KIT, ac.chat, bc.MEMORY = self.kept
        super().tearDown()

    def stand_in(self, *replies):
        replies = list(replies)

        def chat(messages, options=None, kind="reply", fmt=None, kit=None, post=None):
            self.sent.append({"messages": messages, "kind": kind, "fmt": fmt, "kit": kit})
            reply = replies.pop(0) if replies else "ok"
            if isinstance(reply, Exception):
                raise reply
            return reply
        ac.chat = chat

    def test_a_players_world_keeps_its_own_ollama(self):
        cc._installed.update(at=time.time(), names=["gemma4:12b"])
        cfg = cc.squad_config()
        self.assertNotEqual(cfg.get("provider"), "google")
        self.assertEqual(cfg["ollama_url"], "http://127.0.0.1:9")

    def test_the_hub_answers_through_google(self):
        self.set_up()
        cfg = cc.squad_config()
        self.assertEqual((cfg["provider"], cfg["model"]), ("google", ac.DEFAULTS["models"][0]))
        self.stand_in('{"player": "a nurse who plays after night shifts", "style": "short", "likes": "bcnms"}', "lol hey, just got here")
        lines = bc.answer_lines(cfg, {"bot": "Aldric", "to": "Hurami", "kind": "tell", "text": "hi!",
                                      "info": {"job": "WAR", "level": 20, "doing": "hunting in Valkurm Dunes"}})
        self.assertEqual(lines, ["lol hey, just got here"])
        self.assertEqual([(s["kind"], s["fmt"]) for s in self.sent], [("background", "json"), ("reply", None)])
        self.assertEqual(self.sent[0]["kit"], self.kit)
        self.assertIn("You are Aldric", self.sent[1]["messages"][0]["content"])
        self.assertEqual(self.sent[1]["messages"][-1], {"role": "user", "content": "hi!"})

    def test_when_google_has_no_room_the_bot_uses_its_own_lines(self):
        self.set_up()
        cfg = cc.squad_config()
        server = os.path.join(self.kit, "server")
        os.makedirs(os.path.join(server, "modules", "custom", "lua"))
        in_path, out_path, state_path = bc.server_paths(server)
        with open(state_path, "w") as handle:
            json.dump({"offset": 0}, handle)
        with open(in_path, "w") as handle:
            handle.write(json.dumps({"id": 3, "t": time.time(), "bot": "Aldric", "to": "Hurami", "kind": "tell", "text": "hi"}) + "\n")
        self.stand_in(ac.CloudBusy("today's limit is used up"), ac.CloudBusy("today's limit is used up"))
        self.assertEqual(bc.serve(cfg, server), 0)
        self.assertFalse(os.path.exists(out_path) and open(out_path).read())

    def test_town_small_talk_is_background_work_in_json(self):
        self.set_up()
        cfg = cc.squad_config()
        self.stand_in('{"lines": ["anyone selling crab meat?", "brb food"]}')
        content = cc.ask_model(cfg, "say", [])
        self.assertEqual(cc.parse("say", content), ["anyone selling crab meat?", "brb food"])
        self.assertEqual((self.sent[0]["kind"], self.sent[0]["fmt"]), ("background", "json"))


class World(Base):
    """The world without a window starts the chat helper only when it is set up, and visitors are told."""

    def test_visitors_are_told(self):
        import launcher_coop as co
        with open(os.path.join(self.kit, "rates.json"), "w") as handle:
            json.dump({"bots": True, "bots_online": 100}, handle)
        os.makedirs(os.path.join(self.kit, "crowds"))
        shutil.copy(ac.__file__, os.path.join(self.kit, "crowds", "ai_cloud.py"))
        self.assertNotIn("ai_chat", co.world_rules(self.kit))
        self.assertNotIn("Google", co.describe_rules(co.world_rules(self.kit)))
        self.set_up()
        rules = co.world_rules(self.kit)
        self.assertEqual(rules["ai_chat"], "google")
        self.assertIn("bot chat by Google's Gemma AI", co.describe_rules(rules))
        with open(os.path.join(self.kit, "rates.json"), "w") as handle:
            json.dump({"bots": False}, handle)
        self.assertNotIn("ai_chat", co.world_rules(self.kit))                    # no bots, nothing to tell

    def test_the_world_starts_the_helper_only_when_set_up(self):
        import launcher_world as wd
        started = []

        class Fake:
            pass

        world = Fake()
        world.kit, world.logs, world.logfiles, world.helpers = self.kit, os.path.join(self.kit, "logs"), [], {}
        world.cfg, world.rates, world.said = {"server_dir": os.path.join(self.kit, "server")}, {"bots": True, "crowds": False}, []
        world.say = world.said.append
        os.makedirs(world.logs)
        os.makedirs(os.path.join(self.kit, "crowds"))
        shutil.copy(ac.__file__, os.path.join(self.kit, "crowds", "ai_cloud.py"))
        open(os.path.join(self.kit, "crowds", "crowd_chat_ai.py"), "w").close()
        world.cloud_chat = lambda: wd.World.cloud_chat(world)
        popen = wd.subprocess.Popen
        wd.subprocess.Popen = lambda args, **kw: started.append(args) or Fake()
        try:
            self.assertFalse(world.cloud_chat())
            wd.World.start_helpers(world)
            self.assertEqual(started, [])
            self.set_up()
            ac._meters.clear()
            self.assertTrue(world.cloud_chat())
            wd.World.start_helpers(world)
            self.assertEqual(len(started), 1)
            self.assertIn("--bots-only", started[0])
            self.assertIn(world.cfg["server_dir"], started[0])
            self.assertIn("chat_ai", world.helpers)
            world.rates = {"bots": False, "crowds": False}
            self.assertFalse(world.cloud_chat())                              # a quiet world: no bots to chat
        finally:
            wd.subprocess.Popen = popen
            for handle in world.logfiles:
                handle.close()


if __name__ == "__main__":
    unittest.main(verbosity=1)
