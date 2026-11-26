import { SLOTS, KEYS, settings, CombatState, select, nextAlbum, trackTitle } from "/core.js";
import { Mixer } from "/audio.js";

const $ = id => document.getElementById(id);
const storageKey = "vanasync.settings.v1";
const game = new CombatState();
const slotLabels = {
  solo: "Resonance · Solo", party: "Resonance · Party", alliance: "Resonance · Alliance",
  nativeSolo: "Vanilla reference · Solo", nativeParty: "Vanilla reference · Party",
  nativeAlliance: "Vanilla reference · Alliance", exploration: "Exploration reference",
  cutscene: "Cutscene reference", ambience: "Ambience"
};
const volumeIds = { battle: "battle", exploration: "exploration-volume",
  album: "album", ambience: "ambience" };
const phaseNames = { combat: "Combat", grace: "Post-combat", exploration: "Exploration" };

let prefs;
let catalog = {};
let enabled = false;
let emergency = false;
let pending = false;
let selected = null;
let graceTimer;
let polling = false;
let drag;
let disposed = false;
const journal = [];
const failed = new Set();
let previousPlan = "";
// Live mode: the XI Forever Offline add-on feeds real game state through the host.
const liveLaunch = new URLSearchParams(location.search).has("live");
let live = false;
let livePolling = false;
let lastLive = "";
let lastOwn = null;

let defaults = {};
try {
  const response = await fetch("/api/bootstrap");
  if (!response.ok) throw new Error("catalog unavailable");
  const initial = await response.json();
  defaults = initial.defaults;
  catalog = initial.tracks;
} catch {
  log("Initial catalog could not be read");
}

try {
  const stored = JSON.parse(localStorage.getItem(storageKey));
  prefs = settings({ ...(liveLaunch && !stored ? { mode: "Resonance" } : {}),
    ...stored, slots: { ...defaults, ...stored?.slots } });
} catch {
  prefs = settings({ slots: defaults });
  log("Stored settings could not be read");
}

function log(event, detail) {
  journal.push({ at: new Date().toISOString(), event, ...(detail ? { detail } : {}) });
  if (journal.length > 300) journal.shift();
}

function notice(message) {
  $("notice").textContent = message;
}

function save() {
  try {
    localStorage.setItem(storageKey, JSON.stringify(prefs));
  } catch {
    notice("Settings could not be saved in this browser.");
  }
}

const errors = (target, message) => {
  log("Audio fallback", { target: target.channel, reason: message });
  if (message === "Use Enable audio to allow playback") notice(message);
};

const music = new Mixer({
  loading() { pending = true; renderStatus(); },
  settled(target) {
    pending = false;
    selected = target;
    renderStatus();
  },
  changed(target) {
    pending = false;
    selected = target;
    log("Music changed", { source: target?.ownership ?? "silence", channel: target?.channel ?? "" });
    renderStatus();
  },
  ended(target) {
    if (target.channel !== "album") return;
    nextAlbum(prefs, 1, true);
    apply(false, prefs.album.length === 1);
  },
  error: errors,
  failed(target) {
    failed.add(target.key + ":" + target.id);
    reconcile();
  }
});

const ambience = new Mixer({ changed() {}, ended() {}, error: errors });

function checkpoint() {
  if (!prefs.albumOn || prefs.paused || selected?.channel !== "album"
      || selected.key !== "album/" + prefs.cursor || selected.id !== prefs.album[prefs.cursor]) return;
  const position = music.position(selected.key);
  if (Number.isFinite(position)) prefs.position = Math.round(position * 1000) / 1000;
}

function reconcile(retry = false) {
  clearTimeout(graceTimer);
  const now = performance.now();
  const plan = select(prefs, game, now, emergency);
  if (plan.phase === "grace") {
    graceTimer = setTimeout(reconcile, Math.max(1, game.endedAt + prefs.grace * 1000 - now));
  }
  music.setVolume(prefs.volume);
  ambience.setVolume(prefs.volume);
  const planKey = JSON.stringify(plan.stack.map(target => [target.key, target.id]));
  if (retry || planKey !== previousPlan) failed.clear();
  previousPlan = planKey;
  if (enabled) {
    // In live mode the game itself plays "native" music, so only VanaSync's own tracks play here.
    const stack = plan.stack.filter(target => !failed.has(target.key + ":" + target.id)
      && (!live || target.ownership === "custom"));
    const fade = emergency || game.game.cutscene ? 0 : prefs.fade;
    if (game.game.cutscene && selected && selected.key !== "cutscene") music.stop();
    music.reconcile(stack, catalog, fade, retry);
    ambience.reconcile(plan.ambience ? [plan.ambience] : [], catalog, fade, retry);
  }
  renderStatus();
}

