const identity = target => target.key + ":" + target.id;
const loadTimeout = 8000;

function openAudio(target, signal) {
  const audio = new Audio();
  audio.preload = "auto";
  audio.loop = target.loop;
  audio.volume = 0;
  audio.src = "/media/" + target.id;
  return new Promise((resolve, reject) => {
    const finish = error => {
      clearTimeout(timer);
      audio.onloadeddata = audio.onerror = null;
      signal.removeEventListener("abort", abort);
      if (error) {
        dispose(audio);
        reject(error);
      } else resolve(audio);
    };
    const abort = () => finish(new Error("cancelled"));
    const timer = setTimeout(() => finish(new Error("load timeout")), loadTimeout);
    audio.onloadeddata = () => finish();
    audio.onerror = () => finish(new Error("decode or file error"));
    signal.addEventListener("abort", abort, { once: true });
    audio.load();
  });
}

function dispose(audio) {
  audio.onended = audio.onerror = null;
  audio.pause();
  audio.removeAttribute("src");
  audio.load();
}

export class Mixer {
  constructor(events, open = openAudio) {
    this.events = events;
    this.open = open;
    this.live = null;
    this.outgoing = null;
    this.pending = null;
    this.last = "";
    this.frame = 0;
    this.volume = {};
  }

  position(key) {
    return this.live?.target.key === key ? this.live.audio.currentTime : null;
  }

  gain(deck, level) {
    deck.level = level;
    deck.audio.volume = level * (this.volume[deck.target.channel] ?? 1);
  }

  setVolume(volume) {
    this.volume = volume;
    for (const deck of [this.live, this.outgoing]) if (deck) this.gain(deck, deck.level);
  }

  dropOutgoing() {
    cancelAnimationFrame(this.frame);
    if (this.outgoing) dispose(this.outgoing.audio);
    this.outgoing = null;
  }

  switchTo(deck, seconds) {
    this.dropOutgoing();
    this.outgoing = this.live;
    this.live = deck;
    if (this.outgoing) this.outgoing.audio.onended = this.outgoing.audio.onerror = null;
    const start = performance.now();
    const from = this.outgoing?.level ?? 0;
    const frame = now => {
      const progress = seconds ? Math.max(0, Math.min(1, (now - start) / (seconds * 1000))) : 1;
      if (this.outgoing) this.gain(this.outgoing, from * Math.cos(progress * Math.PI / 2));
      if (this.live) this.gain(this.live, Math.sin(progress * Math.PI / 2));
      if (progress < 1) this.frame = requestAnimationFrame(frame);
      else this.dropOutgoing();
    };
    frame(start);
    this.events.changed(deck?.target ?? null);
  }

  async reconcile(stack, catalog, fade, force = false) {
    const signature = JSON.stringify(stack.map(t => [identity(t), t.match, !!catalog[t.id]]));
    if (!force && signature === this.last) return;
    this.last = signature;
    this.pending?.abort();
    const controller = new AbortController();
    this.pending = controller;
    const { signal } = controller;
    try {
      for (const target of stack) {
        if (signal.aborted) return;
        if (!catalog[target.id]) {
          if (target.ownership === "custom" || target.channel === "ambience")
            this.events.error(target, "missing or unassigned audio");
          continue;
        }
        if (this.live && identity(this.live.target) === identity(target) && !force) {
          this.live.target = target;
          this.events.settled?.(target);
          return;
        }
        this.events.loading?.(target);
        let audio;
        try {
          audio = await this.open(target, signal);
          if (signal.aborted) {
            dispose(audio);
            return;
          }
          const prior = this.live;
          const position = target.match && target.match === prior?.target.match
            ? prior.audio.currentTime : target.position;
          if (position > 0 && Number.isFinite(audio.duration) && audio.duration > 0) {
            audio.currentTime = target.loop ? position % audio.duration
              : Math.min(position, Math.max(0, audio.duration - 0.05));
          }
          let timer;
          let stopPending;
          const deadline = new Promise((_, reject) => {
            timer = setTimeout(() => reject(new Error("start timeout")), loadTimeout);
            stopPending = () => reject(new Error("cancelled"));
            signal.addEventListener("abort", stopPending, { once: true });
          });
          try {
            await Promise.race([audio.play(), deadline]);
          } finally {
            clearTimeout(timer);
            signal.removeEventListener("abort", stopPending);
          }
          if (signal.aborted) {
            dispose(audio);
            return;
          }
          const deck = { audio, target, level: 0 };
          audio.onended = () => {
            if (this.live === deck) this.events.ended(deck.target);
          };
          audio.onerror = () => {
            if (this.live !== deck) return;
            dispose(audio);
            this.dropOutgoing();
            this.live = null;
            this.events.error(deck.target, "playback failed");
            this.events.changed(null);
            this.events.failed?.(deck.target);
          };
          this.switchTo(deck, fade);
          return;
        } catch (error) {
          if (audio) dispose(audio);
          if (signal.aborted) return;
          this.events.error(target, error.name === "NotAllowedError"
            ? "Use Enable audio to allow playback" : error.message || "playback failed");
        }
      }
      this.switchTo(null, fade);
    } finally {
      if (this.pending === controller) this.pending = null;
    }
  }

  stop(notify = true) {
    this.pending?.abort();
    this.dropOutgoing();
    if (this.live) dispose(this.live.audio);
    this.live = null;
    this.last = "";
    if (notify) this.events.changed(null);
  }
}
