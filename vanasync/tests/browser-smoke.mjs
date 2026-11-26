import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { access, mkdtemp, readFile, readdir, rename, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const [referencePath, screenshotPath] = process.argv.slice(2);
if (!referencePath) throw new Error("Pass a local MP3 you may use as the simulator reference.");
const root = dirname(dirname(fileURLToPath(import.meta.url)));
const edge = process.env.VANASYNC_EDGE || join(process.env["ProgramFiles(x86)"] || "", "Microsoft", "Edge", "Application", "msedge.exe");
const temp = await mkdtemp(join(tmpdir(), "vanasync-edge-"));
const profile = join(temp, "profile");
const data = join(temp, "catalog");
const downloads = join(temp, "downloads");
const server = spawn(process.env.VANASYNC_PYTHON || "python",
  [join(root, "server.py"), "--port", "0", "--no-open", "--data", data],
  { stdio: ["ignore", "pipe", "inherit"] });
let browser;
let socket;
const exceptions = [];
const delay = ms => new Promise(done => setTimeout(done, ms));
const request = (url, options = {}) => fetch(url, { ...options, signal: AbortSignal.timeout(4000) });

async function until(fn, label, timeout = 10000) {
  const end = Date.now() + timeout;
  let last;
  while (Date.now() < end) {
    try {
      last = await fn();
      if (last) return last;
    } catch (error) {
      last = error.message;
    }
    await delay(75);
  }
  throw new Error("Timed out: " + label + " [" + String(last) + "]");
}

try {
  let output = "";
  server.stdout.on("data", chunk => { output += chunk; });
  const origin = await until(() => output.match(/http:\/\/127\.0\.0\.1:\d+/)?.[0], "host startup");
  console.log("Local host started");
  const { defaults, tracks } = await (await request(origin + "/api/bootstrap")).json();
  const names = Object.fromEntries(Object.entries(defaults).map(([slot, id]) => [slot, tracks[id].slice(0, -4)]));
  const refBytes = await readFile(referencePath);
  async function importReference(name, bytes) {
    const response = await request(origin + "/api/tracks", { method: "POST", body: bytes,
      headers: { "Content-Type": "application/octet-stream", "X-VanaSync": "1",
        Origin: origin, "X-Filename": encodeURIComponent(name) } });
    assert.equal(response.status, 201);
    return (await response.json()).id;
  }
  const reference = await importReference("Simulator Reference.mp3", refBytes);
  const corrupt = await importReference("Decode failure test.mp3", "invalid audio test bytes");
  await access(edge);
  browser = spawn(edge, ["--headless=new", "--no-first-run", "--disable-background-networking",
    "--remote-debugging-port=0", "--window-size=1240,1000", "--user-data-dir=" + profile, "about:blank"],
  { stdio: ["ignore", "ignore", "pipe"] });
  let browserOutput = "";
  browser.stderr.on("data", chunk => { browserOutput += chunk; });
  const debugPort = await until(async () => {
    if (browser.exitCode !== null) throw new Error(browserOutput.slice(-500));
    return (await readFile(join(profile, "DevToolsActivePort"), "utf8")).split("\n")[0];
  }, "local Edge startup");
  console.log("Edge debug port ready");
  const target = await until(async () => (await (await request("http://127.0.0.1:" + debugPort + "/json/list")).json())
    .find(candidate => candidate.type === "page"), "Edge tab");
  socket = new WebSocket(target.webSocketDebuggerUrl);
  await new Promise((done, reject) => {
    const timeout = setTimeout(() => reject(new Error("Edge debugging websocket timeout")), 5000);
    socket.addEventListener("open", () => clearTimeout(timeout));
    socket.addEventListener("open", done);
    socket.addEventListener("error", reject);
  });
  console.log("Edge tab attached");
  let sequence = 0;
  const requests = new Map();
  socket.addEventListener("message", event => {
    const message = JSON.parse(event.data);
    if (message.method === "Runtime.exceptionThrown") {
      const details = message.params.exceptionDetails;
      exceptions.push(details.exception?.description || details.text);
    }
    if (!requests.has(message.id)) return;
    const { done, reject, timer } = requests.get(message.id);
    clearTimeout(timer);
    requests.delete(message.id);
    if (message.error) reject(new Error(message.error.message));
    else done(message.result);
  });
  function call(method, params = {}) {
    const id = ++sequence;
    return new Promise((done, reject) => {
      const timer = setTimeout(() => {
        requests.delete(id);
        reject(new Error("Edge command timed out: " + method));
      }, 4000);
      requests.set(id, { done, reject, timer });
      socket.send(JSON.stringify({ id, method, params }));
    });
  }
  async function run(expression) {
    const result = await call("Runtime.evaluate", { expression, returnByValue: true, userGesture: true });
    if (result.exceptionDetails) throw new Error(result.exceptionDetails.exception?.description || result.exceptionDetails.text);
    return result.result.value;
  }
  const get = id => "document.getElementById(" + JSON.stringify(id) + ")";
  const read = (id, property = "textContent") => run(get(id) + "." + property);
  const click = id => run(get(id) + ".click()");
  const set = (id, value, property = "value", event = "change") =>
    run(get(id) + "." + property + "=" + JSON.stringify(value) + ";" + get(id)
      + ".dispatchEvent(new Event(" + JSON.stringify(event) + ",{bubbles:true}));"
      + "document.getElementById('phase').textContent");
  async function title(value) {
    try {
      await until(async () => (await read("track")) === value, "title " + value);
    } catch (error) {
      throw new Error(error.message + " observed " + JSON.stringify(await run(
        "[...['track','transport-status','phase','notice','arrangement'].map(id => document.getElementById(id).textContent),"
        + "...['mode','override','members','engaged','alliance'].map(id => {const el=document.getElementById(id);return [el.value,el.checked]})]"
      )));
    }
  }
  const phase = value => until(async () => (await read("phase")) === value, "phase " + value);
  const prefs = () => run("JSON.parse(localStorage.getItem('vanasync.settings.v1'))");
  const report = description => console.log("PASS " + description);
  async function capture() {
    if (!screenshotPath) return;
    const frame = await call("Page.captureScreenshot", { format: "png" });
    await writeFile(resolve(screenshotPath), Buffer.from(frame.data, "base64"));
  }
  await call("Runtime.enable");
  await call("Page.enable");
  await call("Page.addScriptToEvaluateOnNewDocument", { source:
    "window.testAudio=[]; const NativeAudio=window.Audio; window.Audio=function(){const audio=new NativeAudio();window.testAudio.push(audio);return audio;};" });
  await call("Browser.setDownloadBehavior", { behavior: "allow", downloadPath: downloads });
  await call("Page.navigate", { url: origin });
  console.log("Player navigation issued");
  await until(async () => (await read("slot-solo", "value")) === defaults.solo, "bundled slot assignments");
  assert.equal(await read("grace", "value"), "5");
  assert.equal(await read("mode", "value"), "Vanilla");
  await set("slot-exploration", reference);
  await set("slot-nativeSolo", reference);
  await set("slot-cutscene", reference);
  await click("enable");
  await title("Simulator Reference");
  await set("mode", "Resonance");
  await set("engaged", true, "checked");
  await title(names.solo);
  await phase("Combat");
  await set("members", "4");
  await title(names.party);
  await capture();
  await set("alliance", true, "checked");
  await title(names.alliance);
  await set("override", "solo");
  await title(names.solo);
  await set("members", "1");
  await set("alliance", false, "checked");
  await set("override", "auto");
  report("Bundled MP3 playback, automatic Solo/Party/Alliance, and manual override");
  await set("mode", "Vanilla");
  await title("Simulator Reference");
  await set("mode", "Off");
  await title("No audio playing");
  await set("mode", "Resonance");
  await title(names.solo);
  assert.equal(await set("engaged", false, "checked"), "Post-combat");
  assert.equal(await read("track"), names.solo);
  const audioCount = await run("window.testAudio.length");
  await delay(400);
  await set("engaged", true, "checked");
  await phase("Combat");
  assert.equal(await read("track"), names.solo);
  assert.equal(await run("window.testAudio.length"), audioCount);
  await set("engaged", false, "checked");
  await title("Simulator Reference");
  await phase("Exploration");
  report("Vanilla and Off switching, rapid re-engagement, and five-second exploration restore");
  assert.equal(await set("engaged", true, "checked"), "Combat");
  await title(names.solo);
  const soloPath = join(data, "tracks", defaults.solo, tracks[defaults.solo]);
  const renamed = "戦闘・Against the Odds (Final).MP3";
  await rename(soloPath, join(dirname(soloPath), renamed));
  await title(renamed.slice(0, -4));
  assert.equal((await prefs()).slots.solo, defaults.solo);
  await rename(join(dirname(soloPath), renamed), join(dirname(soloPath), "temporarily-missing.bin"));
  await title("Simulator Reference");
  await set("slot-solo", corrupt);
  await until(async () => (await read("transport-status")).includes("Custom track unavailable"), "decode fallback");
  await rename(join(dirname(soloPath), "temporarily-missing.bin"), soloPath);
  await until(async () => await run("[..." + get("slot-solo") + ".options].some(item => item.value === "
    + JSON.stringify(defaults.solo) + " && !item.text.startsWith('Missing file'))"),
    "restored catalog entry");
  await set("slot-solo", defaults.solo);
  await title(names.solo);
  await click("restore");
  await title("Simulator Reference");
  assert.match(await read("transport-status"), /Simulated native restoration/);
  await click("enable");
  await title(names.solo);
  report("Unicode rename, retained assignment, missing and corrupt audio fallback, and emergency restore");
  await set("grace", "0");
  await set("engaged", false, "checked");
  const one = join(temp, "01・Album test.mp3");
  const two = join(temp, "02・Album test.mp3");
  await writeFile(one, refBytes);
  await writeFile(two, refBytes);
  const { root: docNode } = await call("DOM.getDocument");
  const { nodeId } = await call("DOM.querySelector", { nodeId: docNode.nodeId, selector: "#album-import" });
  await call("DOM.setFileInputFiles", { nodeId, files: [one, two] });
  await until(async () => (await prefs()).album.length === 2, "playlist import");
  await click("albumOn");
  await title("01・Album test");
  await set("zone", "2");
  await set("engaged", true, "checked");
  assert.equal(await read("track"), "01・Album test");
  await until(async () => (await prefs()).position >= 1, "album checkpoint");
  const before = (await prefs()).position;
  await set("interrupt", true, "checked");
  await title(names.solo);
  assert.ok((await prefs()).position >= before);
  await set("engaged", false, "checked");
  await title("01・Album test");
  await until(async () => (await prefs()).position > before + 0.1, "album resumed");
  await set("cutscene", true, "checked");
  await title("Simulator Reference");
  await set("cutscene", false, "checked");
  await title("01・Album test");
  await click("next");
  await title("02・Album test");
  await click("previous");
  await title("01・Album test");
  await click("pause");
  await title("No audio playing");
  await click("pause");
  await title("01・Album test");
  await set("repeat", true, "checked");
  await set("scale", "1.1", "value", "input");
  await set("transparency", "0.8", "value", "input");
  await set("album", "0.37", "value", "input");
  await set("key-collapse", "K");
  await run("document.body.dispatchEvent(new KeyboardEvent('keydown',{key:'k',bubbles:true}))");
  assert.equal(await read("deck", "hidden"), true);
  await click("collapse");
  async function dragHeader() {
    await run("window.scrollTo(0,0)");
    const [x, y] = await run("(()=>{const box=document.getElementById('drag').getBoundingClientRect();return [box.left+50,box.top+24]})()");
    await call("Input.dispatchMouseEvent", { type: "mouseMoved", x, y });
    await call("Input.dispatchMouseEvent", { type: "mousePressed", x, y, button: "left", buttons: 1, clickCount: 1 });
    await call("Input.dispatchMouseEvent", { type: "mouseMoved", x: x + 60, y: y + 30, buttons: 1 });
    await call("Input.dispatchMouseEvent", { type: "mouseReleased", x: x + 60, y: y + 30, button: "left", clickCount: 1 });
    await call("Input.dispatchMouseEvent", { type: "mouseMoved", x: x + 60, y: y + 30 });
  }
  await dragHeader();
  await until(async () => (await prefs()).x > 20, "saved drag position");
  const moved = (await prefs()).x;
  await run(get("drag") + ".dispatchEvent(new MouseEvent('contextmenu',{bubbles:true,clientX:300,clientY:200}))");
  assert.equal(await read("quick", "hidden"), false);
  await click("quick-lock");
  assert.equal((await prefs()).locked, true);
  await dragHeader();
  assert.equal((await prefs()).x, moved);
  await click("report");
  await until(async () => (await readdir(downloads)).includes("VanaSync-diagnostics.json"), "diagnostics download");
  const diagnostics = JSON.parse(await readFile(join(downloads, "VanaSync-diagnostics.json"), "utf8"));
  assert.equal(diagnostics.source, "simulator");
  assert.ok(diagnostics.events.some(record => record.event === "Audio fallback" && record.detail.reason.includes("decode")));
  await call("Page.reload");
  await until(async () => (await read("key-collapse", "value")) === "K", "saved settings after reload");
  assert.equal(await read("mode", "value"), "Resonance");
  assert.equal(await read("repeat", "checked"), true);
  assert.equal(await read("album", "value"), "0.37");
  assert.equal((await prefs()).x, moved);
  assert.equal(await run("getComputedStyle(document.getElementById('player')).opacity"), "0.8");
  await click("enable");
  await title("01・Album test");
  await click("albumOn");
  await title("Simulator Reference");
  assert.equal(await read("mode", "value"), "Resonance");
  report("Album import order, transport, zone continuity, battle/cutscene resume, settings, and diagnostic download");
  assert.deepEqual(exceptions, []);
  if (screenshotPath) {
    await set("engaged", true, "checked");
    await set("override", "party");
    await title(names.party);
    await capture();
  }
} catch (error) {
  console.error(error);
  if (exceptions.length) console.error(exceptions);
  process.exitCode = 1;
} finally {
  if (socket?.readyState === WebSocket.OPEN) {
    socket.send(JSON.stringify({ id: 2147483647, method: "Browser.close" }));
    socket.close();
  }
  server.kill();
  browser?.stderr.destroy();
  server.stdout.destroy();
  await delay(250);
  if (browser?.exitCode === null) browser.kill();
  await rm(temp, { recursive: true, force: true, maxRetries: 4, retryDelay: 250 });
}