function renderStatus() {
  const { phase, kind, stack } = select(prefs, game, performance.now(), emergency);
  $("phase").textContent = game.game.cutscene ? "Cutscene" : phaseNames[phase];
  $("indicator").dataset.phase = game.game.cutscene ? "" : phase;
  $("arrangement").textContent = phase === "exploration" ? "" : kind[0].toUpperCase() + kind.slice(1);
  const filename = selected && catalog[selected.id];
  const title = !enabled ? "Audio disabled" : filename ? trackTitle(filename)
    : pending ? "Loading audio" : "No audio playing";
  if ($("track").textContent !== title) $("track").textContent = title;
  const desired = stack[0];
  let status = live ? "Live · Enable audio to listen" : "Simulator · Enable audio to listen";
  if (enabled && live && !emergency && !pending && selected?.ownership !== "custom"
      && selected?.channel !== "album") {
    status = desired?.ownership === "custom" ? "Live · Custom track unavailable, game music playing"
      : "Live · Game music playing";
  } else if (enabled) {
    if (emergency) status = "Simulated native restoration";
    else if (pending) status = "Changing tracks";
    else if (selected?.channel === "album") status = "RESONANCE OF VANA’DIEL · Album Mode";
    else if (selected?.ownership === "custom") status = "MELODIES OF FOREVER · Battle music";
    else if (desired?.ownership === "custom") status = selected ? "Vanilla reference · Custom track unavailable"
      : "Audio unavailable · Assign a playable track";
    else if (selected) status = "Vanilla reference · Simulator";
    else if (prefs.albumOn && prefs.paused && !game.game.cutscene) status = "Album paused";
    else if (desired) status = "Native audio requested · Assign a simulator reference";
    else status = "Music off";
  }
  $("transport-status").textContent = status;
  $("enable").textContent = enabled ? "Retry audio" : "Enable audio";
}

function owning() {
  return enabled && !emergency && !pending && selected?.ownership === "custom";
}

async function reportOwner() {
  const own = live && owning();
  if (own === lastOwn && !own) return;
  lastOwn = own;
  try {
    await fetch("/api/owner", { method: "POST", headers: { "X-VanaSync": "1",
      "Content-Type": "application/json" }, body: JSON.stringify({ own }) });
  } catch {
    lastOwn = null;
  }
}

async function pollGame() {
  if (livePolling || disposed) return;
  livePolling = true;
  try {
    const response = await fetch("/api/game");
    const data = response.ok ? await response.json() : { live: false };
    if (data.live !== live) {
      live = data.live === true;
      log(live ? "Game connected" : "Game disconnected");
      document.body.classList.toggle("live", live);
      for (const id of ["engaged", "members", "alliance", "zone", "cutscene"]) $(id).disabled = live;
      if (!live) {
        // Hand music back to the game: no battle, no cutscene.
        game.update({ ...game.game, engaged: false, cutscene: false }, performance.now());
        lastLive = "";
      }
      reconcile();
    }
    if (live && data.state) {
      const key = JSON.stringify(data.state);
      if (key !== lastLive) {
        lastLive = key;
        checkpoint();
        game.update(data.state, performance.now());
        for (const [id, value] of Object.entries(data.state)) {
          if (typeof value === "boolean") $(id).checked = value;
          else $(id).value = value;
        }
        log("Game state changed", { ...game.game });
        reconcile();
      }
    }
  } catch {
    // Host closed; nothing to do until it comes back.
  } finally {
    livePolling = false;
    reportOwner();
  }
}

function apply(capture = true, retry = false) {
  if (capture) checkpoint();
  save();
  renderSettings();
  reconcile(retry);
}

function option(label, value) {
  return new Option(label, value);
}

