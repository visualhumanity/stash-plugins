"use strict";
(() => {
  const PLUGIN_ID = "vhPlayerAspectRatioFix";
  const SETTING_KEY = "shrinkToFit";
  const ORIGINAL = { label: "Original", ratio: null };
  const PRESETS = [
    { label: "16:9", ratio: 16 / 9 },
    { label: "4:3", ratio: 4 / 3 },
    { label: "1:1", ratio: 1 },
    ORIGINAL,
  ];

  // Stash's Filters panel sliders (SceneVideoFilterPanel): Aspect is a stretch factor with
  // default 150, range 0 to 300, divided by 100. Above 150 stretches horizontally, below
  // 150 vertically. Scale is a percentage with default 100.
  const ASPECT_DEFAULT = 150;
  const SCALE_DEFAULT = 100;
  const ASPECT_MIN = 0;
  const ASPECT_MAX = 300;

  // Slider values that make the picture display at `ratio`, starting from the video's natural
  // size as the browser reports it. `ratio` null is Original, which resets both sliders.
  // `scale` null means leave the Scale slider as it is. Returns null while the video size is
  // unknown (videoWidth is 0 until the metadata has loaded).
  function sliderValues({ naturalWidth, naturalHeight, ratio, playerWidth, playerHeight, shrinkToFit }) {
    if (ratio == null) return { aspect: ASPECT_DEFAULT, scale: SCALE_DEFAULT };
    if (!naturalWidth || !naturalHeight) return null;
    const natural = naturalWidth / naturalHeight;
    const stretch = ratio / natural;
    const unclamped =
      stretch > 1 ? ASPECT_DEFAULT + 100 * (stretch - 1) : ASPECT_DEFAULT - 100 * (1 / stretch - 1);
    const aspect = Math.max(ASPECT_MIN, Math.min(ASPECT_MAX, Math.round(unclamped)));
    if (!shrinkToFit || !playerWidth || !playerHeight) return { aspect, scale: null };

    // The stretch Stash applies for this slider value (SceneVideoFilterPanel's formula).
    const stretchX = aspect > ASPECT_DEFAULT ? 1 + (aspect - ASPECT_DEFAULT) / 100 : 1;
    const stretchY = aspect < ASPECT_DEFAULT ? 1 + (ASPECT_DEFAULT - aspect) / 100 : 1;
    // The picture is letterboxed inside the player before the stretch.
    const pictureWidth = Math.min(playerWidth, playerHeight * natural);
    const pictureHeight = pictureWidth / natural;
    const fit = Math.min(playerWidth / (pictureWidth * stretchX), playerHeight / (pictureHeight * stretchY));
    return { aspect, scale: Math.min(SCALE_DEFAULT, Math.floor(100 * fit)) };
  }

  if (typeof window === "undefined") {
    module.exports = { PLUGIN_ID, SETTING_KEY, PRESETS, sliderValues };
    return;
  }

  const PLAYER_ID = "VideoJsPlayer";
  const TICK_MS = 250;
  // Stash can be served under a sub-path; its <base href> holds it (see Stash's createClient).
  const BASE_PATH = new URL(
    (document.querySelector("base") && document.querySelector("base").getAttribute("href")) || "/",
    window.location.origin
  ).pathname;
  const SCENE_PATH = new RegExp(`^${BASE_PATH.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}scenes/(\\d+)`);
  const ICON =
    '<svg viewBox="0 0 24 24" width="1.6em" height="1.6em" aria-hidden="true" focusable="false">' +
    '<rect x="2.5" y="5.5" width="19" height="13" rx="1.5" fill="none" stroke="currentColor" stroke-width="1.6"/>' +
    '<path d="M6 12V9h3M18 12v3h-3" fill="none" stroke="currentColor" stroke-width="1.6"/></svg>';

  const state = {
    sceneId: null,
    active: null, // the preset the plugin applied, or null
    lastSet: null, // { aspect, scale } the plugin last wrote; scale null if it left Scale alone
    pending: null, // preset waiting for the sliders or the video size
    shrinkToFit: false,
  };
  let player = null; // video.js player instance
  let button = null; // video.js Button component in the control bar
  let menu = null;

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
    if (input.value === String(value)) return;
    const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value").set;
    setter.call(input, String(value));
    input.dispatchEvent(new Event("input", { bubbles: true }));
  }

  function writeSliders(values) {
    const s = sliders();
    if (!s) return false;
    setRange(s.aspect, values.aspect);
    if (values.scale != null) setRange(s.scale, values.scale);
    return true;
  }

  function slidersAtDefaults() {
    const s = sliders();
    return !!s && s.aspect.value === String(ASPECT_DEFAULT) && s.scale.value === String(SCALE_DEFAULT);
  }

  function stillActive() {
    const s = sliders();
    if (!state.active || !state.lastSet || !s) return false;
    const { aspect, scale } = state.lastSet;
    return s.aspect.value === String(aspect) && (scale == null || s.scale.value === String(scale));
  }

  function setActive(preset, values) {
    state.active = preset && preset.ratio != null ? preset : null;
    state.lastSet = state.active ? values : null;
    updateButton();
  }

  // Applies a preset now, or keeps it pending until the sliders and the video size exist.
  function apply(preset) {
    const video = videoEl();
    const el = playerEl();
    const rect = el ? el.getBoundingClientRect() : { width: 0, height: 0 };
    const values = sliderValues({
      naturalWidth: video ? video.videoWidth : 0,
      naturalHeight: video ? video.videoHeight : 0,
      ratio: preset.ratio,
      playerWidth: rect.width,
      playerHeight: rect.height,
      shrinkToFit: state.shrinkToFit,
    });
    const applied = !!values && writeSliders(values);
    state.pending = applied ? null : preset;
    setActive(preset, applied ? values : null);
  }

  function refit() {
    if (state.shrinkToFit && stillActive()) apply(state.active);
  }

  function updateButton() {
    if (!button) return;
    const label = (state.active && state.active.label) || "";
    const content = button.el().querySelector(".vh-par-content");
    // Called on every tick while a preset is pending; only touch the DOM when it changes.
    if (content.dataset.label === label) return;
    content.dataset.label = label;
    button.controlText(label ? `Aspect ratio: ${label}` : "Aspect ratio");
    content.innerHTML = label ? `<span class="vh-par-label">${label}</span>` : ICON;
  }

  function closeMenu() {
    if (!menu) return;
    menu.remove();
    menu = null;
    if (button) button.el().setAttribute("aria-expanded", "false");
  }

  function openMenu() {
    const el = playerEl();
    if (!el || !button) return;
    if (state.active && !state.pending && !stillActive()) setActive(null);
    menu = document.createElement("div");
    menu.className = "vh-par-menu";
    menu.setAttribute("role", "menu");
    for (const preset of PRESETS) {
      const item = document.createElement("button");
      const checked =
        preset === ORIGINAL ? !state.active && !state.pending && slidersAtDefaults() : state.active === preset;
      item.type = "button";
      item.className = "vh-par-item";
      item.setAttribute("role", "menuitemradio");
      item.setAttribute("aria-checked", String(checked));
      item.textContent = preset.label;
      item.addEventListener("click", async (event) => {
        event.stopPropagation();
        closeMenu();
        // Read the setting now, so a change on Settings > Plugins applies without a reload.
        await readSetting();
        apply(preset);
      });
      menu.appendChild(item);
    }
    // Inside the player element, so the menu stays visible in fullscreen. Placed above the
    // button, right-aligned to it.
    const playerRect = el.getBoundingClientRect();
    const buttonRect = button.el().getBoundingClientRect();
    menu.style.right = `${Math.max(0, playerRect.right - buttonRect.right)}px`;
    menu.style.bottom = `${Math.max(0, playerRect.bottom - buttonRect.top)}px`;
    el.appendChild(menu);
    button.el().setAttribute("aria-expanded", "true");
  }

  // Adds the button to video.js's control bar, before the fullscreen toggle, the same way
  // Stash adds its own control-bar buttons. Done again whenever video.js creates a new player.
  function ensureButton() {
    const el = playerEl();
    const current = el && el.player;
    if (!current || !current.controlBar) return;
    if (current === player && button && button.el().isConnected) return;

    player = current;
    const { controlBar } = player;
    button = controlBar.addChild("Button", { className: "vh-par-button" });
    const content = document.createElement("span");
    content.className = "vh-par-content";
    button.el().prepend(content);
    button.el().setAttribute("aria-haspopup", "menu");
    button.el().setAttribute("aria-expanded", "false");
    const fullscreenToggle = controlBar.getChild("fullscreenToggle");
    if (fullscreenToggle) controlBar.el().insertBefore(button.el(), fullscreenToggle.el());
    button.on("click", (event) => {
      event.stopPropagation();
      if (menu) closeMenu();
      else openMenu();
    });
    player.on("loadedmetadata", () => {
      if (state.pending) apply(state.pending);
    });
    player.on("playerresize", refit);
    // The control bar hides when the user is inactive; don't leave the menu floating.
    player.on("userinactive", closeMenu);
    updateButton();
  }

  async function readSetting() {
    try {
      const res = await fetch(`${BASE_PATH}graphql`, {
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
    state.pending = ORIGINAL;
    setActive(null);
    closeMenu();
    readSetting();
  }

  function tick() {
    const match = window.location.pathname.match(SCENE_PATH);
    if (!match) {
      state.sceneId = null;
      return;
    }
    if (match[1] !== state.sceneId) onSceneChange(match[1]);
    ensureButton();
    if (state.pending) apply(state.pending);
    else if (state.active && !stillActive()) setActive(null);
  }

  document.addEventListener("click", (event) => {
    if (menu && !menu.contains(event.target)) closeMenu();
  });
  // Capture phase: the player's own key handling stops Escape before it reaches the document.
  document.addEventListener(
    "keydown",
    (event) => {
      if (event.key === "Escape") closeMenu();
    },
    true
  );
  document.addEventListener("fullscreenchange", () => {
    closeMenu();
    setTimeout(refit, TICK_MS);
  });
  window.addEventListener("resize", refit);
  readSetting();
  setInterval(tick, TICK_MS);
})();
