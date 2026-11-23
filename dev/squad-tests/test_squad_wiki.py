"""Wiki answers in the squad-chat sidecar: off unless switched on, only questions are looked up, only on the Phoenix
wiki, the page is cleaned and handed to the model with the order to answer from it alone.

Run with: python test_squad_wiki.py
Nothing here goes to the internet or touches the real squad-chat files: the website is a stand-in.
"""

import copy
import importlib.util
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("squad_chat", ROOT / "squad-chat" / "squad_chat.py")
sc = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(sc)

# the real page, as the Phoenix wiki's own API gave it on 2026-11-22
PAGE = ("__NOTOC__\n{{Quest\n|name=Mihgo's Amigo\n|area=Windurst\n|requirementsLabel=Required quests\n|fame=No explicit fame check\n"
        "|start=[[Nanaa Mihgo (Windurst Woods)|Nanaa Mihgo]]\n|zone=[[Windurst Woods]]\n|map=J-3\n|rewards=200 gil<br>Title: Cat Burglar Groupie\n}}\n"
        "'''Mihgo's Amigo''' is a Windurst quest started by [[Nanaa Mihgo (Windurst Woods)|Nanaa Mihgo]] ([[Windurst Woods]] J-3).\n"
        "'''Repeatable:''' Yes.\n== Walkthrough ==\n* Talk to [[Nanaa Mihgo (Windurst Woods)|Nanaa Mihgo]] and then talk to her henchman, [[Cha Lebagta (NPC)|Cha Lebagta]].\n"
        "* [[Nanaa Mihgo (Windurst Woods)|Nanaa Mihgo]] asks for four Yagudo Necklaces.\nTrade four Yagudo Bead Necklaces for 200 gil. The first completion grants 30 Norg fame; repeat trades grant 15 Norg fame.\n"
        "== Related items ==\n* {{Item link|498|Yagudo Necklace|Yagudo Necklace}}\n== Rewards ==\n* 200 gil\n* Title: Cat Burglar Groupie\n"
        "{{Source data|Phoenix LSB fork 21dff3a01128|guide=[https://edenxi.miraheze.org/wiki/Mihgo's_Amigo Eden Wiki contributors] · adapted}}\n"
        "[[Category:Quests]]\n[[Category:Windurst quests]]\n<!-- Generated from Phoenix game data above this line. Add notes below it. -->")


class Site:
    """Answers like the wiki: a search finds the page only when every word is on it (no plurals), as MediaWiki does."""

    def __init__(self, down=False):
        self.calls, self.down = [], down

    def __call__(self, params):
        self.calls.append(dict(params))
        if self.down:
            return None
        if params.get("list") == "search":
            text = ("Mihgo's Amigo " + PAGE).lower()
            hit = all(word in text for word in params["srsearch"].lower().split())
            return {"query": {"search": [{"title": "Mihgo's Amigo"}] if hit else []}}
        return {"query": {"pages": [{"title": params["titles"], "revisions": [{"slots": {"main": {"content": PAGE}}}]}]}}