function renderAssignments() {
  for (const slot of SLOTS) {
    const field = $("slot-" + slot);
    const current = prefs.slots[slot];
    const entries = [option("Unassigned", ""), ...Object.entries(catalog).map(([id, filename]) =>
      option(trackTitle(filename), id))];
    if (current && !catalog[current]) entries.push(option("Missing file (assignment retained)", current));
    field.replaceChildren(...entries);
    field.value = current;
  }
}

function renderPlaylist() {
  const list = $("playlist");
  const items = prefs.album.map((id, index) => {
    const item = document.createElement("li");
    const filename = catalog[id];
    item.textContent = filename ? trackTitle(filename) : "Missing file";
    item.setAttribute("aria-current", String(index === prefs.cursor));
    for (const [text, label, delta] of [["↑", "Move earlier", -1], ["↓", "Move later", 1], ["Remove", "Remove", 0]]) {
      const button = document.createElement("button");
      button.type = "button";
      button.textContent = text;
      button.setAttribute("aria-label", label + " track " + (index + 1));
      button.disabled = index + delta < 0 || index + delta >= prefs.album.length;
      button.onclick = () => {
        checkpoint();
        if (!delta) {
          prefs.album.splice(index, 1);
          if (index === prefs.cursor) prefs.position = 0;
          if (index < prefs.cursor || prefs.cursor >= prefs.album.length)
            prefs.cursor = Math.max(0, prefs.cursor - 1);
        } else {
          const next = index + delta;
          [prefs.album[index], prefs.album[next]] = [prefs.album[next], prefs.album[index]];
          if (prefs.cursor === index) prefs.cursor = next;
          else if (prefs.cursor === next) prefs.cursor = index;
        }
        renderPlaylist();
        apply(false);
      };
      item.append(button);
    }
    return item;
  });
  list.replaceChildren(...items);
}

function place() {
  const player = $("player");
  const available = Math.max(280, document.documentElement.clientWidth - 16);
  const scale = Math.min(prefs.scale, available / player.offsetWidth);
  const centered = (document.documentElement.clientWidth - player.offsetWidth) / 2;
  const left = centered - (scale - 1) * player.offsetWidth / 2;
  const right = left + scale * player.offsetWidth;
  const horizontal = Math.max(8 - left, Math.min(available + 8 - right, prefs.x));
  const vertical = Math.max(-player.offsetTop + 8, Math.min(innerHeight - 125, prefs.y));
  player.style.transform = "translate(" + horizontal + "px," + vertical + "px) scale(" + scale + ")";
  player.style.opacity = prefs.transparency;
  return [horizontal, vertical];
}

function renderSettings() {
  for (const id of ["mode", "override", "grace", "fade", "scale", "transparency"])
    $(id).value = prefs[id];
  for (const id of ["locked", "sync", "interrupt", "repeat"]) $(id).checked = prefs[id];
  for (const [channel, id] of Object.entries(volumeIds)) $(id).value = prefs.volume[channel];
  for (const action of Object.keys(KEYS)) $("key-" + action).value = prefs.keys[action];
  $("drag").classList.toggle("locked", prefs.locked);
  $("quick-lock").textContent = prefs.locked ? "Unlock position" : "Lock position";
  $("deck").hidden = prefs.collapsed;
  $("collapse").textContent = prefs.collapsed ? "+" : "−";
  $("collapse").setAttribute("aria-label", prefs.collapsed ? "Expand player" : "Collapse player");
  $("collapse").setAttribute("aria-expanded", String(!prefs.collapsed));
  $("albumOn").textContent = prefs.albumOn ? "Exit Album Mode" : "Enter Album Mode";
  $("albumOn").setAttribute("aria-pressed", String(prefs.albumOn));
  $("pause").textContent = prefs.paused ? "Resume" : "Pause";
  for (const id of ["previous", "pause", "next"]) $(id).disabled = !prefs.albumOn;
  place();
  renderPosition();
  for (const [index, row] of [...$("playlist").children].entries())
    row.setAttribute("aria-current", String(index === prefs.cursor));
}

function renderPosition() {
  const seconds = Math.floor(prefs.position);
  $("position").textContent = Math.floor(seconds / 60) + ":" + String(seconds % 60).padStart(2, "0");
}

