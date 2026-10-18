"use strict";
(() => {
  const PLUGIN_ID = "vhPlayerAspectRatioFix";
  const SETTING_KEY = "shrinkToFit";
  const PRESETS = [
    { label: "16:9", ratio: 16 / 9 },
    { label: "4:3", ratio: 4 / 3 },
    { label: "1:1", ratio: 1 },
    { label: "Original", ratio: null },
  ];

  // Stash's Filters panel sliders (SceneVideoFilterPanel): Aspect is a stretch factor with
  // default 150, range 0 to 300, divided by 100. Above 150 stretches horizontally, below
  // 150 vertically. Scale is a percentage with default 100.
  const ASPECT_DEFAULT = 150;
  const SCALE_DEFAULT = 100;
  const ASPECT_MIN = 0;
  const ASPECT_MAX = 300;

  // Slider values that make the picture display at `ratio`, starting from the video's natural
  // size as the browser reports it. `ratio` null is Original. Returns null while the video
  // size is unknown (videoWidth is 0 until the metadata has loaded).
  function calculate({ naturalWidth, naturalHeight, ratio, playerWidth, playerHeight, shrinkToFit }) {
    if (ratio == null) return { aspect: ASPECT_DEFAULT, scale: SCALE_DEFAULT };
    if (!naturalWidth || !naturalHeight) return null;
    const natural = naturalWidth / naturalHeight;
    const k = ratio / natural;
    const raw = k > 1 ? ASPECT_DEFAULT + 100 * (k - 1) : ASPECT_DEFAULT - 100 * (1 / k - 1);
    const aspect = Math.max(ASPECT_MIN, Math.min(ASPECT_MAX, Math.round(raw)));
    if (!shrinkToFit) return { aspect, scale: SCALE_DEFAULT };

    // The stretch Stash applies for this slider value (SceneVideoFilterPanel's formula).
    const x = aspect > ASPECT_DEFAULT ? 1 + (aspect - ASPECT_DEFAULT) / 100 : 1;
    const y = aspect < ASPECT_DEFAULT ? 1 + (ASPECT_DEFAULT - aspect) / 100 : 1;
    // The picture is letterboxed inside the player before the stretch.
    const width = Math.min(playerWidth, playerHeight * natural);
    const height = width / natural;
    const needed = Math.floor(100 * Math.min(playerWidth / (width * x), playerHeight / (height * y)));
    return { aspect, scale: Math.min(SCALE_DEFAULT, needed) };
  }

  if (typeof window === "undefined") {
    module.exports = { PLUGIN_ID, SETTING_KEY, PRESETS, calculate };
    return;
  }

  const PLAYER_ID = "VideoJsPlayer";
  const TICK_MS = 250;
  const ICON =
    '<svg viewBox="0 0 24 24" width="1.6em" height="1.6em" aria-hidden="true" focusable="false">' +
    '<rect x="2.5" y="5.5" width="19" height="13" rx="1.5" fill="none" stroke="currentColor" stroke-width="1.6"/>' +
    '<path d="M6 12V9h3M18 12v3h-3" fill="none" stroke="currentColor" stroke-width="1.6"/></svg>';

  const state = {
    sceneId: null,
    active: null, // label of the preset the plugin applied, or null
    lastSet: null, // { aspect, scale } the plugin last wrote to the sliders
    pending: null, // preset waiting for the sliders or the video size
    shrinkToFit: false,
  };
  let button = null;
  let menu = null;
  let boundPlayer = null;

  const playerEl = () => document.getElementById(PLAYER_ID);
  const videoEl = () => {
    const el = playerEl();
    return el && el.querySelector("video");
  };

  function sliders() {
    const panel = document.querySelector(".scene-video-filter");
    if (!panel) return null;
    const inputs = Array.from(panel.querySelectorAll('input[type="range"]'));
    const index = inputs.findIndex((input) => input.max === String(ASPECT_MAX));
    // Scale is the slider directly before Aspect in the panel.
    if (index < 1) return null;
    return { aspect: inputs[index], scale: inputs[index - 1] };
  }

  // The sliders are React-controlled: set the value through the native setter and fire an
  // input event so React updates its state, and Stash applies the transform itself.
  function setRange(input, value) {
    const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value").set;
    setter.call(input, String(value));
    input.dispatchEvent(new Event("input", { bubbles: true }));
  }

  function writeSliders(values) {
    const s = sliders();
    if (!s) return false;
    if (s.aspect.value !== String(values.aspect)) setRange(s.aspect, values.aspect);
    if (s.scale.value !== String(values.scale)) setRange(s.scale, values.scale);
    return true;
  }

  function stillActive() {
    const s = sliders();
    return !!(
      state.active &&
      state.lastSet &&
      s &&
      s.aspect.value === String(state.lastSet.aspect) &&
      s.scale.value === String(state.lastSet.scale)
    );
  }

  // Applies a preset now, or keeps it pending until the sliders and the video size exist.
  function apply(preset) {
    const video = videoEl();
    const player = playerEl();
    const rect = player ? player.getBoundingClientRect() : { width: 0, height: 0 };
    const values = calculate({
      naturalWidth: video ? video.videoWidth : 0,
      naturalHeight: video ? video.videoHeight : 0,
      ratio: preset.ratio,
      playerWidth: rect.width,
      playerHeight: rect.height,
      shrinkToFit: state.shrinkToFit,
    });
    if (!values || !writeSliders(values)) {
      state.pending = preset;
      state.active = preset.ratio == null ? null : preset.label;
      state.lastSet = null;
      updateButton();
      return;
    }
    state.pending = null;
    state.active = preset.ratio == null ? null : preset.label;
    state.lastSet = preset.ratio == null ? null : values;
    updateButton();
  }

  function refit() {
    if (!state.shrinkToFit || !state.active || !stillActive()) return;
    apply(PRESETS.find((p) => p.label === state.active));
  }

  function updateButton() {
    if (!button) return;
    const label = state.active;
    button.classList.toggle("vh-par-button--active", !!label);
    button.title = label ? `Aspect ratio: ${label}` : "Aspect ratio";
    button.setAttribute("aria-label", button.title);
    button.innerHTML = label ? `<span class="vh-par-label">${label}</span>` : ICON;
  }

  function closeMenu() {
    if (!menu) return;
    menu.remove();
    menu = null;
    if (button) button.setAttribute("aria-expanded", "false");
  }

  function openMenu() {
    const player = playerEl();
    if (!player) return;
    if (state.active && !state.pending && !stillActive()) {
      state.active = null;
      state.lastSet = null;
      updateButton();
    }
    menu = document.createElement("div");
    menu.className = "vh-par-menu";
    menu.setAttribute("role", "menu");
    for (const preset of PRESETS) {
      const item = document.createElement("button");
      const checked = preset.ratio == null ? !state.active : state.active === preset.label;
      item.type = "button";
      item.className = "vh-par-item";
      item.setAttribute("role", "menuitemradio");
      item.setAttribute("aria-checked", String(checked));
      item.textContent = preset.label;
      item.addEventListener("click", (event) => {
        event.stopPropagation();
        apply(preset);
        closeMenu();
      });
      menu.appendChild(item);
    }
    // Inside the player element, so the menu stays visible in fullscreen.
    player.appendChild(menu);
    button.setAttribute("aria-expanded", "true");
  }

  function buildButton() {
    button = document.createElement("button");
    button.type = "button";
    button.className = "vjs-control vjs-button vh-par-button";
    button.setAttribute("aria-haspopup", "menu");
    button.setAttribute("aria-expanded", "false");
    button.addEventListener("click", (event) => {
      event.stopPropagation();
      if (menu) closeMenu();
      else openMenu();
    });
    updateButton();
  }

  // video.js can rebuild its control bar; put the button back whenever it is missing.
  function ensureButton() {
    const player = playerEl();
    const bar = player && player.querySelector(".vjs-control-bar");
    if (!bar) return;
    if (!button) buildButton();
    if (!bar.contains(button)) bar.insertBefore(button, bar.querySelector(".vjs-fullscreen-control"));
  }

  // video.js keeps its player instance on the player element.
  function bindPlayer() {
    const player = playerEl() && playerEl().player;
    if (!player || player === boundPlayer) return;
    boundPlayer = player;
    player.on("loadedmetadata", () => {
      if (state.pending) apply(state.pending);
    });
    player.on("playerresize", refit);
  }

  async function readSetting() {
    try {
      const res = await fetch("/graphql", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query: "{ configuration { plugins } }" }),
      });
      const json = await res.json();
      const settings = (json.data && json.data.configuration.plugins[PLUGIN_ID]) || {};
      state.shrinkToFit = settings[SETTING_KEY] === true;
    } catch (e) {
      state.shrinkToFit = false;
    }
  }

  // The scene page is not remounted between scenes, so the Filters panel keeps its slider
  // values. Reset them so a preset never carries into the next scene.
  function onSceneChange(sceneId) {
    state.sceneId = sceneId;
    state.active = null;
    state.lastSet = null;
    state.pending = { label: "Original", ratio: null };
    closeMenu();
    updateButton();
    readSetting();
  }

  function tick() {
    const match = window.location.pathname.match(/^\/scenes\/(\d+)/);
    if (!match) {
      state.sceneId = null;
      return;
    }
    if (match[1] !== state.sceneId) onSceneChange(match[1]);
    ensureButton();
    bindPlayer();
    if (state.pending) apply(state.pending);
    if (state.active && !state.pending && !stillActive()) {
      state.active = null;
      state.lastSet = null;
      updateButton();
    }
  }

  document.addEventListener("click", (event) => {
    if (menu && !menu.contains(event.target)) closeMenu();
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") closeMenu();
  });
  document.addEventListener("fullscreenchange", () => setTimeout(refit, TICK_MS));
  window.addEventListener("resize", refit);
  setInterval(tick, TICK_MS);
})();
