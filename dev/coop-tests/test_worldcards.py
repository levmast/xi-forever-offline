"""OPEN WORLDS cards and the worlds list (2026-11-23): a world's description and banner come from the world itself,
open worlds list themselves on the hub (dev/worldlist), the page merges the lists, and the character comes home by
itself when the game closes. No database needed. Run: python3 test_worldcards.py"""
import hashlib
import io
import json
import os
import shutil
import sys
import tempfile
import unittest

KIT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, KIT)
sys.path.insert(0, os.path.join(KIT, "dev", "worldlist"))
import launcher_coop as co          # noqa: E402
import worldlist_service as wl      # noqa: E402

PIN = "SHA256:" + "A" * 43
PIN2 = "SHA256:" + "B" * 43


def link(address="66.179.255.236", port=54100, pin=PIN, name="The Hub"):
    return co.make_link(address, port, pin, name)


class WorldList(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.checked = []

        def check(address, port, pin):
            self.checked.append((address, port, pin))
            return address != "8.8.4.4"          # this one "does not answer"
        self.list = wl.WorldList(self.tmp, check=check)

    def test_announce_and_list(self):
        self.assertEqual(self.list.announce(link())["ok"], True)
        rows = self.list.listing()["worlds"]
        self.assertEqual([r["link"] for r in rows], [link()])
        self.assertEqual(wl.read_link(link())["pin"], PIN)                 # the service reads the launcher's links

    def test_refusals(self):
        self.assertFalse(self.list.announce("hello")["ok"])
        private = self.list.announce(link("192.168.1.20"))
        self.assertFalse(private["ok"])
        self.assertIn("public internet address", private["error"])
        self.assertFalse(self.list.announce(link("100.85.61.16"))["ok"])  # Tailscale
        dead = self.list.announce(link("8.8.4.4"))
        self.assertFalse(dead["ok"])
        self.assertIn("did not answer", dead["error"])
        self.assertEqual(self.list.listing()["worlds"], [])

    def test_stale_worlds_drop_off(self):
        self.list.announce(link(), now=1000)
        self.assertEqual(len(self.list.listing(now=1000 + wl.FRESH - 1)["worlds"]), 1)
        self.assertEqual(len(self.list.listing(now=1000 + wl.FRESH + 1)["worlds"]), 0)

    def test_one_address_has_a_limit(self):
        for i in range(wl.PER_ADDRESS):
            self.assertTrue(self.list.announce(link(port=54100 + i, pin="SHA256:" + chr(65 + i) * 43))["ok"])
        self.assertFalse(self.list.announce(link(port=55000, pin="SHA256:" + "Z" * 43))["ok"])

    def test_owner_hides_a_world(self):
        self.list.announce(link())
        self.assertFalse(self.list.hide("wrong", PIN)["ok"])
        self.assertTrue(self.list.hide(self.list.owner, PIN)["ok"])
        self.assertEqual(self.list.listing()["worlds"], [])
        self.assertFalse(self.list.announce(link())["ok"])
        again = wl.WorldList(self.tmp, check=lambda *a: True)           # kept across a restart
        self.assertFalse(again.announce(link())["ok"])
        self.assertTrue(again.hide(again.owner, PIN, on=False)["ok"])
        self.assertTrue(again.announce(link())["ok"])

    def test_key_fingerprint_matches_the_launcher(self):
        pem = open(os.path.join(KIT, "dev", "coop-tests", "fixtures", "login.cert")).read() if os.path.exists(
            os.path.join(KIT, "dev", "coop-tests", "fixtures", "login.cert")) else None
        if pem is None:
            import base64, re, subprocess
            folder = tempfile.mkdtemp()
            subprocess.run(["openssl", "req", "-x509", "-newkey", "ec", "-pkeyopt", "ec_paramgen_curve:prime256v1", "-nodes",
                            "-days", "1", "-subj", "/CN=t", "-keyout", os.path.join(folder, "k"), "-out", os.path.join(folder, "c")],
                           capture_output=True, check=True)
            pem = open(os.path.join(folder, "c")).read()
        import base64, re
        der = base64.b64decode("".join(re.search(r"-----BEGIN CERTIFICATE-----(.+?)-----END", pem, re.S).group(1).split()))
        self.assertEqual(wl.key_fingerprint(der), co.certificate_fingerprint(pem))


class Banners(unittest.TestCase):
    def setUp(self):
        self.kit = tempfile.mkdtemp()
        from PIL import Image
        self.picture = os.path.join(self.kit, "pic.jpg")
        Image.new("RGB", (1920, 900), (40, 80, 160)).save(self.picture)

    def test_banner_is_made_640_by_160(self):
        from PIL import Image
        path = co.set_banner(self.kit, self.picture)
        with Image.open(path) as image:
            self.assertEqual((image.format, image.size), ("PNG", co.BANNER_SIZE))
        data = co.banner_bytes(self.kit)
        self.assertTrue(0 < len(data) <= co.BANNER_MOST)
        self.assertEqual(co.banner_hash(self.kit), hashlib.sha256(data).hexdigest())
        co.set_banner(self.kit, None)
        self.assertEqual(co.banner_hash(self.kit), "")

    def test_the_world_serves_it_and_the_visitor_checks_it(self):
        co.set_banner(self.kit, self.picture)
        settings = co.load_settings(self.kit)
        settings.update({"open": True, "hosting": True, "about": "Era rates\x07 and \n friends"})
        host = co.Host({}, self.kit, settings, log=lambda line: None, connect=lambda: None)

        def post(address, port, key_header, body, timeout):
            return host.handle(key_header, body, "1.2.3.4", secure=True)
        invite = co.read_link(link())
        sha = co.banner_hash(self.kit)
        visitor = tempfile.mkdtemp()
        got = co.fetch_banner(visitor, invite, sha, post=post)
        self.assertTrue(got and os.path.exists(got))
        self.assertEqual(open(got, "rb").read(), co.banner_bytes(self.kit))
        # a world that names one picture and sends another: nothing is kept
        self.assertIsNone(co.fetch_banner(tempfile.mkdtemp(), invite, "0" * 64, post=post))
        self.assertEqual(co.clean_about(settings["about"]), "Era rates and friends")
        settings["open"] = False                         # a world that is not open shows no banner
        self.assertIsNone(co.fetch_banner(tempfile.mkdtemp(), invite, sha, post=post))


class Lists(unittest.TestCase):
    def test_official_first_then_listed_ones_without_doubles(self):
        kit = tempfile.mkdtemp()
        os.makedirs(os.path.join(kit, "coop"))
        with open(os.path.join(kit, "worlds.json"), "w") as f:
            json.dump({"worlds": [{"name": "The Hub", "official": True, "about": "Official", "link": link()}]}, f)
        other = link("45.33.10.7", 54100, PIN2, "Bob's 10x world")
        with open(os.path.join(kit, "coop", co.DIRECTORY_FILE), "w") as f:
            json.dump({"worlds": [{"link": link()}, {"link": other}, {"link": "junk"}]}, f)
        rows = co.all_worlds(kit)
        self.assertEqual([(w["name"], w["official"]) for w in rows], [("The Hub", True), ("Bob's 10x world", False)])

    def test_refresh_directory_keeps_only_links(self):
        kit = tempfile.mkdtemp()
        answer = {"worlds": [{"link": link(), "seen": 5, "evil": "<script>"}]}
        self.assertTrue(co.refresh_directory(kit, fetch=lambda url, body: json.dumps(answer)))
        kept = json.load(open(os.path.join(kit, "coop", co.DIRECTORY_FILE)))
        self.assertEqual(kept, {"worlds": [{"link": link()}]})

    def test_a_world_that_does_not_answer(self):
        world = co.read_worlds(json.dumps({"worlds": [{"link": link(), "about": "x"}]}))[0]

        def post(*a):
            raise OSError("down")
        card = co.world_card(tempfile.mkdtemp(), world, post=post)
        self.assertEqual((card["up"], card["state"], card["banner"]), (False, "no answer right now", None))


class Friends(unittest.TestCase):
    def test_a_friends_world_is_kept_for_one_click(self):
        kit = tempfile.mkdtemp()
        code = co.make_invite("100.85.61.16", 54100, "ab" * 16, "DaBeej's world")
        co.remember_friend(kit, code, "DaBeej's world", now=100)
        co.remember_friend(kit, link(), "The Hub")                    # open worlds are not friends' worlds
        rows = co.friends(kit)
        self.assertEqual([(r["name"], r["invite"]["address"]) for r in rows], [("DaBeej's world", "100.85.61.16")])
        newer = co.make_invite("100.85.61.16", 54100, "cd" * 16, "DaBeej's world")    # a new code for the same PC replaces it
        co.remember_friend(kit, newer, "DaBeej's world", now=200)
        self.assertEqual([r["code"] for r in co.friends(kit)], [newer])
        for i in range(co.FRIENDS_MOST + 3):
            co.remember_friend(kit, co.make_invite(f"192.168.1.{i + 2}", 54100, "ef" * 16, f"W{i}"), f"W{i}")
        self.assertEqual(len(co.friends(kit)), co.FRIENDS_MOST)
        co.forget_friend(kit, co.friends(kit)[0]["code"])
        self.assertEqual(len(co.friends(kit)), co.FRIENDS_MOST - 1)


class ComeHome(unittest.TestCase):
    def test_waits_while_the_world_still_sees_it_logged_in(self):
        calls = []

        def fake(cfg, kit, charid, force=False, log=print, post=None, connect=None):
            calls.append(charid)
            if len(calls) < 3:
                raise co.Refused("still in the game", "online")
            return {"name": "Hurami"}
        real, co.come_home = co.come_home, fake
        try:
            slept = []
            self.assertEqual(co.come_home_after_game({}, "", 5, sleep=slept.append, wait=8), {"name": "Hurami"})
            self.assertEqual((len(calls), slept), (3, [8, 8]))
            calls.clear()
            co.come_home = lambda *a, **k: (_ for _ in ()).throw(co.Refused("left", "holdings", {"holdings": {"auctions": 1}}))
            self.assertEqual(co.come_home_after_game({}, "", 5, sleep=lambda s: None).code, "holdings")
        finally:
            co.come_home = real


if __name__ == "__main__":
    unittest.main(verbosity=2)
