import test from "node:test";
import assert from "node:assert/strict";
import { settings, CombatState, arrangement, select, trackTitle, nextAlbum } from "../app/core.js";

const id = "1".repeat(32);
const combat = (state, now, fields) => state.update({ ...state.game, ...fields }, now);

test("automatic group boundaries and manual overrides", () => {
  const prefs = settings();
  for (const [members, alliance, expected] of [[1, false, "solo"], [2, false, "party"],
    [6, false, "party"], [7, false, "alliance"], [2, true, "alliance"]]) {
    assert.equal(arrangement(prefs, { members, alliance }), expected);
    for (const override of ["solo", "party", "alliance"])
      assert.equal(arrangement({ ...prefs, override }, { members, alliance }), override);
  }
});

test("grace stays armed across zone and composition updates, and cancels on re-entry", () => {
  const state = new CombatState();
  const prefs = settings({ mode: "Resonance" });
  combat(state, 10, { engaged: true });
  combat(state, 100, { engaged: false });
  combat(state, 200, { members: 3, zone: 2 });
  assert.equal(select(prefs, state, 5099).phase, "grace");
  assert.equal(select(prefs, state, 5099).stack[0].key, "party");
  assert.equal(select(prefs, state, 5100).stack[0].key, "exploration");
  combat(state, 500, { engaged: true });
  assert.equal(select(prefs, state, 9000).phase, "combat");
  combat(state, 9100, { engaged: false });
  assert.equal(select({ ...prefs, grace: 0 }, state, 9100).phase, "exploration");
});

test("soundtrack switching and emergency fallback order", () => {
  const prefs = settings({ mode: "Resonance", sync: true, slots: { solo: id, ambience: id } });
  const state = new CombatState();
  combat(state, 1, { engaged: true });
  const plan = select(prefs, state, 1);
  assert.deepEqual(plan.stack.map(t => t.key), ["solo", "nativeSolo"]);
  assert.equal(plan.stack[0].match, plan.stack[1].match);
  assert.equal(select({ ...prefs, mode: "Vanilla" }, state, 1).stack[0].key, "nativeSolo");
  assert.deepEqual(select({ ...prefs, mode: "Off" }, state, 1).stack, []);
  const emergency = select({ ...prefs, mode: "Off" }, state, 1, true);
  assert.equal(emergency.stack[0].key, "nativeSolo");
  assert.equal(emergency.ambience, null);
});

test("album survives zoning, yields to cutscene or optional battle, resumes saved position", () => {
  const prefs = settings({ albumOn: true, album: [id], position: 17.5, mode: "Resonance" });
  const state = new CombatState();
  combat(state, 1, { zone: 3, engaged: true });
  assert.equal(select(prefs, state, 1).stack[0].position, 17.5);
  assert.equal(select({ ...prefs, interrupt: true }, state, 1).stack[0].key, "solo");
  combat(state, 2, { cutscene: true });
  assert.equal(select(prefs, state, 2).stack[0].key, "cutscene");
  combat(state, 3, { cutscene: false, engaged: false });
  assert.equal(select(prefs, state, 3).stack[0].key, "album/0");
  assert.equal(select({ ...prefs, albumOn: false }, state, 3).stack[0].key, "solo");
  assert.deepEqual(select({ ...prefs, paused: true }, state, 3).stack, []);
});

test("album track order, wrap, and end-of-album pause", () => {
  const prefs = settings({ album: [id, "2".repeat(32)], position: 10 });
  nextAlbum(prefs, 1, true);
  assert.deepEqual([prefs.cursor, prefs.position, prefs.paused], [1, 0, false]);
  nextAlbum(prefs, 1, true);
  assert.deepEqual([prefs.cursor, prefs.paused], [0, true]);
  prefs.repeat = true;
  prefs.paused = false;
  nextAlbum(prefs, -1);
  nextAlbum(prefs, 1, true);
  assert.deepEqual([prefs.cursor, prefs.paused], [0, false]);
});

test("settings round trip sanitizes invalid values and names retain Unicode", () => {
  const prefs = settings({ grace: -3, slots: { party: id, solo: "../file" },
    keys: { album: "F2" }, transparency: 10, volume: { album: 0 } });
  assert.equal(prefs.grace, 0);
  assert.equal(prefs.slots.party, id);
  assert.equal(prefs.slots.solo, "");
  assert.equal(prefs.keys.album, "");
  assert.equal(prefs.transparency, 1);
  assert.equal(prefs.volume.album, 0);
  assert.deepEqual(settings(JSON.parse(JSON.stringify(prefs))), prefs);
  assert.equal(trackTitle("戦闘・Party (Mix).Final.WAV"), "戦闘・Party (Mix).Final");
});

test("copy numbers at the end of a file name are not shown", () => {
  for (const [file, title] of [
    ["Choose to Fight (Special Battle Theme XIFO Exclusive).mp3", "Choose to Fight (Special Battle Theme XIFO Exclusive)"],
    ["Choose to Fight (Special Battle Theme XIFO Exclusive) (1).mp3", "Choose to Fight (Special Battle Theme XIFO Exclusive)"],
    ["Against the Odds (Solo Battle Theme) (1).mp3", "Against the Odds (Solo Battle Theme)"],
    ["Track (2) (1).mp3", "Track"],
    ["Beyond the Veil (Party Battle Theme).mp3", "Beyond the Veil (Party Battle Theme)"],
    ["Night Song (Remix).ogg", "Night Song (Remix)"], ["Encore (Live) (3).wav", "Encore (Live)"],
    ["Symphony No. 5.mp3", "Symphony No. 5"], ["Level 99 Blues.mp3", "Level 99 Blues"],
    ["Opus (1999).mp3", "Opus (1999)"], ["07 (2) Road.mp3", "07 (2) Road"], ["Take(1).mp3", "Take(1)"],
    ["(1).mp3", "(1)"], ["noextension", "noextension"]])
    assert.equal(trackTitle(file), title);
});

test("100,000 simulator updates fit a 2 second regression budget", () => {
  const state = new CombatState();
  const prefs = settings({ mode: "Resonance" });
  const start = performance.now();
  for (let i = 0; i < 100000; i++) {
    combat(state, i, { engaged: i % 3 === 0, members: 1 + i % 18 });
    select(prefs, state, i);
  }
  const elapsed = performance.now() - start;
  assert.ok(elapsed < 2000, String(elapsed));
});
