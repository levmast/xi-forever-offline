import test from "node:test";
import assert from "node:assert/strict";
import { Mixer } from "../app/audio.js";

globalThis.requestAnimationFrame = callback => setTimeout(() => callback(performance.now()), 4);
globalThis.cancelAnimationFrame = clearTimeout;
const delay = ms => new Promise(resolve => setTimeout(resolve, ms));
const audio = () => ({ currentTime: 0, duration: 20, volume: 0, paused: true, disposed: 0,
  play() { this.paused = false; return Promise.resolve(); },
  pause() { this.paused = true; },
  removeAttribute() { this.disposed++; }, load() {} });
const target = (key, options = {}) => ({ key, id: key, channel: "battle",
  loop: true, ownership: "custom", position: 0, ...options });

function setup(open) {
  const calls = [];
  const mixer = new Mixer({
    changed(t) { calls.push(["changed", t?.key]); },
    error(t, error) { calls.push(["error", t.key, error]); },
    failed(t) { calls.push(["failed", t.key]); },
    ended(t) { calls.push(["ended", t.key]); }
  }, open);
  return { calls, mixer };
}

test("crossfade overlaps decks, preserves compatible position and then releases the old deck", async () => {
  const { mixer } = setup(async () => audio());
  const a = target("solo", { match: "shared" });
  const b = target("party", { match: "shared" });
  const catalog = { solo: true, party: true };
  await mixer.reconcile([a], catalog, 0);
  const prior = mixer.live.audio;
  prior.currentTime = 27;
  await mixer.reconcile([b], catalog, 0.045);
  assert.equal(mixer.live.audio.currentTime, 7);
  assert.equal(mixer.outgoing.audio, prior);
  assert.equal(prior.paused, false);
  await delay(100);
  assert.equal(mixer.outgoing, null);
  assert.equal(prior.disposed, 1);
  assert.equal(mixer.live.audio.volume, 1);
  mixer.stop();
});

test("a frame timestamp preceding fade start cannot set an invalid media volume", async () => {
  const original = globalThis.requestAnimationFrame;
  let captured;
  const tracks = [];
  globalThis.requestAnimationFrame = callback => { captured = callback; return 0; };
  const { mixer } = setup(async () => {
    const media = audio();
    tracks.push(media);
    return media;
  });
  try {
    await mixer.reconcile([target("solo")], { solo: true }, 0);
    await mixer.reconcile([target("party")], { party: true }, 0.5);
    captured(performance.now() - 100);
    assert.deepEqual(tracks.map(track => track.volume), [1, 0]);
    captured(performance.now() + 1000);
    assert.equal(mixer.outgoing, null);
  } finally {
    mixer.stop();
    globalThis.requestAnimationFrame = original;
  }
});

test("missing and corrupt custom candidates recover to Vanilla", async () => {
  const { mixer, calls } = setup(async ({ key }) => {
    if (key === "bad") throw new Error("decode error");
    return audio();
  });
  const vanilla = target("native", { ownership: "native" });
  await mixer.reconcile([target("missing"), target("bad"), vanilla], { bad: true, native: true }, 0);
  assert.deepEqual(calls.map(call => call.slice(0, 2)),
    [["error", "missing"], ["error", "bad"], ["changed", "native"]]);
  mixer.stop();
});

test("a decode fallback to a live deck settles without reopening it", async () => {
  const { mixer } = setup(async ({ key }) => {
    if (key === "bad") throw new Error("decode error");
    return audio();
  });
  let settled;
  mixer.events.settled = target => { settled = target.key; };
  const reference = target("native", { ownership: "native" });
  await mixer.reconcile([reference], { native: true }, 0);
  const live = mixer.live.audio;
  await mixer.reconcile([target("bad"), reference], { bad: true, native: true }, 0);
  assert.equal(settled, "native");
  assert.equal(mixer.live.audio, live);
  mixer.stop();
});

test("same intent and a rename preserve the playing instance across rapid events", async () => {
  const { mixer } = setup(async () => audio());
  const solo = target("solo");
  await mixer.reconcile([solo], { solo: "A.mp3" }, 0);
  const playing = mixer.live.audio;
  await mixer.reconcile([solo], { solo: "改名.mp3" }, 0);
  assert.equal(mixer.live.audio, playing);
  mixer.stop();
  assert.equal(playing.disposed, 1);
});

test("a stale load cannot replace a newer choice or resurrect audio after shutdown", async () => {
  const stale = audio();
  let resolve;
  const { mixer } = setup(({ key }) => key === "slow" ?
    new Promise(done => { resolve = done; }) : Promise.resolve(audio()));
  const pending = mixer.reconcile([target("slow")], { slow: true }, 0);
  await mixer.reconcile([target("new")], { new: true }, 0);
  mixer.stop();
  resolve(stale);
  await pending;
  assert.equal(stale.disposed, 1);
  assert.equal(mixer.live, null);
});

test("runtime failures release the live deck and signal fallback", async () => {
  const { mixer, calls } = setup(async () => audio());
  await mixer.reconcile([target("solo")], { solo: true }, 0);
  const live = mixer.live.audio;
  live.onerror();
  assert.deepEqual(calls.at(-1), ["failed", "solo"]);
  assert.equal(mixer.live, null);
  assert.equal(live.disposed, 1);
});

test("non-matched transitions use explicit saved position and channel gain", async () => {
  const { mixer } = setup(async () => audio());
  await mixer.reconcile([target("solo")], { solo: true }, 0);
  mixer.live.audio.currentTime = 13;
  const album = target("album", { loop: false, channel: "album", position: 4 });
  mixer.setVolume({ album: 0.37 });
  await mixer.reconcile([album], { album: true }, 0);
  assert.equal(mixer.live.audio.currentTime, 4);
  assert.equal(mixer.live.audio.volume, 0.37);
  mixer.stop();
});