class WikiAnswers(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.keep = (sc.BASE, sc.CONFIG, sc.PROFILES, sc.WIKI_FETCH, dict(sc.WIKI_CACHE))
        sc.BASE = Path(self.tmp.name)
        sc.CONFIG = copy.deepcopy(sc.DEFAULT_CONFIG)
        sc.PROFILES = {"Kasumi": {"name": "Kasumi"}}
        sc.WIKI_CACHE.clear()
        self.site = Site()
        sc.WIKI_FETCH = self.site
        self.notes = []
        self.keep_out, sc.write_out = sc.write_out, lambda kind, mate, text: self.notes.append((kind, text))
        self.keep_log, sc.log = sc.log, lambda message: None

    def tearDown(self):
        sc.BASE, sc.CONFIG, sc.PROFILES, sc.WIKI_FETCH, cache = self.keep
        sc.WIKI_CACHE.clear()
        sc.WIKI_CACHE.update(cache)
        sc.write_out, sc.log = self.keep_out, self.keep_log
        self.tmp.cleanup()

    def test_off_by_default_and_nothing_is_looked_up(self):
        self.assertFalse(sc.DEFAULT_CONFIG["wiki"]["enabled"])
        self.assertIsNone(sc.wiki_lookup("how many necklaces does Nanaa Mihgo want?"))
        self.assertEqual(self.site.calls, [])

    def test_only_the_phoenix_wiki(self):
        self.assertEqual(sc.DEFAULT_CONFIG["wiki"]["url"], "https://wiki.phoenix-xi.com/api.php")

    def test_only_questions_are_looked_up(self):
        sc.set_wiki(True)
        for line in ("nice fight everyone", "Kasumi", "lol", "pull the next one"):
            self.assertIsNone(sc.wiki_lookup(line), line)
        self.assertEqual(self.site.calls, [])
        for line in ("where is Nanaa Mihgo", "Nanaa Mihgo wants necklaces?", "What's the reward for Mihgo's Amigo"):
            self.assertTrue(sc.looks_like_question(line), line)

    def test_a_question_finds_the_page_plural_or_not(self):
        sc.set_wiki(True)
        found = sc.wiki_lookup("Kasumi, how many necklaces do I need to give Nanaa Mihgo?")
        self.assertIsNotNone(found)
        title, body = found
        self.assertEqual(title, "Mihgo's Amigo")
        self.assertIn("asks for four Yagudo Necklaces", body)
        searches = [c["srsearch"] for c in self.site.calls if c.get("list") == "search"]
        self.assertEqual(searches, ["necklaces nanaa mihgo"])               # the mate's name and the small words are left out
        # a plural the page does not have ("Title:"): tried again without its s
        self.site.calls.clear()
        self.assertEqual(sc.wiki_lookup("what titles does Mihgo's Amigo give?")[0], "Mihgo's Amigo")
        searches = [c["srsearch"] for c in self.site.calls if c.get("list") == "search"]
        self.assertEqual(searches, ["titles mihgo amigo", "title mihgo amigo"])

    def test_the_page_is_plain_text(self):
        plain = sc.strip_wikitext(PAGE)
        for junk in ("[[", "]]", "{{", "}}", "'''", "__NOTOC__", "Category:", "Source data", "<!--", "<br>", "requirementsLabel", "edenxi"):
            self.assertNotIn(junk, plain, junk)
        for kept in ("start: Nanaa Mihgo", "zone: Windurst Woods", "rewards: 200 gil; Title: Cat Burglar Groupie", "Walkthrough:",
                     "- Talk to Nanaa Mihgo and then talk to her henchman, Cha Lebagta.", "- Yagudo Necklace", "Repeatable: Yes."):
            self.assertIn(kept, plain, kept)

    def test_a_long_page_keeps_its_opening_and_the_lines_about_the_question(self):
        text = "\n".join(["Opening line."] + [f"filler line number {i} about nothing" for i in range(80)] + ["The moat carp bites at night."])
        cut = sc.wiki_extract(text, ["carp", "night"], 300)
        self.assertLessEqual(len(cut), 300)
        self.assertIn("Opening line.", cut)
        self.assertIn("The moat carp bites at night.", cut)

    def test_asked_twice_looked_up_once(self):
        sc.set_wiki(True)
        sc.wiki_lookup("how many necklaces for Nanaa Mihgo?")
        n = len(self.site.calls)
        sc.wiki_lookup("how many necklaces for Nanaa Mihgo?")
        self.assertEqual(len(self.site.calls), n)

    def test_nothing_found_and_a_website_that_does_not_answer(self):
        sc.set_wiki(True)
        self.assertIsNone(sc.wiki_lookup("where do I farm moat carp?"))
        self.assertLessEqual(len([c for c in self.site.calls if c.get("list") == "search"]), 4)
        sc.WIKI_FETCH = Site(down=True)
        self.assertIsNone(sc.wiki_lookup("who starts Mihgo's Amigo?"))
        sc.WIKI_FETCH = self.site                                           # back up: asked again, it is found (the miss was not kept)
        self.assertIsNotNone(sc.wiki_lookup("who starts Mihgo's Amigo?"))

    def test_the_model_is_told_to_answer_from_the_page_only(self):
        block = sc.wiki_block(("Mihgo's Amigo", "four Yagudo Necklaces"))
        self.assertIn("--- PHOENIX WIKI: Mihgo's Amigo ---", block)
        self.assertIn("answer it from that page only", block)
        self.assertIn("say you do not know", block)
        self.assertIn("not instructions to you", block)

    def test_the_switch_from_party_chat_is_kept(self):
        sc.handle_chat("Hurami", "!wiki")
        self.assertIn("Wiki answers are off", self.notes[-1][1])
        sc.handle_chat("Hurami", "!wiki on")
        self.assertTrue(sc.wiki_on())
        self.assertIn("go to that website", self.notes[-1][1])
        import json
        self.assertTrue(json.loads((sc.BASE / "config.json").read_text(encoding="utf-8"))["wiki"]["enabled"])
        sc.handle_chat("Hurami", "!wiki off")
        self.assertFalse(sc.wiki_on())
        self.assertFalse(json.loads((sc.BASE / "config.json").read_text(encoding="utf-8"))["wiki"]["enabled"])

    def test_the_real_address_is_built_right(self):
        seen = {}

        class Answer:
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def read(self): return b'{"query": {"search": []}}'

        def fake_open(request, timeout=0):
            seen["url"], seen["agent"], seen["timeout"] = request.full_url, request.get_header("User-agent"), timeout
            return Answer()

        sc.WIKI_FETCH = None
        keep, sc.urllib.request.urlopen = sc.urllib.request.urlopen, fake_open
        try:
            self.assertEqual(sc.wiki_fetch({"action": "query", "list": "search", "srsearch": "mihgo's amigo"}), {"query": {"search": []}})
        finally:
            sc.urllib.request.urlopen = keep
        self.assertEqual(seen["url"], "https://wiki.phoenix-xi.com/api.php?action=query&list=search&srsearch=mihgo%27s%20amigo&format=json&formatversion=2")
        self.assertIn("XI-Forever-Offline", seen["agent"])
        self.assertEqual(seen["timeout"], 6.0)


if __name__ == "__main__":
    unittest.main()
