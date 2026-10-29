# VH - Player Aspect Ratio Fix

Adds an aspect ratio button to the scene player's control bar. Pick a ratio and the playing
picture is stretched to it, for videos that play at the wrong shape (for example a squeezed
widescreen re-encode, or a 4:3 video stretched to 16:9).

## Features

- Aspect ratio button next to the player's fullscreen button, with **16:9**, **4:3**, **1:1** and
  **Original** presets. Works in fullscreen.
- Only the picture on screen changes. Files, stored metadata and the scene itself are never
  modified, and nothing is saved.
- Optional **Shrink to fit** keeps a stretched picture fully inside the player.

## Use

1. Open a scene and show the player's controls.
2. Click the aspect ratio button, next to the fullscreen button.
3. Pick **16:9**, **4:3** or **1:1**. The button then shows the active ratio (for example `4:3`).
4. Pick **Original** to go back to how the video looked when it loaded.

The menu marks the active choice.

## How presets work

The plugin drives Stash's own **Aspect Ratio** and **Scale** sliders on the scene page's
**Filters** tab. You can see the values it set there and fine-tune them by hand.

- Ratios are absolute. Each preset is calculated from the video's natural size as the browser
  reports it, so picking 4:3 and then 16:9 gives 16:9, not two stretches stacked.
- The browser already applies a file's pixel aspect ratio. An anamorphic 720x480 DVD rip with
  8:9 pixels already displays at 4:3, so the 4:3 preset leaves it unchanged.
- The sliders take whole numbers only, so results are within about 0.4% of the target ratio.
- Presets only change the Scale slider when Shrink to fit is on, so a Scale you set by hand is
  kept. **Original** resets both sliders.
- Moving to another scene resets both sliders to their defaults, so a preset never carries over.
  This also resets values you set by hand on the Filters tab.
- If you move the Aspect Ratio or Scale slider by hand, the button and menu stop showing a preset
  as active.

With Shrink to fit off, a preset that makes the picture taller relative to its width is cut off
at the top and bottom in a landscape player, which includes most fullscreen use. For example,
1:1 on a 4:3 video can look the same size as 4:3 with the top and bottom of the picture missing.
Turn on Shrink to fit to see the whole picture.

## Configuration

| Setting | Default | Description |
|---|---|---|
| Shrink to fit | off | Scale a stretched picture down so it stays fully inside the player instead of being cropped at the edges. A change takes effect the next time you pick a preset, without reloading. When it is on, the scale is recalculated when the player is resized or enters or leaves fullscreen. |

## Known limitations

- VR mode is not supported. The player draws to a canvas there, and the button gives wrong results.
- The button hides with the rest of the player controls while the mouse is idle (video.js behavior).
- On some devices the video size is unknown until playback starts. A preset picked before that is
  applied as soon as the video loads.
- Only tested in Chromium-based browsers.
- No keyboard shortcut.

## Development

Tests: `python3 -m unittest discover -t . -s tests/vhPlayerAspectRatioFix` from the repo root.
They load `vhPlayerAspectRatioFix.js` in Node (`node` must be on the `PATH`) and cover the slider
values each preset writes, the menu presets, touch taps, and that the script and manifest agree on
the plugin ID and setting key. The button and menu in a real player have no automated tests; check
them by hand on a test Stash instance.