async function refreshCatalog() {
  if (polling || disposed) return;
  polling = true;
  try {
    const response = await fetch("/api/tracks");
    if (!response.ok) throw new Error("catalog unavailable");
    const next = await response.json();
    if (JSON.stringify(next) !== JSON.stringify(catalog)) {
      checkpoint();
      catalog = next;
      renderAssignments();
      renderPlaylist();
      reconcile();
    }
  } catch {
    if (Object.keys(catalog).length) {
      checkpoint();
      catalog = {};
      renderAssignments();
      renderPlaylist();
      log("Catalog connection lost");
      reconcile();
    }
  } finally {
    polling = false;
  }
}

async function importTracks(event, album) {
  const field = event.currentTarget;
  const files = [...field.files];
  field.disabled = true;
  let imported = 0;
  let rejected = 0;
  try {
    for (const file of files) {
      if (album && prefs.album.length >= 200) {
        rejected++;
        continue;
      }
      try {
        const response = await fetch("/api/tracks", { method: "POST", body: file,
          headers: { "Content-Type": "application/octet-stream", "X-VanaSync": "1",
            "X-Filename": encodeURIComponent(file.name) } });
        if (!response.ok) throw new Error("Import rejected");
        const { id, filename } = await response.json();
        catalog[id] = filename;
        if (album) prefs.album.push(id);
        imported++;
      } catch {
        rejected++;
      }
    }
    notice(imported + " imported" + (rejected ? " · " + rejected + " failed" : ""));
    log("Import completed", { imported, rejected });
    renderAssignments();
    renderPlaylist();
    apply();
  } finally {
    field.value = "";
    field.disabled = false;
  }
}

function restore() {
  checkpoint();
  save();
  emergency = true;
  enabled = true;
  music.stop();
  ambience.stop();
  log("Emergency restoration requested");
  notice("Using the simulator’s Vanilla references. Enable audio to return to your selection.");
  reconcile();
}

function toggleAlbum() {
  checkpoint();
  prefs.albumOn = !prefs.albumOn;
  apply(false);
}

function toggleCollapse() {
  prefs.collapsed = !prefs.collapsed;
  apply();
}

for (const slot of SLOTS) {
  const field = document.createElement("select");
  field.id = "slot-" + slot;
  const label = document.createElement("label");
  label.append(slotLabels[slot], field);
  $("slots").append(label);
  field.onchange = () => {
    prefs.slots[slot] = field.value;
    apply();
  };
}

const shortcutValues = ["", "F2", "F3", "F4", "F5", "F6", "F7", "F8", "F9",
  ..."ABCDEFGHIJKLMNOPQRSTUVWXYZ"];
for (const action of Object.keys(KEYS)) {
  const field = $("key-" + action);
  field.replaceChildren(...shortcutValues.map(key => option(key || "Disabled", key)));
  field.onchange = () => {
    if (field.value && Object.entries(prefs.keys).some(([other, key]) => other !== action && key === field.value)) {
      notice("That shortcut is already assigned.");
      renderSettings();
      return;
    }
    prefs.keys[action] = field.value;
    apply();
  };
}

for (const id of ["mode", "override", "grace", "fade", "locked", "sync", "interrupt", "repeat",
    "scale", "transparency"]) {
  const field = $(id);
  field.addEventListener(field.type === "range" ? "input" : "change", () => {
    checkpoint();
    const value = field.type === "checkbox" ? field.checked
      : ["range", "number"].includes(field.type) ? field.valueAsNumber : field.value;
    prefs = settings({ ...prefs, [id]: value });
    apply(false);
  });
}
for (const [channel, id] of Object.entries(volumeIds)) {
  $(id).oninput = () => {
    prefs.volume[channel] = $(id).valueAsNumber;
    apply();
  };
}
for (const id of ["engaged", "members", "alliance", "zone", "cutscene"]) {
  $(id).onchange = () => {
    checkpoint();
    const members = Math.max(1, Math.min(18, Math.floor($("members").valueAsNumber || 1)));
    const zone = Math.max(1, Math.min(9999, Math.floor($("zone").valueAsNumber || 1)));
    $("members").value = members;
    $("zone").value = zone;
    game.update({ engaged: $("engaged").checked, alliance: $("alliance").checked,
      cutscene: $("cutscene").checked, members, zone }, performance.now());
    log("Simulator state changed", { ...game.game });
    save();
    reconcile();
  };
}
$("import").onchange = event => importTracks(event, false);
$("album-import").onchange = event => importTracks(event, true);
$("enable").onclick = () => {
  checkpoint();
  enabled = true;
  emergency = false;
  notice("");
  apply(false, true);
};
$("albumOn").onclick = toggleAlbum;
$("restore").onclick = restore;
$("collapse").onclick = toggleCollapse;
$("pause").onclick = () => {
  checkpoint();
  prefs.paused = !prefs.paused;
  apply(false);
};
for (const [id, step] of [["previous", -1], ["next", 1]]) {
  $(id).onclick = () => {
    nextAlbum(prefs, step);
    apply(false, prefs.album.length === 1);
  };
}

