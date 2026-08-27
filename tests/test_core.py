from __future__ import annotations

from pathlib import Path
import unittest

from fisheye_studio.ffmpeg_service import (
    _parse_dimensions_from_ffmpeg_line,
    _parse_duration_from_ffmpeg_summary,
    _parse_fps_from_ffmpeg_line,
    build_multi_view_filter,
    estimate_output_bytes,
    sanitize_filename,
)
from fisheye_studio.models import (
    RenderSettings,
    TimestampSettings,
    default_views,
    normalized_to_roll_pitch,
    roll_pitch_to_normalized,
)


class CoreTests(unittest.TestCase):
    def test_cardinal_roll_mapping(self) -> None:
        top = roll_pitch_to_normalized(0, 90)
        right = roll_pitch_to_normalized(90, 90)
        bottom = roll_pitch_to_normalized(180, 90)
        left = roll_pitch_to_normalized(-90, 90)
        self.assertAlmostEqual(top[0], 0.5, places=5)
        self.assertAlmostEqual(top[1], 0.0, places=5)
        self.assertAlmostEqual(right[0], 1.0, places=5)
        self.assertAlmostEqual(right[1], 0.5, places=5)
        self.assertAlmostEqual(bottom[0], 0.5, places=5)
        self.assertAlmostEqual(bottom[1], 1.0, places=5)
        self.assertAlmostEqual(left[0], 0.0, places=5)
        self.assertAlmostEqual(left[1], 0.5, places=5)

    def test_bottom_left_mapping(self) -> None:
        roll, pitch = normalized_to_roll_pitch(0.25, 0.75)
        self.assertAlmostEqual(roll, -135.0, places=4)
        self.assertGreater(pitch, 60)

    def test_filter_contains_all_views(self) -> None:
        views = default_views()
        graph, labels = build_multi_view_filter(views, TimestampSettings(), RenderSettings())
        self.assertEqual(len(labels), 5)
        self.assertIn("roll=180.000", graph)
        self.assertIn("overlay=0:0", graph)

    def test_size_estimate(self) -> None:
        per_view, total = estimate_output_bytes(3300, 5, RenderSettings(), True)
        self.assertGreater(per_view, 1_000_000_000)
        self.assertEqual(total, per_view * 5)


    def test_ffmpeg_only_probe_parser(self) -> None:
        video_line = (
            "Stream #0:0: Video: h264 (High), yuv420p(progressive), "
            "1248x1248, 15 fps, 15 tbr, 15360 tbn"
        )
        summary = "Duration: 00:55:14.10, start: 0.000000, bitrate: 3200 kb/s"
        self.assertEqual(_parse_dimensions_from_ffmpeg_line(video_line), (1248, 1248))
        self.assertAlmostEqual(_parse_duration_from_ffmpeg_summary(summary), 3314.10, places=2)
        self.assertAlmostEqual(_parse_fps_from_ffmpeg_line(video_line), 15.0, places=2)

    def test_filename_sanitizing(self) -> None:
        self.assertEqual(sanitize_filename('Bad:Name?'), 'Bad_Name_')

    def test_compact_ffmpeg_probe_parsing(self) -> None:
        stream_line = (
            "Stream #0:0[0x1](und): Video: h264 (High) (avc1 / 0x31637661), "
            "yuv420p(progressive), 1280x1280 [SAR 1:1 DAR 1:1], 29.97 fps, 30 tbr"
        )
        summary = "Duration: 00:55:13.25, start: 0.000000, bitrate: 3000 kb/s"
        self.assertEqual(_parse_dimensions_from_ffmpeg_line(stream_line), (1280, 1280))
        self.assertAlmostEqual(_parse_fps_from_ffmpeg_line(stream_line), 29.97, places=2)
        self.assertAlmostEqual(_parse_duration_from_ffmpeg_summary(summary), 3313.25, places=2)


if __name__ == "__main__":
    unittest.main()
