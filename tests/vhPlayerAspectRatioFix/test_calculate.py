import json
import os
import shutil
import subprocess
import unittest

PLUGIN_JS = os.path.join(
    os.path.dirname(__file__), "..", "..", "plugins", "vhPlayerAspectRatioFix", "vhPlayerAspectRatioFix.js"
)


def calculate(**inputs):
    """Run the plugin's calculate() in Node and return its result."""
    node = shutil.which("node")
    if node is None:
        raise AssertionError("node is required to run the vhPlayerAspectRatioFix tests")
    script = (
        "const { calculate } = require(process.argv[1]);"
        "process.stdout.write(JSON.stringify(calculate(JSON.parse(process.argv[2]))));"
    )
    out = subprocess.run(
        [node, "-e", script, os.path.abspath(PLUGIN_JS), json.dumps(inputs)],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(out.stdout)


def preset(width, height, ratio, player=(0, 0), fit=False):
    return calculate(
        naturalWidth=width,
        naturalHeight=height,
        ratio=ratio,
        playerWidth=player[0],
        playerHeight=player[1],
        shrinkToFit=fit,
    )


class CalculateTests(unittest.TestCase):
    def test_widescreen_source_to_4_3_stretches_vertically(self):
        self.assertEqual(preset(1920, 1080, 4 / 3), {"aspect": 117, "scale": 100})

    def test_4_3_source_to_16_9_stretches_horizontally(self):
        self.assertEqual(preset(720, 540, 16 / 9), {"aspect": 183, "scale": 100})

    def test_original_returns_slider_defaults(self):
        self.assertEqual(preset(720, 480, None), {"aspect": 150, "scale": 100})
        self.assertEqual(preset(1920, 1080, None, player=(400, 800), fit=True), {"aspect": 150, "scale": 100})

    def test_aspect_is_clamped_to_the_slider_range(self):
        # 1:3 portrait source to 16:9 needs a 5.33x horizontal stretch; the slider stops at 300
        self.assertEqual(preset(360, 1080, 16 / 9), {"aspect": 300, "scale": 100})
        # 4:1 source to 1:1 needs a 4x vertical stretch; the slider stops at 0
        self.assertEqual(preset(1600, 400, 1), {"aspect": 0, "scale": 100})

    def test_shrink_to_fit_scales_a_vertical_stretch_into_a_landscape_player(self):
        # 16:9 source fills a 1600x900 player; 1:1 stretches it to 1600x1602 (slider 72 is 1.78x)
        self.assertEqual(preset(1920, 1080, 1, player=(1600, 900), fit=True), {"aspect": 72, "scale": 56})

    def test_shrink_to_fit_scales_a_horizontal_stretch(self):
        # 4:3 source fills an 800x600 player; 16:9 stretches it to 1064x600 (slider 183 is 1.33x)
        self.assertEqual(preset(720, 540, 16 / 9, player=(800, 600), fit=True), {"aspect": 183, "scale": 75})

    def test_shrink_to_fit_leaves_scale_alone_when_the_picture_already_fits(self):
        # 16:9 source in a 400x800 portrait player is 400x225; 4:3 makes it 400x299, still inside
        self.assertEqual(preset(1920, 1080, 4 / 3, player=(400, 800), fit=True), {"aspect": 117, "scale": 100})

    def test_shrink_to_fit_off_never_changes_scale(self):
        self.assertEqual(preset(1920, 1080, 1, player=(1600, 900), fit=False), {"aspect": 72, "scale": 100})

    def test_unknown_video_size_gives_no_result(self):
        # videoWidth and videoHeight are 0 until the video's metadata has loaded
        self.assertIsNone(preset(0, 0, 4 / 3))

    def test_original_does_not_need_the_video_size(self):
        self.assertEqual(preset(0, 0, None), {"aspect": 150, "scale": 100})


if __name__ == "__main__":
    unittest.main()
