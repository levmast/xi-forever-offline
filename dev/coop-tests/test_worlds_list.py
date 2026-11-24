"""Tests for the list of open worlds a launcher shows without being given a link (launcher_coop.py, 2026-11-23):
worlds.json (the kit's own and the copy read from the website), the official world first, and the few words about
each world. No database and no network. Run: python test_worlds_list.py"""
import json, os, shutil, sys, tempfile, time, unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import launcher_coop as co

PIN = "SHA256:" + "A" * 43


def link(address="93.184.216.34", port=54100, name="The Hub"):
    return co.make_link(address, port, PIN, name)


def listing(*worlds):
    return json.dumps({"version": 1, "worlds": list(worlds)})


class Net:
    """The stand-in website: what it answers, and what it was asked."""

    def __init__(self, text):
        self.text, self.asked = text, []

    def __call__(self, url, timeout=0):
        self.asked.append(url)
        if isinstance(self.text, Exception):
            raise self.text
        return self.text.encode("utf-8")


class WorldsList(unittest.TestCase):
    def setUp(self):
        self.kit = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.kit, ignore_errors=True)

    def test_the_official_world_comes_first_and_what_is_no_world_is_left_out(self):
        hub, other, third = link(), link("93.184.216.99", 54100, "Kupo Land"), link("93.184.216.77", 54111, "Third")
        found = co.read_worlds(listing(
            {"name": "Kupo Land", "link": other, "about": "A friendly\n world.\x07  " + "x" * 300},
            {"name": "Broken", "link": "XIFO2-not-a-link"},
            {"name": "An invite", "link": co.make_invite("93.184.216.34", 54100, "ab" * 16, "Friends")},
            {"name": "No link"}, "not an entry", None,
            {"name": "The Hub", "official": True, "link": " " + hub + "\n", "about": "The official world."},
            {"name": "The Hub again", "official": True, "link": hub},
            {"link": third, "official": "yes"}))
        self.assertEqual([(w["name"], w["official"]) for w in found], [("The Hub", True), ("Kupo Land", False), ("Third", False)])
        self.assertEqual((found[0]["link"], found[0]["about"]), (hub, "The official world."))
        self.assertEqual((found[0]["invite"]["address"], found[0]["invite"]["port"], found[0]["invite"]["open"]), ("93.184.216.34", 54100, True))
        self.assertEqual(len(found[1]["about"]), 160)
        self.assertTrue(found[1]["about"].startswith("A friendly world. xxx"), found[1]["about"][:30])
        for broken in ("", "{", "[]", "{}", '{"worlds": 5}', '{"worlds": {"a": 1}}', None):
            self.assertEqual(co.read_worlds(broken), [], broken)
        many = listing(*[{"link": link("93.184.216.34", 20000 + n, f"W{n}")} for n in range(co.WORLDS_MOST + 5)])
        self.assertEqual(len(co.read_worlds(many)), co.WORLDS_MOST)

    def test_the_kits_own_list_until_the_website_has_been_read(self):
        self.assertEqual(co.listed_worlds(self.kit), [])
        with open(os.path.join(self.kit, co.WORLDS_FILE), "w", encoding="utf-8") as handle:
            handle.write(listing({"name": "The Hub", "official": True, "link": link()}))
        self.assertEqual([w["name"] for w in co.listed_worlds(self.kit)], ["The Hub"])
        os.makedirs(os.path.join(self.kit, "coop"))
        moved = link("93.184.216.200")
        with open(co._worlds_path(self.kit), "w", encoding="utf-8") as handle:
            handle.write(listing({"name": "The Hub", "official": True, "link": moved}))
        self.assertEqual(co.listed_worlds(self.kit)[0]["link"], moved, "the list read from the website counts first")
        with open(co._worlds_path(self.kit), "w", encoding="utf-8") as handle:
            handle.write("{ torn")
        self.assertEqual(co.listed_worlds(self.kit)[0]["link"], link(), "a copy that cannot be read: the kit's own list")

    def test_the_website_is_read_when_the_copy_here_is_old(self):
        text = listing({"name": "The Hub", "official": True, "link": link()})
        net = Net(text)
        self.assertTrue(co.refresh_worlds(self.kit, fetch=net))
        self.assertEqual(net.asked, [co.WORLDS_URL])
        self.assertEqual([w["name"] for w in co.listed_worlds(self.kit)], ["The Hub"])
        self.assertFalse(co.refresh_worlds(self.kit, fetch=net), "a fresh copy is not asked for again")
        self.assertEqual(len(net.asked), 1)
        later = time.time() + co.WORLDS_FRESH_SECONDS + 1
        moved = listing({"name": "The Hub", "official": True, "link": link("93.184.216.200")})
        self.assertTrue(co.refresh_worlds(self.kit, fetch=Net(moved), now=later))
        self.assertEqual(co.listed_worlds(self.kit)[0]["invite"]["address"], "93.184.216.200")
        for bad in (OSError("no internet"), "{ torn", listing(), listing({"name": "x", "link": "nothing"}), "x" * 200001):
            net = Net(bad)
            self.assertFalse(co.refresh_worlds(self.kit, fetch=net, now=later + 10000), repr(bad)[:40])
            self.assertEqual(len(net.asked), 1)
            self.assertEqual(co.listed_worlds(self.kit)[0]["invite"]["address"], "93.184.216.200", "what is here stays")
        self.assertEqual(sorted(os.listdir(os.path.join(self.kit, "coop"))), [co.WORLDS_FILE], "no half-written file is left")

    def test_a_few_words_about_a_world(self):
        world = co.read_worlds(listing({"name": "The Hub", "official": True, "link": link()}))[0]
        real, asked = co.hello, []
        try:
            co.hello = lambda invite, post=None, timeout=12: (asked.append((invite["address"], timeout)), {"guests": 3, "max_guests": 30})[1]
            self.assertEqual(co.world_state(world), "online: 3 of 30 visitors")
            self.assertEqual(asked, [("93.184.216.34", 6)])
            co.hello = lambda invite, post=None, timeout=12: {"guests": 0, "max_guests": 12, "password": True}
            self.assertEqual(co.world_state(world), "online: 0 of 12 visitors, has a password")

            def nobody(invite, post=None, timeout=12):
                raise co.CoopError("No answer.")

            co.hello = nobody
            self.assertEqual(co.world_state(world), "no answer right now")
            co.hello = lambda invite, post=None, timeout=12: {"guests": "many"}
            self.assertEqual(co.world_state(world), "no answer right now")
        finally:
            co.hello = real


if __name__ == "__main__":
    unittest.main(verbosity=1)
