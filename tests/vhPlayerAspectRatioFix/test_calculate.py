import unittest

from tests.vhPlayerAspectRatioFix.node_runner import run_plugin


def preset(width, height, ratio, player=(0, 0), fit=False):
    """Slider values the plugin writes for `ratio` (None is Original)."""
    return run_plugin(
        "plugin.sliderValues(input)",
        {
            "naturalWidth": width,
            "naturalHeight": height,
            "ratio": ratio,
            "playerWidth": player[0],
            "playerHeight": player[1],
            "shrinkToFit": fit,
        },
    )


# scale None means the plugin leaves the Scale slider as it is
class AspectTests(unittest.TestCase):
    def test_widescreen_source_to_4_3_stretches_vertically(self):
        # 16:9 to 4:3 is a 1.333x vertical stretch: 150 - 33.3, rounded to 117
        self.assertEqual(preset(1920, 1080, 4 / 3), {"aspect": 117, "scale": None})

    def test_4_3_source_to_16_9_stretches_horizontally(self):
        self.assertEqual(preset(720, 540, 16 / 9), {"aspect": 183, "scale": None})

    def test_matching_ratio_leaves_the_aspect_at_its_default(self):
        self.assertEqual(preset(720, 540, 4 / 3), {"aspect": 150, "scale": None})

    def test_3_2_source(self):
        # 3:2 to 16:9 is a 1.185x horizontal stretch (168.5, rounded up to 169)
        self.assertEqual(preset(720, 480, 16 / 9), {"aspect": 169, "scale": None})
        # 3:2 to 1:1 is a 1.5x vertical stretch
        self.assertEqual(preset(720, 480, 1), {"aspect": 100, "scale": None})

    def test_aspect_is_clamped_to_the_slider_range(self):
        # 1:3 portrait source to 16:9 needs a 5.33x horizontal stretch; the slider stops at 300
        self.assertEqual(preset(360, 1080, 16 / 9), {"aspect": 300, "scale": None})
        # 4:1 source to 1:1 needs a 4x vertical stretch; the slider stops at 0
        self.assertEqual(preset(1600, 400, 1), {"aspect": 0, "scale": None})

    def test_unknown_video_size_gives_no_result(self):
        # videoWidth and videoHeight are 0 until the video's metadata has loaded
        self.assertIsNone(preset(0, 0, 4 / 3))


class OriginalTests(unittest.TestCase):
    def test_original_resets_both_sliders(self):
        self.assertEqual(preset(720, 480, None), {"aspect": 150, "scale": 100})
        self.assertEqual(preset(1920, 1080, None, player=(400, 800), fit=True), {"aspect": 150, "scale": 100})

    def test_original_does_not_need_the_video_size(self):
        self.assertEqual(preset(0, 0, None), {"aspect": 150, "scale": 100})


class ShrinkToFitTests(unittest.TestCase):
    def test_scales_a_vertical_stretch_into_a_landscape_player(self):
        # 16:9 source fills a 1600x900 player; 1:1 stretches it to 1600x1602 (slider 72 is 1.78x)
        self.assertEqual(preset(1920, 1080, 1, player=(1600, 900), fit=True), {"aspect": 72, "scale": 56})

    def test_scales_a_horizontal_stretch(self):
        # 4:3 source fills an 800x600 player; 16:9 stretches it to 1064x600 (slider 183 is 1.33x)
        self.assertEqual(preset(720, 540, 16 / 9, player=(800, 600), fit=True), {"aspect": 183, "scale": 75})

    def test_sets_scale_100_when_the_picture_already_fits(self):
        # 16:9 source in a 400x800 portrait player is 400x225; 4:3 makes it 400x299, still inside
        self.assertEqual(preset(1920, 1080, 4 / 3, player=(400, 800), fit=True), {"aspect": 117, "scale": 100})

    def test_off_leaves_scale_alone(self):
        self.assertEqual(preset(1920, 1080, 1, player=(1600, 900), fit=False), {"aspect": 72, "scale": None})

    def test_unmeasured_player_leaves_scale_alone(self):
        # a hidden or not yet laid out player measures 0x0
        self.assertEqual(preset(1920, 1080, 1, player=(0, 0), fit=True), {"aspect": 72, "scale": None})


if __name__ == "__main__":
    unittest.main()