$("drag").onpointerdown = event => {
  if (prefs.locked || event.button !== 0 || event.target.closest("button")) return;
  const [x, y] = place();
  drag = { pointer: event.pointerId, x: event.clientX - x, y: event.clientY - y };
  $("drag").setPointerCapture(event.pointerId);
};
$("drag").onpointermove = event => {
  if (drag?.pointer !== event.pointerId) return;
  prefs.x = event.clientX - drag.x;
  prefs.y = event.clientY - drag.y;
  place();
};
function finishDrag(event) {
  if (drag?.pointer !== event.pointerId) return;
  drag = null;
  [prefs.x, prefs.y] = place();
  save();
}
$("drag").onpointerup = finishDrag;
$("drag").onpointercancel = finishDrag;
$("drag").onlostpointercapture = finishDrag;
$("reset-position").onclick = () => {
  prefs.x = prefs.y = 0;
  apply();
};
$("player").oncontextmenu = event => {
  if (event.target.closest("input, select")) return;
  event.preventDefault();
  $("quick").hidden = false;
  $("quick").style.left = Math.max(0, Math.min(event.clientX, innerWidth - $("quick").offsetWidth)) + "px";
  $("quick").style.top = Math.max(0, Math.min(event.clientY, innerHeight - $("quick").offsetHeight)) + "px";
  $("quick-lock").focus();
};
$("quick-lock").onclick = () => {
  prefs.locked = !prefs.locked;
  apply();
};
$("quick-settings").onclick = () => {
  prefs.collapsed = false;
  apply();
  $("settings-section").open = true;
  $("settings-section").querySelector("summary").focus();
};
$("quick-restore").onclick = restore;
document.addEventListener("click", () => { $("quick").hidden = true; });
document.addEventListener("keydown", event => {
  if (event.key === "Escape") $("quick").hidden = true;
  if (event.repeat || event.altKey || event.ctrlKey || event.metaKey || event.shiftKey
      || event.target.closest("input, select, textarea, [contenteditable]")) return;
  const key = event.key.toUpperCase();
  const actions = { collapse: toggleCollapse, album: toggleAlbum, emergency: restore };
  for (const [action, value] of Object.entries(prefs.keys)) {
    if (key === value) {
      event.preventDefault();
      actions[action]();
      return;
    }
  }
});
$("report").onclick = () => {
  const data = JSON.stringify({ version: "0.1.0", source: live ? "live" : "simulator", events: journal }, null, 2);
  const download = document.createElement("a");
  const url = URL.createObjectURL(new Blob([data], { type: "application/json" }));
  download.href = url;
  download.download = "VanaSync-diagnostics.json";
  download.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
};
window.addEventListener("resize", place);
const catalogTimer = setInterval(refreshCatalog, 1500);
const gameTimer = setInterval(pollGame, 250);
const positionTimer = setInterval(() => {
  const earlier = prefs.position;
  checkpoint();
  if (prefs.position !== earlier) {
    save();
    renderPosition();
  }
}, 1000);
window.addEventListener("pagehide", () => {
  checkpoint();
  save();
  disposed = true;
  clearInterval(catalogTimer);
  clearInterval(positionTimer);
  clearInterval(gameTimer);
  clearTimeout(graceTimer);
  music.stop(false);
  ambience.stop(false);
});
window.addEventListener("pageshow", event => {
  if (event.persisted) location.reload();
});

if (liveLaunch) enabled = true; // launched by XI Forever Offline with autoplay allowed
renderSettings();
renderAssignments();
renderPlaylist();
refreshCatalog();
pollGame();
reconcile();
