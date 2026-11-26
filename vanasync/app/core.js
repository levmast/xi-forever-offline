export const ARRANGEMENTS = ["solo", "party", "alliance"];
export const SLOTS = ["solo", "party", "alliance", "nativeSolo", "nativeParty",
  "nativeAlliance", "exploration", "cutscene", "ambience"];
export const KEYS = { collapse: "F2", album: "F3", emergency: "F8" };
const idPattern = /^[a-f0-9]{32}$/;
const validId = value => typeof value === "string" && idPattern.test(value);
const number = (value, fallback, min, max) => typeof value === "number" && Number.isFinite(value)
  ? Math.max(min, Math.min(max, value)) : fallback;

export function settings(raw = {}) {
  raw = raw && typeof raw === "object" ? raw : {};
  const album = Array.isArray(raw.album) ? raw.album.filter(validId).slice(0, 200) : [];
  const cursor = Math.floor(number(raw.cursor, 0, 0, Math.max(0, album.length - 1)));
  const usedKeys = new Set();
  const keys = {};
  const slots = {};
  for (const slot of SLOTS) slots[slot] = validId(raw.slots?.[slot]) ? raw.slots[slot] : "";
  for (const action of Object.keys(KEYS)) {
    const value = raw.keys?.[action] ?? KEYS[action];
    if (/^(?:F[2-9]|[A-Z])$/.test(value) && !usedKeys.has(value)) {
      keys[action] = value;
      usedKeys.add(value);
    } else {
      keys[action] = "";
    }
  }
  return {
    mode: ["Vanilla", "Resonance", "Off"].includes(raw.mode) ? raw.mode : "Vanilla",
    override: ARRANGEMENTS.includes(raw.override) ? raw.override : "auto",
    grace: number(raw.grace, 5, 0, 30), fade: number(raw.fade, 0.8, 0, 4),
    sync: raw.sync === true, slots, album, cursor,
    position: number(raw.position, 0, 0, 86400), albumOn: raw.albumOn === true,
    paused: raw.paused === true, repeat: raw.repeat === true,
    interrupt: raw.interrupt === true, locked: raw.locked === true,
    collapsed: raw.collapsed === true, transparency: number(raw.transparency, 1, 0.45, 1),
    scale: number(raw.scale, 1, 0.75, 1.4),
    x: number(raw.x, 0, -10000, 10000), y: number(raw.y, 0, -10000, 10000),
    volume: Object.fromEntries(["battle", "exploration", "album", "ambience"]
      .map(key => [key, number(raw.volume?.[key], key === "ambience" ? 0.4 : 0.8, 0, 1)])),
    keys
  };
}

export function arrangement(prefs, game) {
  if (prefs.override !== "auto") return prefs.override;
  if (game.alliance || game.members > 6) return "alliance";
  return game.members > 1 ? "party" : "solo";
}

export class CombatState {
  game = { engaged: false, members: 1, alliance: false, zone: 1, cutscene: false };
  endedAt = null;

  update(snapshot, now) {
    if (this.game.engaged && !snapshot.engaged) this.endedAt = now;
    if (snapshot.engaged) this.endedAt = null;
    this.game = { ...snapshot };
  }

  phase(now, grace) {
    if (this.game.engaged) return "combat";
    if (this.endedAt !== null && now - this.endedAt < grace * 1000) return "grace";
    return "exploration";
  }
}

export function select(prefs, state, now, emergency = false) {
  const phase = state.phase(now, prefs.grace);
  const battle = phase !== "exploration";
  const kind = arrangement(prefs, state.game);
  const nativeBattle = "native" + kind[0].toUpperCase() + kind.slice(1);
  const native = battle ? nativeBattle : "exploration";
  const stack = [];
  const add = (key, id, channel, ownership, match = null, loop = true, position = 0) => {
    stack.push({ key, id, channel, ownership, match, loop, position });
  };
  if (state.game.cutscene) {
    add("cutscene", prefs.slots.cutscene, "exploration", "native");
  } else if (emergency) {
    add(native, prefs.slots[native], battle ? "battle" : "exploration", "native");
  } else if (prefs.albumOn && !(battle && prefs.interrupt && !prefs.paused)) {
    if (!prefs.paused && prefs.album.length) {
      add("album/" + prefs.cursor, prefs.album[prefs.cursor], "album", "custom",
        null, false, prefs.position);
      add(native, prefs.slots[native], battle ? "battle" : "exploration", "native");
    } else if (!prefs.paused) {
      add("album/empty", "", "album", "custom", null, false);
      add(native, prefs.slots[native], battle ? "battle" : "exploration", "native");
    }
  } else if (prefs.mode !== "Off") {
    const match = battle && prefs.sync ? "battle-shared-timeline" : null;
    if (battle && prefs.mode === "Resonance") add(kind, prefs.slots[kind], "battle", "custom", match);
    add(native, prefs.slots[native], battle ? "battle" : "exploration", "native", match);
  }
  const ambience = !emergency && !state.game.cutscene && prefs.slots.ambience
    ? { key: "ambience", id: prefs.slots.ambience, channel: "ambience", loop: true, position: 0 }
    : null;
  return { phase, kind, stack, ambience };
}

export function nextAlbum(prefs, step, automatic = false) {
  if (!prefs.album.length) return;
  const next = prefs.cursor + step;
  if (automatic && next >= prefs.album.length && !prefs.repeat) {
    prefs.paused = true;
    prefs.cursor = 0;
  } else {
    prefs.cursor = (next + prefs.album.length) % prefs.album.length;
  }
  prefs.position = 0;
}

export function trackTitle(filename) {
  return filename.slice(0, filename.lastIndexOf("."));
}
